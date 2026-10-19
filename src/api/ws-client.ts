import WebSocket from 'ws';
import {
    BinanceRestClient, OrderNotFoundError, OrderStatusUnknownError, binanceError, isFilterFailure, isInsufficientBalance,
    isLotSizeFailure, newClientOrderId
} from './rest-client';
import { brain } from './zmq-client';
import { TelegramClient, escapeHtml } from './telegram-client';
import { config } from '../config/env';
import {
    EntryCost, Execution, SymbolFilters, floorToStep, formatPrice, formatQty, formatUsdt, isTradable,
    mergeExecutions, netPnl, sellableQuantity, soldQuantity
} from './execution';

// Velas de 15 min, igual que el backtest (download_data.py usa data_frequency="15m" y optimize.py
// evalua cierres de 15 min). Si se cambia, cambiar tambien KLINE_INTERVAL en binance-research/config.py.
const KLINE_INTERVAL = '15m';
// Tras un error de orden no se intenta otra compra del mismo simbolo durante este tiempo.
const ORDER_ERROR_COOLDOWN_MS = 60000;
// Tras un fallo de venta se espera esto antes de reintentar (no inundar el REST); si mientras tanto el precio
// cae aun mas bajo el SL, se permite un reintento inmediato una sola vez.
const CLOSE_RETRY_MS = 5000;
// Si no se pudo confirmar una venta, se espera mas antes de consultarla otra vez.
const CLOSE_UNKNOWN_RETRY_MS = 30000;
// Rechazo de una venta por filtro (-1013 NOTIONAL/LOT_SIZE) que con el precio medio de Binance sí es vendible: se
// reintenta con espera creciente (5 s, 10 s, 20 s... hasta 60 s) y se avisa por Telegram desde el tercer rechazo
// (y luego cada 10, para no inundar el chat).
const FILTER_RETRY_MAX_MS = 60000;
const FILTER_ALERT_FROM = 3;
const FILTER_ALERT_EVERY = 10;
// Una orden que Binance dice que no existe puede aparecer tarde (-1007: el motor la procesa después). Antes de darla
// por inexistente (cancelar la compra o reenviar la venta) se vuelve a consultar con espera creciente: 10, 30 y 90 s
// tras cada "no existe" (≈ 2 min en total). Mientras tanto la moneda no abre otra compra (compra dudosa) o la venta no
// se reenvía (venta dudosa); las demás monedas siguen con normalidad y los precios vistos se guardan.
export const LATE_ORDER_RECHECKS_MS = [10000, 30000, 90000];
export const LATE_BUY_CANCEL_REASON = 'NO LLEGÓ A BINANCE (no apareció en ~2 min de consultas)';
// Margen sobre minNotional al decidir si algo es vendible: Binance valora las MARKET con el precio medio reciente.
export const NOTIONAL_MARGIN = 0.01;
// Si el nocional queda a menos de este margen del minimo, se consulta el precio medio de Binance (avgPrice).
const NOTIONAL_CHECK_BAND = 0.25;
// Consultas de una orden con estado desconocido (cada una ya reintenta en rest-client) y espera entre ellas.
const UNKNOWN_ORDER_LOOKUPS = 3;
const UNKNOWN_ORDER_WAIT_MS = 5000;
// Reconexion del WebSocket (Binance corta la conexion cada 24 h): espera inicial y maxima.
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 60000;
// Conexión muerta sin evento 'close' (corte de red o de la VPN que deja el TCP medio abierto): Binance envía un ping
// cada 20 s y cada vela se actualiza cada 2 s; si en STALE_SOCKET_MS no llega nada, se fuerza la reconexión. Sin esto
// el bot dejaría de vigilar los TP/SL en silencio.
export const STALE_SOCKET_MS = 120000;
export const STALE_CHECK_MS = 15000;

export interface Position extends EntryCost {
    symbol: string;
    orderId: number;
    takeProfit: number;
    stopLoss: number;
    quantity: number;       // cantidad comprada (executedQty)
    netQuantity: number;    // cantidad en cartera: comprada menos la comisión cobrada en la moneda base
    // Salida ya decidida (TP/SL tocado): se completa aunque el precio vuelva al rango, como en el backtest
    exitReason?: string;
    exitTrigger?: number;
    // Tramos de venta ya ejecutados (salida en varias órdenes): el cierre los suma todos
    exitParts?: Execution[];
    // newClientOrderId de una venta enviada sin confirmar: antes de vender otra vez se consulta
    unconfirmedSellId?: string;
    // Respuestas "no existe" seguidas de esa venta: se reenvía solo tras agotar LATE_ORDER_RECHECKS_MS
    sellNotFound?: number;
    // Rechazos por filtro de la venta (-1013)
    filterRejections?: number;
    // Recuperada del ledger sin poder verificarla en Binance al arrancar: no se gestiona hasta verificarla
    startupCheckPending?: boolean;
}

interface Tick {
    price: number;
    openTime: number;
}

// Pausa tras un fallo de venta
interface CloseRetry {
    until: number;
    price: number;          // precio con el que se intentó la venta fallida
    slOverride: boolean;    // queda el reintento inmediato si el precio cae aún más bajo el SL
}

// Compra dudosa: registrada como PENDING en el ledger y aún no se sabe si se ejecutó (Binance sin respuesta, o "no
// existe" por ahora). Bloquea nuevas compras de la moneda (pendingEntries guarda sus precios para revisar el TP/SL al
// adoptarla) y se vuelve a consultar con sus precios.
interface UnresolvedBuy {
    clientOrderId: string;
    signalPrice: number | null;
    takeProfit: number;
    stopLoss: number;
    retryAt: number;
    // Respuestas "no existe" seguidas (0: solo sin respuesta). Se cancela al superar LATE_ORDER_RECHECKS_MS.length.
    notFound: number;
    inFlight?: boolean;
}

// Intención de compra (lo que la fila PENDING guarda): lo necesario para adoptar la orden si se ejecutó
interface BuyIntent {
    clientOrderId: string;
    signalPrice: number | null;
    takeProfit: number;
    stopLoss: number;
}

// Resultado de vender lo que falta: nota para el motivo y motivo si no se vendió nada
interface SaleOutcome {
    note: string;
    noSaleReason: string;
    // Cantidad de la posición que sigue en cartera sin vender (residuo bajo el stepSize/mínimo). Se valora en el PnL.
    // Sin dato: lo neto menos lo vendido.
    heldQty?: number;
}

type RestApi = Pick<BinanceRestClient,
    'getSymbolFilters' | 'invalidateSymbolFilters' | 'marketBuy' | 'marketSell' | 'getFreeBalances' | 'getPrice' |
    'getAvgPrice' | 'lookupOrder' | 'getOrder' | 'getMyTrades' | 'tradesToExecution'>;

export interface SocketLike {
    on(event: string, listener: (...args: any[]) => any): unknown;
    close(): void;
    terminate?(): void;   // ws: cierra sin esperar el cierre ordenado (que en una conexión muerta tarda 30 s)
}

export interface WSClientDeps {
    rest: RestApi;
    brain: { ask(type: string, payload?: any): Promise<any> };
    telegram: { sendMessage(message: string): Promise<void> };
    createSocket: (url: string) => SocketLike;
    sleep: (ms: number) => Promise<void>;
}

/** Posición a partir de una fila OPEN del ledger (las filas antiguas no tienen datos de ejecución). */
export function positionFromLedger(trade: any): Position {
    const num = (value: any, fallback: number) =>
        value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? fallback : Number(value);
    const quantity = num(trade.quantity, 0);
    const entryPrice = num(trade.entry_price, 0);
    const netQuantity = num(trade.net_quantity, quantity);
    return {
        symbol: String(trade.symbol),
        orderId: Number(trade.order_id),
        entryPrice,
        takeProfit: num(trade.take_profit, Infinity),
        stopLoss: num(trade.stop_loss, -Infinity),
        quantity,
        netQuantity,
        entryQuote: num(trade.entry_quote, entryPrice * quantity),
        entryFeeQuote: num(trade.entry_fee_usdt, 0),
        entryFeeBaseQty: Math.max(0, quantity - netQuantity)
    };
}

export class BinanceWSClient {
    private ws: SocketLike | null = null;
    private baseUrl = `${config.WS_URL}/stream?streams=`;
    private tradeQuoteUsdt: number;
    private rest: RestApi;
    private brain: WSClientDeps['brain'];
    private telegram: WSClientDeps['telegram'];
    private createSocket: WSClientDeps['createSocket'];
    private sleep: WSClientDeps['sleep'];

    private activePositions: Map<string, Position> = new Map();
    // open_time de la ultima vela cerrada enviada a Python, por simbolo (una evaluacion por vela)
    private lastClosedOpenTime: Map<string, number> = new Map();
    // open_time de la vela en la que se cerro la ultima posicion: la senal de esa misma vela no se opera
    private lastExitOpenTime: Map<string, number> = new Map();
    private orderCooldownUntil: Map<string, number> = new Map();
    // Simbolos con una orden de venta en curso: evita un segundo SELL mientras se espera al REST
    private closing: Set<string> = new Set();
    // Simbolos con una compra en curso y los precios vistos mientras tanto: al registrar la posicion se
    // comprueban contra TP/SL (el precio pudo tocarlos antes de que la posicion existiera)
    private pendingEntries: Map<string, Tick[]> = new Map();
    // Pausa tras un fallo de venta, por simbolo
    private closeRetry: Map<string, CloseRetry> = new Map();
    // Ventas sin confirmar ya avisadas por Telegram (un aviso por orden)
    private notifiedUnknownSells: Set<string> = new Set();
    // Próximo reintento de la verificación del arranque que falló, por símbolo
    private startupCheckRetryAt: Map<string, number> = new Map();
    // Compras PENDING sin resolver (estado desconocido), por símbolo
    private unresolvedBuys: Map<string, UnresolvedBuy> = new Map();

    private url: string;
    private stopped = false;
    private reconnectDelayMs = RECONNECT_MIN_MS;
    // Último mensaje, ping o pong del WebSocket (vigilancia de conexión muerta)
    private lastSocketActivityAt = 0;
    private watchdog: ReturnType<typeof setInterval> | null = null;

    /**
     * @param tradeQuoteUsdt USDT por operación. Lo da Python en el handshake (optimize.NOTIONAL_USDT): así el
     *                       vivo compra exactamente el importe que simula el backtest.
     */
    constructor(roster: string[], tradeQuoteUsdt: number, deps: Partial<WSClientDeps> = {}) {
        if (!Number.isFinite(tradeQuoteUsdt) || tradeQuoteUsdt <= 0) {
            throw new Error(`Tamaño por operación no válido: ${tradeQuoteUsdt}`);
        }
        this.tradeQuoteUsdt = tradeQuoteUsdt;
        this.rest = deps.rest ?? new BinanceRestClient();
        this.brain = deps.brain ?? brain;
        this.telegram = deps.telegram ?? new TelegramClient();
        this.createSocket = deps.createSocket ?? ((url: string) => new WebSocket(url));
        this.sleep = deps.sleep ?? (ms => new Promise(resolve => setTimeout(resolve, ms)));
        const streams = roster.map(symbol => `${symbol.toLowerCase()}@kline_${KLINE_INTERVAL}`).join('/');
        this.url = `${this.baseUrl}${streams}`;
    }

    /** Recupera las posiciones del ledger y despues abre el WebSocket: ningun precio llega sin ellas. */
    public async start() {
        await this.syncStateFromLedger();
        if (this.stopped) return;
        this.ws = this.connect();
        if (!this.watchdog) {
            this.watchdog = setInterval(() => this.checkSocketAlive(), STALE_CHECK_MS);
            (this.watchdog as any).unref?.();   // no mantiene vivo el proceso por sí solo
        }
    }

    /** Si el WebSocket lleva STALE_SOCKET_MS sin mensajes ni pings, se corta: el evento 'close' reconecta. */
    private checkSocketAlive() {
        if (this.stopped || !this.ws) return;
        const idle = Date.now() - this.lastSocketActivityAt;
        if (idle < STALE_SOCKET_MS) return;
        console.warn(`[WS] ${Math.round(idle / 1000)} s sin datos ni pings de Binance: se fuerza la reconexión.`);
        this.lastSocketActivityAt = Date.now();
        try {
            if (this.ws.terminate) this.ws.terminate();
            else this.ws.close();
        } catch (error: any) {
            console.error('[WS] No se pudo cortar la conexión muerta:', error?.message ?? error);
        }
    }

    public getPosition(symbol: string): Readonly<Position> | undefined {
        return this.activePositions.get(symbol);
    }

    // Las velas que falten tras una reconexion las recupera Python (fill_gap) con la siguiente vela cerrada.
    private connect(): SocketLike {
        const ws = this.createSocket(this.url);
        this.lastSocketActivityAt = Date.now();
        const alive = () => { this.lastSocketActivityAt = Date.now(); };

        ws.on('open', () => {
            console.log(`[WS] WebSocket connected to combined stream.`);
            this.reconnectDelayMs = RECONNECT_MIN_MS;
            alive();
        });
        // ws contesta solo a los pings de Binance (cada 20 s); aquí solo cuentan como señal de vida
        ws.on('ping', alive);
        ws.on('pong', alive);

        ws.on('message', async (data: WebSocket.RawData) => {
            alive();
            try {
                const parsedData = JSON.parse(data.toString());
                if (parsedData.data && parsedData.data.e === 'kline') {
                    await this.handleMarketData(parsedData.data);
                }
            } catch (err: any) {
                console.error('[WS] Error procesando mensaje:', err?.message ?? err);
            }
        });

        ws.on('error', (error: any) => console.error('[WS] Error:', error?.message ?? error));
        ws.on('close', () => {
            console.log('[WS] Connection closed.');
            this.scheduleReconnect();
        });

        return ws;
    }

    private scheduleReconnect() {
        if (this.stopped) return;
        const delay = this.reconnectDelayMs;
        this.reconnectDelayMs = Math.min(delay * 2, RECONNECT_MAX_MS);
        console.log(`[WS] Reconnecting in ${delay / 1000}s...`);
        setTimeout(() => {
            if (this.stopped) return;
            try {
                this.ws = this.connect();
            } catch (error: any) {
                // Un fallo al crear el socket no puede escapar del temporizador: se reintenta más tarde
                console.error('[WS] No se pudo reconectar:', error?.message ?? error);
                this.scheduleReconnect();
            }
        }, delay);
    }

    private async handleMarketData(data: any) {
        const symbol = data.s;
        const kline = data.k;
        const currentPrice = parseFloat(kline.c);
        const openTime = Number(kline.t);

        // 0. Con una compra en curso se guardan los precios: se revisan contra TP/SL al registrar la posicion.
        this.pendingEntries.get(symbol)?.push({ price: currentPrice, openTime });
        //    Una compra PENDING sin resolver se vuelve a consultar (como mucho cada pocos segundos).
        const unresolved = this.unresolvedBuys.get(symbol);
        if (unresolved) await this.retryUnresolvedBuy(symbol, unresolved);

        // 1. Cada actualizacion (vela cerrada o no) vigila el TP/SL de la posicion abierta con el precio actual.
        if (this.activePositions.has(symbol)) {
            await this.manageExistingPosition(symbol, currentPrice, openTime);
        }

        // 2. La estrategia solo ve velas CERRADAS (k.x), una vez por vela y simbolo. Tambien con posicion
        //    abierta, para que su ventana no se congele; en ese caso evaluateNewTrade ignora el BUY.
        if (kline.x !== true) return;
        const lastSent = this.lastClosedOpenTime.get(symbol);
        if (lastSent !== undefined && openTime <= lastSent) return;
        this.lastClosedOpenTime.set(symbol, openTime);

        const marketData = {
            open_time: openTime,
            open: parseFloat(kline.o),
            high: parseFloat(kline.h),
            low: parseFloat(kline.l),
            close: currentPrice,
            volume: parseFloat(kline.v)
        };
        await this.evaluateNewTrade(symbol, marketData, data.E);
    }

    private async manageExistingPosition(symbol: string, currentPrice: number, openTime: number) {
        if (this.closing.has(symbol)) return;
        const position = this.activePositions.get(symbol);
        if (!position) return;
        if (position.startupCheckPending && !(await this.retryStartupCheck(symbol, position))) return;
        const hitTp = currentPrice >= position.takeProfit;
        const hitSl = currentPrice <= position.stopLoss;
        // Una salida ya decidida (venta fallida o a medias) se completa con cualquier precio, con su motivo y nivel
        if (position.exitReason === undefined && !hitTp && !hitSl) return;

        // Pausa tras un fallo de venta: solo se adelanta una vez, si el precio cae aun mas bajo el SL
        let override = false;
        const retry = this.closeRetry.get(symbol);
        if (retry && Date.now() < retry.until) {
            if (!(hitSl && retry.slOverride && currentPrice < retry.price)) return;
            retry.slOverride = false;
            override = true;
            console.log(`[EXIT] ${symbol}: el precio sigue cayendo bajo el SL (${currentPrice} < ${retry.price}); reintento inmediato.`);
        }

        // Modificamos para enviar el motivo exacto del cierre
        if (position.exitReason !== undefined) {
            console.log(`\n[EXIT RETRY] ${symbol} @ ${currentPrice}: se completa la salida (${position.exitReason}).`);
            await this.closePosition(symbol, position, position.exitTrigger ?? currentPrice, position.exitReason, openTime, override);
        } else if (hitTp) {
            console.log(`\n[TAKE PROFIT HIT] ${symbol} @ ${currentPrice}. Exiting trade.`);
            await this.closePosition(symbol, position, currentPrice, "TAKE PROFIT ✅", openTime, override);
        } else {
            console.log(`\n[STOP LOSS HIT] ${symbol} @ ${currentPrice}. Cutting losses.`);
            await this.closePosition(symbol, position, currentPrice, "STOP LOSS ⚠️", openTime, override);
        }
    }

    private async evaluateNewTrade(symbol: string, marketData: { open_time: number; [k: string]: number }, timestamp: number) {
        let signal: any;
        try {
            signal = await this.brain.ask('evaluate', {
                symbol: symbol,
                market_data: marketData,
                timestamp: timestamp
            });
        } catch (error: any) {
            console.error(`[BRAIN] ${symbol}: no se pudo evaluar la vela:`, error?.message ?? error);
            return;
        }
        if (signal && signal.action === 'BUY' && this.canOpenPosition(symbol, marketData.open_time)) {
            // Sin niveles numéricos la posición nunca se cerraría
            if (!Number.isFinite(signal.take_profit) || !Number.isFinite(signal.stop_loss)) {
                console.error(`[SIGNAL] ${symbol}: BUY sin take_profit/stop_loss numéricos, no se opera.`, signal);
                return;
            }
            await this.openPosition(symbol, signal);
        }
    }

    // Una posicion por moneda, como el backtest: el BUY se ignora con posicion abierta (o compra en curso), en la
    // misma vela en la que se cerro la anterior (la senal debe ser posterior a la vela de salida) y durante el
    // cooldown por error.
    private canOpenPosition(symbol: string, openTime: number): boolean {
        if (this.activePositions.has(symbol) || this.pendingEntries.has(symbol)) {
            console.log(`[SIGNAL] ${symbol}: BUY ignorado, ya hay una posición abierta.`);
            return false;
        }
        if (this.unresolvedBuys.has(symbol)) {
            console.log(`[SIGNAL] ${symbol}: BUY ignorado, hay una compra anterior sin confirmar en Binance.`);
            return false;
        }
        const lastExit = this.lastExitOpenTime.get(symbol);
        if (lastExit !== undefined && openTime <= lastExit) {
            console.log(`[SIGNAL] ${symbol}: BUY ignorado, la posición anterior se cerró en esta vela.`);
            return false;
        }
        if (Date.now() < (this.orderCooldownUntil.get(symbol) ?? 0)) {
            console.log(`[SIGNAL] ${symbol}: BUY ignorado, cooldown por error de orden.`);
            return false;
        }
        return true;
    }

    /**
     * Compra MARKET por tradeQuoteUsdt. Antes de enviarla se escribe en el ledger una fila PENDING con su
     * newClientOrderId: si el proceso muere entre la ejecución y el registro, al arrancar se encuentra en Binance.
     * La posición se registra (la misma fila pasa a OPEN) con lo ejecutado de verdad y con los TP/SL absolutos de la
     * estrategia. Si la compra queda sin confirmar, se consulta por su newClientOrderId y, si se ejecutó, se adopta.
     */
    private async openPosition(symbol: string, signal: any) {
        console.log(`\n=========================================`);
        console.log(`[NEW TRADE] Python signal for ${symbol}`);
        this.pendingEntries.set(symbol, []);
        const intent: BuyIntent = {
            clientOrderId: newClientOrderId('BUY'),
            signalPrice: Number.isFinite(signal.entry_price) ? signal.entry_price : null,
            takeProfit: signal.take_profit,
            stopLoss: signal.stop_loss
        };

        let filters: SymbolFilters;
        try {
            filters = await this.rest.getSymbolFilters(symbol);
        } catch (error: any) {
            this.pendingEntries.delete(symbol);
            this.handleOrderError(symbol, error);
            return;
        }
        // 0. Sin la fila PENDING no se compra: una compra no registrada quedaría huérfana si el proceso muere
        if (!(await this.ledgerPending(symbol, intent))) {
            this.pendingEntries.delete(symbol);
            this.handleOrderError(symbol, new Error('no se pudo registrar la compra pendiente en el ledger; no se envía'));
            return;
        }

        let exec: Execution;
        let adopted = false;
        try {
            exec = await this.rest.marketBuy(symbol, this.tradeQuoteUsdt, signal.entry_price, intent.clientOrderId);
        } catch (error: any) {
            if (!(error instanceof OrderStatusUnknownError || error instanceof OrderNotFoundError)) {
                // Rechazada (4xx) o no enviada: la orden no existe en Binance
                this.pendingEntries.delete(symbol);
                await this.ledgerCancel(symbol, intent.clientOrderId, `RECHAZADA: ${binanceError(error).msg}`);
                this.handleOrderError(symbol, error);
                return;
            }
            console.warn(`[ORDER UNKNOWN] ${symbol}: compra ${intent.clientOrderId} sin confirmar; se consulta en Binance...`);
            let outcome: Execution | null | 'unknown' = null;   // OrderNotFoundError: Binance ya dijo "no existe"
            if (error instanceof OrderStatusUnknownError) {
                try {
                    outcome = await this.resolveUnknownOrder(symbol, intent.clientOrderId);
                } catch {
                    outcome = 'unknown';
                }
            }
            if (outcome === null || outcome === 'unknown') {
                // Compra dudosa: la fila sigue PENDING, la moneda no abre otra compra y pendingEntries sigue guardando
                // los precios. Se vuelve a consultar con los próximos precios: "no existe" con espera creciente
                // (LATE_ORDER_RECHECKS_MS, puede aparecer tarde); sin respuesta, cada CLOSE_RETRY_MS.
                const notFound = outcome === null ? 1 : 0;
                this.unresolvedBuys.set(symbol, {
                    ...intent, notFound,
                    retryAt: Date.now() + (notFound ? LATE_ORDER_RECHECKS_MS[0]! : CLOSE_RETRY_MS)
                });
                this.handleOrderError(symbol, new OrderStatusUnknownError(symbol, intent.clientOrderId, error));
                return;
            }
            exec = outcome;
            adopted = true;
        }
        if (!(exec.executedQty > 0)) {
            this.pendingEntries.delete(symbol);
            await this.ledgerCancel(symbol, intent.clientOrderId, `SIN EJECUTAR (${exec.status})`);
            console.log(`[ORDER FAILED] ${symbol}: la compra MARKET no se ejecutó (status ${exec.status}).`);
            this.notify(`❌ <b>ERROR DE ORDEN: ${symbol}</b>\nLa compra a mercado no se ejecutó (<i>${escapeHtml(exec.status)}</i>).`);
            this.orderCooldownUntil.set(symbol, Date.now() + ORDER_ERROR_COOLDOWN_MS);
            return;
        }
        await this.registerEntry(symbol, exec, intent, filters, adopted);
    }

    /** Posición a partir de lo ejecutado de verdad y de los niveles absolutos de la estrategia. */
    private positionFromExecution(symbol: string, exec: Execution, intent: BuyIntent): Position {
        return {
            symbol,
            orderId: exec.orderId,
            entryPrice: exec.avgPrice,
            takeProfit: intent.takeProfit,
            stopLoss: intent.stopLoss,
            quantity: exec.executedQty,
            netQuantity: exec.executedQty - exec.fees.baseQty,
            entryQuote: exec.quoteQty,
            entryFeeQuote: exec.fees.totalQuote,
            entryFeeBaseQty: exec.fees.baseQty
        };
    }

    /**
     * Registra una compra ejecutada: ledger (la fila PENDING pasa a OPEN), posición activa, aviso y revisión de los
     * precios vistos mientras se compraba (carrera compra/TP-SL).
     */
    private async registerEntry(symbol: string, exec: Execution, intent: BuyIntent, filters: SymbolFilters, adopted: boolean) {
        if (exec.fees.unpriced.length) {
            console.warn(`[FEES] ${symbol}: comisión en ${exec.fees.unpriced.join(', ')} sin valorar en USDT (cuenta 0).`);
        }
        const position = this.positionFromExecution(symbol, exec, intent);

        // 1. Ledger antes de registrar la posicion: una salida inmediata necesita la fila para cerrarla.
        await this.ledgerOpen(position, exec, intent.signalPrice, intent.clientOrderId);

        // 2. Se registra la posicion y se revisan los precios vistos mientras se compraba (carrera compra/TP-SL).
        const ticks = this.pendingEntries.get(symbol) ?? [];
        this.pendingEntries.delete(symbol);
        this.activePositions.set(symbol, position);

        const px = (value: number) => formatPrice(value, filters.tickSize);
        const signalText = intent.signalPrice !== null ? px(intent.signalPrice) : '?';
        console.log(`[ENTRY FILLED] ${symbol}: ${exec.executedQty} @ ${px(exec.avgPrice)} (señal ${signalText}), ` +
            `${exec.quoteQty.toFixed(4)} USDT, comisión ${exec.fees.detail || '0'}${adopted ? ' (confirmada tras consultar la orden)' : ''}`);
        this.notify(
            `🚀 <b>NUEVA COMPRA: ${symbol}</b>\n` +
            `🔹 <b>Precio:</b> $${px(exec.avgPrice)} (señal $${signalText})\n` +
            `📦 <b>Cantidad:</b> ${formatQty(exec.executedQty)} (${exec.quoteQty.toFixed(2)} USDT)\n` +
            `💸 <b>Comisión:</b> ${exec.fees.totalQuote.toFixed(4)} USDT${exec.fees.detail ? ` (${exec.fees.detail})` : ''}\n` +
            `🎯 <b>Target:</b> $${px(position.takeProfit)}\n` +
            `🛡️ <b>Riesgo:</b> $${px(position.stopLoss)}` +
            (adopted ? `\n<i>Orden confirmada tras consultarla en Binance.</i>` : '')
        );
        console.log(`=========================================\n`);

        const hit = ticks.find(t => t.price >= position.takeProfit || t.price <= position.stopLoss);
        if (hit) {
            console.log(`[RACE] ${symbol}: el precio tocó TP/SL (${hit.price}) mientras se colocaba la compra.`);
            await this.manageExistingPosition(symbol, hit.price, hit.openTime);
        }
    }

    /**
     * Vuelve a consultar una compra dudosa (PENDING sin resolver) cuando toca: sin respuesta, cada CLOSE_RETRY_MS; tras
     * un "no existe", pasados 10, 30 y 90 s (LATE_ORDER_RECHECKS_MS). Ejecutada: se adopta como posición abierta y los
     * precios vistos mientras tanto se revisan contra su TP/SL. "No existe" también en la última consulta (≈ 2 min):
     * la fila pasa a CANCELLED y la moneda vuelve a poder comprar.
     */
    private async retryUnresolvedBuy(symbol: string, pending: UnresolvedBuy) {
        if (pending.inFlight || Date.now() < pending.retryAt) return;
        pending.inFlight = true;
        try {
            let exec: Execution | null;
            let filters: SymbolFilters;
            try {
                exec = await this.rest.lookupOrder(symbol, pending.clientOrderId);
                filters = await this.rest.getSymbolFilters(symbol);
            } catch (error: any) {
                pending.retryAt = Date.now() + CLOSE_RETRY_MS;
                console.warn(`[ORDER UNKNOWN] ${symbol}: la compra ${pending.clientOrderId} sigue sin confirmar (${binanceError(error).msg}).`);
                return;
            }
            if (exec === null) {
                pending.notFound += 1;
                if (pending.notFound <= LATE_ORDER_RECHECKS_MS.length) {
                    const waitMs = LATE_ORDER_RECHECKS_MS[pending.notFound - 1]!;
                    pending.retryAt = Date.now() + waitMs;
                    console.warn(`[ORDER UNKNOWN] ${symbol}: Binance aún no tiene la compra ${pending.clientOrderId} ` +
                        `(${pending.notFound}.ª vez); se vuelve a consultar en ${waitMs / 1000} s.`);
                    return;
                }
                this.unresolvedBuys.delete(symbol);
                this.pendingEntries.delete(symbol);
                await this.ledgerCancel(symbol, pending.clientOrderId, LATE_BUY_CANCEL_REASON);
                this.notify(`ℹ️ <b>COMPRA DESCARTADA: ${symbol}</b>\nLa orden <code>${escapeHtml(pending.clientOrderId)}</code> ` +
                    `no existe en Binance (consultada durante ~2 min).`);
                return;
            }
            this.unresolvedBuys.delete(symbol);
            if (!(exec.executedQty > 0)) {
                this.pendingEntries.delete(symbol);
                await this.ledgerCancel(symbol, pending.clientOrderId, `SIN EJECUTAR (${exec.status})`);
                return;
            }
            // Hasta que registerEntry deje la posición activa (espera al ledger), la moneda sigue bloqueada para otra
            // compra; pendingEntries ya tiene los precios vistos durante la duda y registerEntry los revisa contra el TP/SL.
            if (!this.pendingEntries.has(symbol)) this.pendingEntries.set(symbol, []);
            console.log(`[ORDER UNKNOWN] ${symbol}: la compra ${pending.clientOrderId} sí se ejecutó; se adopta la posición.`);
            await this.registerEntry(symbol, exec, pending, filters, true);
        } finally {
            pending.inFlight = false;
        }
    }

    private handleOrderError(symbol: string, error: any) {
        if (error instanceof OrderStatusUnknownError) {
            console.error(`[ORDER UNKNOWN] ${symbol}: ${error.message}`);
            this.notify(`❗ <b>COMPRA SIN CONFIRMAR: ${symbol}</b>\nTras varias consultas no se pudo saber si la orden ` +
                `<code>${escapeHtml(error.clientOrderId)}</code> se ejecutó. Queda PENDIENTE en el ledger y se sigue ` +
                `consultando con cada precio: si se ejecutó, se adopta la posición; si no existe, se cancela.`);
        } else {
            const msg = binanceError(error).msg;
            console.log(`[ORDER FAILED] ${symbol}:`, msg);
            // Notificación de error crítico en ejecución
            this.notify(`❌ <b>ERROR DE ORDEN: ${symbol}</b>\nNo se abrió la posición: <i>${escapeHtml(msg)}</i>`);
        }
        console.log(`[SYSTEM] Applying 60-second cooldown to ${symbol}...`);
        this.orderCooldownUntil.set(symbol, Date.now() + ORDER_ERROR_COOLDOWN_MS);
    }

    /**
     * Orden con estado desconocido: se consulta por newClientOrderId hasta UNKNOWN_ORDER_LOOKUPS veces.
     * Devuelve la ejecución real, null si Binance no la tiene, o lanza OrderStatusUnknownError.
     */
    private async resolveUnknownOrder(symbol: string, clientOrderId: string): Promise<Execution | null> {
        let lastError: unknown = null;
        for (let attempt = 0; attempt < UNKNOWN_ORDER_LOOKUPS; attempt++) {
            if (attempt > 0) await this.sleep(UNKNOWN_ORDER_WAIT_MS * attempt);
            try {
                return await this.rest.lookupOrder(symbol, clientOrderId);
            } catch (error: any) {
                lastError = error;
                console.warn(`[ORDER UNKNOWN] ${symbol}: consulta ${attempt + 1}/${UNKNOWN_ORDER_LOOKUPS} de ${clientOrderId} sin respuesta.`);
            }
        }
        throw new OrderStatusUnknownError(symbol, clientOrderId, lastError);
    }

    private async closePosition(symbol: string, position: Position, triggerPrice: number, reason: string, openTime: number,
                                override = false) {
        this.closing.add(symbol);
        const parts = position.exitParts ?? (position.exitParts = []);
        // Desde aquí la salida está decidida: si falla o queda a medias, se completa en los siguientes precios
        position.exitReason ??= reason;
        position.exitTrigger ??= triggerPrice;
        try {
            const filters = await this.rest.getSymbolFilters(symbol);

            // Una venta anterior quedó sin confirmar: si se ejecutó, cuenta como tramo (no se vende dos veces)
            if (position.unconfirmedSellId) {
                const prior = await this.resolveUnknownOrder(symbol, position.unconfirmedSellId);
                if (prior === null) {
                    // Venta dudosa que (aún) no aparece: solo se reenvía tras agotar las esperas (≈ 2 min)
                    position.sellNotFound = (position.sellNotFound ?? 0) + 1;
                    if (position.sellNotFound <= LATE_ORDER_RECHECKS_MS.length) {
                        throw new OrderNotFoundError(symbol, position.unconfirmedSellId, new Error('sigue sin aparecer'));
                    }
                    console.warn(`[EXIT] ${symbol}: la venta ${position.unconfirmedSellId} no apareció en ~2 min; se vende otra vez.`);
                }
                delete position.unconfirmedSellId;
                delete position.sellNotFound;
                if (prior && prior.executedQty > 0) parts.push(prior);
            }

            const outcome = await this.sellRemaining(symbol, position, triggerPrice, filters);
            await this.finishClose(symbol, position, filters, reason, outcome, triggerPrice, openTime);
        } catch (error: any) {
            // La posicion sigue en activePositions (con los tramos ya vendidos): se reintenta mas tarde
            await this.handleCloseError(symbol, position, error, triggerPrice, reason, openTime, override);
        } finally {
            this.closing.delete(symbol);
        }
    }

    /**
     * Vende a mercado lo que falte de la posición (cada tramo ejecutado se guarda en position.exitParts).
     * - Saldo insuficiente (p. ej. una comisión no prevista): se vende lo libre.
     * - MARKET llenada en parte o sin llenar (libro sin liquidez): se intenta con el resto.
     * - Tramo sin confirmar: se consulta; si sigue desconocido, se lanza y la posición espera.
     * Si al terminar aún queda algo vendible, lanza (se reintenta); lo que quede por debajo del mínimo es polvo.
     */
    private async sellRemaining(symbol: string, position: Position, price: number, f: SymbolFilters): Promise<SaleOutcome> {
        const parts = position.exitParts ?? (position.exitParts = []);
        let limit = position.netQuantity;   // máximo vendible: la posición, o lo libre si Binance dice que hay menos
        let note = '';
        for (let attempt = 0; attempt < 3; attempt++) {
            const qty = floorToStep(limit - soldQuantity(parts), f.stepSize);
            if (!(await this.isSellable(symbol, parseFloat(qty), price, f))) break;
            try {
                const exec = await this.rest.marketSell(symbol, qty);
                if (exec.executedQty > 0) parts.push(exec);
            } catch (error: any) {
                if (error instanceof OrderStatusUnknownError) {
                    position.unconfirmedSellId = error.clientOrderId;
                    const resolved = await this.resolveUnknownOrder(symbol, error.clientOrderId);
                    // "No existe" puede ser que aún no aparezca (-1007): venta dudosa, se reconsulta con espera creciente
                    if (resolved === null) {
                        position.sellNotFound = 1;
                        throw new OrderNotFoundError(symbol, error.clientOrderId, error);
                    }
                    delete position.unconfirmedSellId;
                    if (resolved.executedQty > 0) parts.push(resolved);
                    continue;
                }
                if (error instanceof OrderNotFoundError) {
                    position.unconfirmedSellId = error.clientOrderId;
                    position.sellNotFound = 1;
                    throw error;
                }
                if (!isInsufficientBalance(error)) throw error;
                const free = (await this.rest.getFreeBalances()).get(f.baseAsset) ?? 0;
                if (free >= parseFloat(qty)) throw error; // el saldo alcanza: no es eso, se reintenta más tarde
                console.warn(`[EXIT] ${symbol}: saldo insuficiente, libre ${free} ${f.baseAsset} para vender ${qty}.`);
                note = ` (saldo insuficiente: libre ${formatQty(free)} de ${qty} ${f.baseAsset})`;
                limit = soldQuantity(parts) + free;
            }
        }
        const remaining = parseFloat(floorToStep(limit - soldQuantity(parts), f.stepSize));
        if (await this.isSellable(symbol, remaining, price, f)) {
            throw new Error(`venta incompleta de ${symbol}: quedan ${remaining} ${f.baseAsset} por vender`);
        }
        const unsold = formatQty(Math.max(0, position.netQuantity - soldQuantity(parts)));
        return {
            note,
            noSaleReason: note ? `SIN SALDO${note}` : `POLVO: ${unsold} ${f.baseAsset} por debajo del mínimo de Binance, no se puede vender`,
            // Con saldo insuficiente, limit ya es lo vendido + lo libre: no se valora lo que no está en la cuenta
            heldQty: Math.max(0, limit - soldQuantity(parts))
        };
    }

    /**
     * ¿Es vendible esta cantidad? minQty/maxQty y mínimo nocional con margen. Cerca del mínimo se usa el precio
     * medio de Binance (avgPrice), que es con el que valora las MARKET, en vez del último precio.
     */
    private async isSellable(symbol: string, qty: number, price: number, f: SymbolFilters): Promise<boolean> {
        if (!isTradable(qty, price, { ...f, minNotional: 0 })) return false;
        if (f.minNotional <= 0) return true;
        if (qty * price >= f.minNotional * (1 + NOTIONAL_CHECK_BAND)) return true;
        let reference = price;
        try {
            reference = await this.rest.getAvgPrice(symbol);
        } catch {
            // sin precio medio se usa el último precio
        }
        return isTradable(qty, reference, f, NOTIONAL_MARGIN);
    }

    /**
     * Registra la salida con todos los tramos vendidos (PnL neto real) o, si no se vendió nada, la cierra sin venta.
     * triggerPrice null / openTime undefined: cierre detectado al arrancar (sin vela ni nivel).
     */
    private async finishClose(symbol: string, position: Position, f: SymbolFilters, reason: string, outcome: SaleOutcome,
                              triggerPrice: number | null, openTime?: number) {
        const parts = position.exitParts ?? [];
        if (parts.length === 0) {
            await this.closeWithoutSale(symbol, position, outcome.noSaleReason, openTime);
            return;
        }
        const exec = mergeExecutions(parts);
        let note = outcome.note;
        const unsold = parseFloat(floorToStep(position.netQuantity - exec.executedQty, f.stepSize));
        if (unsold > 0 && !note) note = ` (quedan ${formatQty(unsold)} ${f.baseAsset} sin vender)`;
        // Residuo que sigue en la cuenta (Binance da las cantidades con 8 decimales): se valora al precio de salida
        const residual = Number(Math.max(0, outcome.heldQty ?? (position.netQuantity - exec.executedQty)).toFixed(8));

        this.activePositions.delete(symbol);
        if (openTime !== undefined) this.lastExitOpenTime.set(symbol, openTime);
        this.closeRetry.delete(symbol);

        const pnl = netPnl(position, exec, residual);
        const px = (value: number) => formatPrice(value, f.tickSize);
        console.log(`[EXIT CONFIRMED] ${symbol} closed. Order ID: ${exec.orderId} | ${exec.executedQty} @ ${px(exec.avgPrice)} ` +
            `| PnL neto ${formatUsdt(pnl)}${residual > 0 ? ` (residuo ${formatQty(residual)} ${f.baseAsset})` : ''}`);

        await this.ledgerClose({
            order_id: position.orderId,
            symbol,
            exit_price: exec.avgPrice,
            exit_quantity: exec.executedQty,
            exit_quote: exec.quoteQty,
            exit_fee_usdt: exec.fees.totalQuote,
            exit_fees: exec.fees.detail,
            exit_order_id: exec.orderId,
            exit_trigger_price: triggerPrice,
            residual_quantity: residual,
            pnl: pnl,
            reason: reason + note
        });

        const fees = position.entryFeeQuote + exec.fees.totalQuote;
        this.notify(
            `<b>${escapeHtml(reason)}</b>\n` +
            `🔹 <b>Moneda:</b> ${symbol}\n` +
            `🔹 <b>Entrada:</b> $${px(position.entryPrice)}\n` +
            `🔹 <b>Salida:</b> $${px(exec.avgPrice)}${triggerPrice !== null ? ` (nivel $${px(triggerPrice)})` : ''}\n` +
            `💸 <b>Comisiones:</b> ${fees.toFixed(4)} USDT\n` +
            (residual > 0 ? `🧹 <b>Residuo sin vender:</b> ${formatQty(residual)} ${f.baseAsset} ` +
                `(${(residual * exec.avgPrice).toFixed(4)} USDT, incluido en el PnL)\n` : '') +
            `💰 <b>PnL neto:</b> ${formatUsdt(pnl)}` +
            (note ? `\n<i>${escapeHtml(note.trim())}</i>` : '')
        );
    }

    private async handleCloseError(symbol: string, position: Position, error: any, triggerPrice: number, reason: string,
                                   openTime: number, override: boolean) {
        const msg = binanceError(error).msg;
        console.error(`[ERROR] Closing position for ${symbol}:`, msg);

        if (error instanceof OrderStatusUnknownError) {
            position.unconfirmedSellId = error.clientOrderId;
            this.setCloseRetry(symbol, CLOSE_UNKNOWN_RETRY_MS, triggerPrice, false);
            if (!this.notifiedUnknownSells.has(error.clientOrderId)) {
                this.notifiedUnknownSells.add(error.clientOrderId);
                this.notify(`❗ <b>VENTA SIN CONFIRMAR: ${symbol}</b>\nSe consultará la orden <code>${escapeHtml(error.clientOrderId)}</code> ` +
                    `antes de volver a vender.`);
            }
            return;
        }

        if (error instanceof OrderNotFoundError) {
            // Venta dudosa: sin respuesta y "no existe" al consultarla, puede aparecer tarde. Se reconsulta pasados
            // 10, 30 y 90 s (LATE_ORDER_RECHECKS_MS) antes de volver a vender, sin adelanto por el SL
            position.unconfirmedSellId = error.clientOrderId;
            position.sellNotFound ??= 1;
            const waitMs = LATE_ORDER_RECHECKS_MS[Math.min(position.sellNotFound, LATE_ORDER_RECHECKS_MS.length) - 1]!;
            this.setCloseRetry(symbol, waitMs, triggerPrice, false);
            if (position.sellNotFound === 1) {
                this.notify(`❗ <b>VENTA SIN CONFIRMAR: ${symbol}</b>\nBinance aún no muestra la orden ` +
                    `<code>${escapeHtml(error.clientOrderId)}</code>; se consulta durante ~2 min antes de volver a vender.`);
            }
            return;
        }

        if (isFilterFailure(error)) {
            // Binance rechaza la cantidad (NOTIONAL/LOT_SIZE). Solo es polvo si, valorada con su precio medio (con el
            // que juzga las MARKET), no llega al mínimo con margen; si es vendible se reintenta con espera creciente.
            const rejections = (position.filterRejections ?? 0) + 1;
            position.filterRejections = rejections;
            // El paso o los límites de cantidad guardados pueden estar desactualizados: se vuelven a leer
            if (isLotSizeFailure(error)) this.rest.invalidateSymbolFilters(symbol);
            try {
                const f = await this.rest.getSymbolFilters(symbol);
                let dust = false;
                try {
                    const avg = await this.rest.getAvgPrice(symbol);
                    const qty = parseFloat(floorToStep(position.netQuantity - soldQuantity(position.exitParts), f.stepSize));
                    dust = !isTradable(qty, avg, f, NOTIONAL_MARGIN);
                } catch {
                    // sin precio medio no se puede confirmar que sea polvo: se reintenta
                }
                if (dust) {
                    await this.finishClose(symbol, position, f, reason,
                        { note: ` (resto no vendible: ${msg})`,
                          noSaleReason: `POLVO: Binance rechaza la venta (${msg}) y con su precio medio no llega al mínimo` },
                        triggerPrice, openTime);
                    return;
                }
            } catch (inner: any) {
                console.error(`[ERROR] ${symbol}: no se pudo comprobar el rechazo por filtro:`, binanceError(inner).msg);
            }
            const waitMs = Math.min(CLOSE_RETRY_MS * 2 ** (rejections - 1), FILTER_RETRY_MAX_MS);
            this.setCloseRetry(symbol, waitMs, triggerPrice, false);
            if (rejections === FILTER_ALERT_FROM ||
                (rejections > FILTER_ALERT_FROM && (rejections - FILTER_ALERT_FROM) % FILTER_ALERT_EVERY === 0)) {
                this.notify(`⚠️ <b>VENTA RECHAZADA: ${symbol}</b>\nBinance rechazó la venta ${rejections} veces ` +
                    `(<i>${escapeHtml(msg)}</i>), pero con su precio medio la posición es vendible: se reintenta cada ` +
                    `${Math.round(waitMs / 1000)} s.`);
            }
            return;
        }

        // Error genérico: pausa de 5 s; el reintento inmediato por caída bajo el SL no se encadena
        this.setCloseRetry(symbol, CLOSE_RETRY_MS, triggerPrice, !override);
    }

    private setCloseRetry(symbol: string, waitMs: number, price: number, slOverride: boolean) {
        this.closeRetry.set(symbol, { until: Date.now() + waitMs, price, slOverride });
    }

    /** Cierra la posición en el ledger sin venta (polvo, sin saldo u orden inexistente): sin PnL, con el motivo. */
    private async closeWithoutSale(symbol: string, position: Position, reason: string, openTime?: number) {
        this.activePositions.delete(symbol);
        if (openTime !== undefined) this.lastExitOpenTime.set(symbol, openTime);
        this.closeRetry.delete(symbol);
        console.warn(`[EXIT] ${symbol}: posición ${position.orderId} cerrada en el ledger sin venta. ${reason}`);
        await this.ledgerClose({ order_id: position.orderId, symbol, pnl: null, reason });
        this.notify(`⚠️ <b>CIERRE SIN VENTA: ${symbol}</b>\n${escapeHtml(reason)}`);
    }

    /** Fila PENDING antes de enviar la compra. false si el ledger no la registró (entonces no se compra). */
    private async ledgerPending(symbol: string, intent: BuyIntent): Promise<boolean> {
        try {
            const result = await this.brain.ask('ledger_pending', {
                client_order_id: intent.clientOrderId,
                symbol,
                signal_price: intent.signalPrice,
                take_profit: intent.takeProfit,
                stop_loss: intent.stopLoss
            });
            if (result?.status !== 'logged') throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            return true;
        } catch (error: any) {
            console.error(`[LEDGER] No se pudo registrar la compra pendiente de ${symbol}:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar la compra pendiente de ${symbol}; no se envía la orden.`);
            return false;
        }
    }

    /** La fila PENDING pasa a CANCELLED: la compra no existe en Binance (rechazada, sin ejecutar o no llegó). */
    private async ledgerCancel(symbol: string, clientOrderId: string, reason: string) {
        try {
            const result = await this.brain.ask('ledger_cancel', { client_order_id: clientOrderId, symbol, reason });
            if (result?.status !== 'updated') throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Compra ${clientOrderId} marcada como CANCELLED (${reason}).`);
        } catch (error: any) {
            console.error(`[LEDGER] No se pudo cancelar la compra pendiente ${clientOrderId}:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo marcar como cancelada la compra pendiente de ${symbol} ` +
                `(<code>${escapeHtml(clientOrderId)}</code>).`);
        }
    }

    /** Compra confirmada: con clientOrderId su fila PENDING pasa a OPEN con los fills reales. false si falló. */
    private async ledgerOpen(position: Position, exec: Execution, signalPrice: number | null, clientOrderId?: string): Promise<boolean> {
        try {
            const result = await this.brain.ask('ledger_open', {
                order_id: position.orderId,
                symbol: position.symbol,
                action: "BUY",
                entry_price: position.entryPrice,
                take_profit: position.takeProfit,
                stop_loss: position.stopLoss,
                quantity: position.quantity,
                net_quantity: position.netQuantity,
                entry_quote: position.entryQuote,
                entry_fee_usdt: position.entryFeeQuote,
                entry_fees: exec.fees.detail,
                signal_price: signalPrice,
                client_order_id: clientOrderId ?? null
            });
            if (result?.status !== 'logged') throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Trade logged securely in Python CSV Ledger.`);
            return true;
        } catch (error: any) {
            console.error(`[LEDGER] Failed to log trade to Python ledger:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar la compra de ${position.symbol} (orden ${position.orderId}).`);
            return false;
        }
    }

    private async ledgerClose(payload: Record<string, unknown>) {
        try {
            const result = await this.brain.ask('ledger_close', payload);
            if (result?.status !== 'updated') throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Trade ${payload.order_id} marked as CLOSED.`);
        } catch (error: any) {
            console.error(`[LEDGER] Failed to update Python ledger closure:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar el cierre de la orden ${payload.order_id}.`);
        }
    }

    // Telegram no debe retrasar las órdenes ni dejar promesas rechazadas sin capturar
    private notify(message: string) {
        try {
            Promise.resolve(this.telegram.sendMessage(message)).catch((error: any) =>
                console.error('[TELEGRAM] No se pudo enviar el aviso:', error?.message ?? error));
        } catch (error: any) {
            console.error('[TELEGRAM] No se pudo enviar el aviso:', error?.message ?? error);
        }
    }

    private async currentPrice(symbol: string, fallback: number): Promise<number> {
        try {
            return await this.rest.getPrice(symbol);
        } catch {
            return fallback;
        }
    }

    /**
     * Recupera las posiciones OPEN del ledger y comprueba cada una contra Binance antes de gestionarla:
     * 1. La compra existe y se ejecutó (GET /api/v3/order por orderId).
     * 2. No se vendió ya (ventas posteriores en /myTrades): si se vendió, se registra esa salida real.
     * 3. Hay saldo libre suficiente; si no (o solo polvo), se cierra en el ledger sin venta.
     * Si Binance no responde, la posición queda pendiente de verificar (startupCheckPending): no se vende ni se
     * ajusta su cantidad hasta que la verificación se complete (se reintenta con los siguientes precios). Gestionarla
     * sin verificar perdería del ledger una venta hecha antes del reinicio y el ajuste por saldo podría vender
     * monedas que no son de esta posición.
     */
    public async syncStateFromLedger() {
        // 0. Compras PENDING (el proceso murió con la compra en vuelo): ejecutadas -> se adoptan (su fila pasa a OPEN y
        //    siguen la verificación normal); inexistentes -> CANCELLED; sin respuesta -> se reintentan con los precios.
        const adopted = await this.resolveStartupPendingBuys();

        let openTrades: any;
        try {
            openTrades = await this.brain.ask('sync_positions');
        } catch (error) {
            console.error(`[SYNC] Failed to sync state from ledger.`, error);
            return;
        }
        if (!Array.isArray(openTrades)) {
            console.error(`[SYNC] Respuesta inesperada del ledger:`, openTrades);
            return;
        }
        // Adoptadas cuya fila no se pudo pasar a OPEN: se gestionan igual (se compraron)
        for (const trade of adopted) {
            if (!openTrades.some((t: any) => t.symbol === trade.symbol && Number(t.order_id) === Number(trade.order_id))) {
                openTrades.push(trade);
            }
        }

        // Una posicion por moneda: si el ledger tiene varias OPEN del mismo simbolo se gestiona la mas reciente
        const latest = new Map<string, any>();
        for (const trade of openTrades) {
            const previous = latest.get(trade.symbol);
            if (previous) {
                console.warn(`[SYNC] ${trade.symbol}: varias posiciones OPEN en el ledger; se gestiona solo la más reciente.`);
            }
            if (!previous || Number(trade.timestamp ?? 0) >= Number(previous.timestamp ?? 0)) latest.set(trade.symbol, trade);
        }

        let balances: Map<string, number> | null = null;
        if (latest.size > 0) {
            try {
                balances = await this.rest.getFreeBalances();
            } catch (error: any) {
                console.warn(`[SYNC] No se pudo leer el saldo (${binanceError(error).msg}); saldo sin comprobar.`);
            }
        }

        for (const trade of latest.values()) {
            const position = positionFromLedger(trade);
            try {
                if (!(await this.verifyStartupOrder(position))) continue;
                if (!balances) throw new Error('saldo no disponible');
                if (!(await this.checkStartupBalance(position, balances))) continue;
            } catch (error: any) {
                position.startupCheckPending = true;
                const msg = binanceError(error).msg;
                console.warn(`[SYNC] ${position.symbol}: no se pudo verificar la posición ${position.orderId} en Binance ` +
                    `(${msg}); no se gestiona hasta verificarla (se reintenta con los próximos precios).`);
                this.notify(`⚠️ <b>POSICIÓN SIN VERIFICAR: ${position.symbol}</b>\nBinance no respondió al arrancar ` +
                    `(<i>${escapeHtml(msg)}</i>). No se venderá hasta poder verificarla; se reintenta con cada precio.`);
            }
            this.activePositions.set(position.symbol, position);
        }
        if (this.activePositions.size > 0) {
            console.log(`[SYNC] Synced ${this.activePositions.size} active position(s) from Python Ledger.`);
        }
    }

    /**
     * Resuelve las compras PENDING del ledger por su client_order_id. Devuelve, como filas OPEN, las adoptadas cuya
     * fila no se pudo actualizar (las demás ya vuelven en sync_positions).
     */
    private async resolveStartupPendingBuys(): Promise<any[]> {
        let pendingRows: any;
        try {
            pendingRows = await this.brain.ask('sync_pending');
        } catch (error: any) {
            console.error(`[SYNC] No se pudieron leer las compras pendientes del ledger:`, error?.message ?? error);
            return [];
        }
        if (!Array.isArray(pendingRows)) return [];
        // Una consulta por fila, todas a la vez y sin esperas: lo que no se resuelva en el acto ("no existe" por ahora o
        // sin respuesta) se sigue consultando en segundo plano con los precios, sin retrasar la conexión del WebSocket.
        const adopted = await Promise.all(pendingRows.map(row => this.resolveStartupPendingRow(row)));
        return adopted.filter(row => row !== null);
    }

    /** Fila PENDING del arranque. Devuelve la fila OPEN de una compra adoptada cuyo ledger no se pudo actualizar. */
    private async resolveStartupPendingRow(row: any): Promise<any | null> {
        const symbol = String(row.symbol);
        const intent: BuyIntent = {
            clientOrderId: String(row.client_order_id ?? ''),
            signalPrice: Number.isFinite(row.signal_price) ? row.signal_price : null,
            takeProfit: Number.isFinite(row.take_profit) ? row.take_profit : Infinity,
            stopLoss: Number.isFinite(row.stop_loss) ? row.stop_loss : -Infinity
        };
        if (!intent.clientOrderId) {
            console.warn(`[SYNC] ${symbol}: fila PENDING sin client_order_id; no se puede consultar.`);
            return null;
        }
        let exec: Execution | null | undefined;   // undefined: Binance no respondió
        try {
            exec = await this.rest.lookupOrder(symbol, intent.clientOrderId);
        } catch (error: any) {
            console.warn(`[SYNC] ${symbol}: la compra pendiente ${intent.clientOrderId} no se pudo consultar ` +
                `(${binanceError(error).msg}); se reintenta con los próximos precios.`);
        }
        if (exec === undefined || exec === null) {
            // Compra dudosa: queda PENDING, la moneda no abre otra compra y se resuelve con los precios (pendingEntries
            // los guarda para revisar el TP/SL si se adopta). "No existe": espera creciente, puede aparecer tarde.
            const notFound = exec === null ? 1 : 0;
            this.unresolvedBuys.set(symbol, {
                ...intent, notFound, retryAt: Date.now() + (notFound ? LATE_ORDER_RECHECKS_MS[0]! : CLOSE_RETRY_MS)
            });
            if (!this.pendingEntries.has(symbol)) this.pendingEntries.set(symbol, []);
            this.notify(`⚠️ <b>COMPRA PENDIENTE SIN VERIFICAR: ${symbol}</b>\n` +
                (notFound ? 'Binance aún no la muestra' : 'Binance no respondió al arrancar') +
                `; se consulta <code>${escapeHtml(intent.clientOrderId)}</code> con los próximos precios.`);
            return null;
        }
        if (!(exec.executedQty > 0)) {
            await this.ledgerCancel(symbol, intent.clientOrderId, `SIN EJECUTAR (${exec.status}, detectado al arrancar)`);
            return null;
        }
        const position = this.positionFromExecution(symbol, exec, intent);
        console.warn(`[SYNC] ${symbol}: la compra pendiente ${intent.clientOrderId} se ejecutó antes del reinicio; se adopta.`);
        this.notify(`🔁 <b>COMPRA RECUPERADA: ${symbol}</b>\nLa orden <code>${escapeHtml(intent.clientOrderId)}</code> se ` +
            `ejecutó antes del reinicio (${formatQty(exec.executedQty)} a $${formatPrice(exec.avgPrice)}); se gestiona como posición abierta.`);
        if (await this.ledgerOpen(position, exec, intent.signalPrice, intent.clientOrderId)) return null;
        return {
            order_id: position.orderId, symbol, entry_price: position.entryPrice, take_profit: position.takeProfit,
            stop_loss: position.stopLoss, quantity: position.quantity, net_quantity: position.netQuantity,
            entry_quote: position.entryQuote, entry_fee_usdt: position.entryFeeQuote, timestamp: row.timestamp ?? Date.now()
        };
    }

    /**
     * Repite la verificación del arranque que falló (como mucho cada CLOSE_RETRY_MS). true si la posición sigue
     * abierta y ya se puede gestionar con este precio; false si sigue sin verificar o quedó cerrada en el ledger.
     */
    private async retryStartupCheck(symbol: string, position: Position): Promise<boolean> {
        if (Date.now() < (this.startupCheckRetryAt.get(symbol) ?? 0)) return false;
        this.closing.add(symbol);   // ningún otro precio toca la posición mientras se verifica
        try {
            if (!(await this.verifyStartupOrder(position))) return false;
            if (!(await this.checkStartupBalance(position, await this.rest.getFreeBalances()))) return false;
            delete position.startupCheckPending;
            this.startupCheckRetryAt.delete(symbol);
            console.log(`[SYNC] ${symbol}: posición ${position.orderId} verificada en Binance; se gestiona desde ahora.`);
            return this.activePositions.get(symbol) === position;
        } catch (error: any) {
            this.startupCheckRetryAt.set(symbol, Date.now() + CLOSE_RETRY_MS);
            console.warn(`[SYNC] ${symbol}: la posición ${position.orderId} sigue sin verificar (${binanceError(error).msg}).`);
            return false;
        } finally {
            this.closing.delete(symbol);
        }
    }

    /** La compra existe y se ejecutó, y no se vendió ya. false si la posición quedó cerrada en el ledger. */
    private async verifyStartupOrder(position: Position): Promise<boolean> {
        const { symbol } = position;
        const order = await this.rest.getOrder(symbol, position.orderId);
        if (order === null) {
            await this.closeWithoutSale(symbol, position, `ORDEN INEXISTENTE al arrancar: Binance no tiene la compra ${position.orderId}`);
            return false;
        }
        if (!(parseFloat(order.executedQty) > 0)) {
            await this.closeWithoutSale(symbol, position,
                `COMPRA SIN EJECUTAR al arrancar: la orden ${position.orderId} está ${order.status} sin nada ejecutado`);
            return false;
        }

        // Ventas posteriores a la compra que el ledger no registró (p. ej. el bot se cortó tras vender)
        const buyTrades = await this.rest.getMyTrades(symbol, { orderId: position.orderId });
        if (buyTrades.length === 0) return true;
        const lastBuyTradeId = Math.max(...buyTrades.map(t => Number(t.id)));
        const later = await this.rest.getMyTrades(symbol, { fromId: lastBuyTradeId + 1 });
        const f = await this.rest.getSymbolFilters(symbol);
        const sellable = parseFloat(sellableQuantity(position.netQuantity, f));
        const sells: any[] = [];
        let sold = 0;
        for (const trade of later) {
            if (trade.isBuyer) {
                // Otra compra del mismo par (manual u otra posición): las ventas que siguen ya no son seguro de esta
                console.warn(`[SYNC] ${symbol}: hay otra compra (orden ${trade.orderId}) después de la ${position.orderId}; ` +
                    `solo se cuentan las ventas anteriores a ella.`);
                break;
            }
            if (sold >= sellable) break;
            sells.push(trade);
            sold += parseFloat(trade.qty);
        }
        if (sells.length === 0) return true;

        position.exitParts = [await this.rest.tradesToExecution(symbol, sells, { orderId: sells[0].orderId })];
        const remaining = parseFloat(floorToStep(position.netQuantity - soldQuantity(position.exitParts), f.stepSize));
        const price = await this.currentPrice(symbol, position.entryPrice);
        if (await this.isSellable(symbol, remaining, price, f)) {
            // La salida ya estaba en marcha antes del reinicio: se completa con el primer precio
            console.warn(`[SYNC] ${symbol}: ya se vendieron ${sold} ${f.baseAsset} de la posición; se vende el resto (${remaining}).`);
            position.exitReason = 'SALIDA EN CURSO (iniciada antes de arrancar)';
            return true;
        }
        await this.finishClose(symbol, position, f, 'VENTA YA EJECUTADA (detectada al arrancar)', { note: '', noSaleReason: '' }, null);
        return false;
    }

    private async checkStartupBalance(position: Position, balances: Map<string, number>): Promise<boolean> {
        const { symbol } = position;
        const f = await this.rest.getSymbolFilters(symbol);
        const free = balances.get(f.baseAsset) ?? 0;
        const sold = soldQuantity(position.exitParts);
        const needed = parseFloat(sellableQuantity(position.netQuantity - sold, f));
        const available = parseFloat(sellableQuantity(position.netQuantity - sold, f, free));
        const price = await this.currentPrice(symbol, position.entryPrice);
        if (await this.isSellable(symbol, available, price, f)) {
            if (available < needed) {
                console.warn(`[SYNC] ${symbol}: saldo libre ${free} ${f.baseAsset} menor que la posición (${needed}); se venderá ${available}.`);
                position.netQuantity = sold + available;
            }
            return true;
        }
        const reason = free < needed
            ? `SIN SALDO al arrancar: libre ${formatQty(free)} ${f.baseAsset}, la posición necesita ${needed}`
            : `POLVO al arrancar: ${formatQty(position.netQuantity - sold)} ${f.baseAsset} por debajo del mínimo de Binance`;
        console.warn(`[SYNC] ${symbol}: ${reason}. Se cierra en el ledger.`);
        // Con tramos ya vendidos se registra esa salida real; si no, cierre sin venta
        await this.finishClose(symbol, position, f, 'VENTA YA EJECUTADA (detectada al arrancar)',
            { note: ` (resto: ${reason})`, noSaleReason: reason, heldQty: Math.min(free, Math.max(0, position.netQuantity - sold)) },
            null);
        return false;
    }

    public close() {
        this.stopped = true;
        if (this.watchdog) clearInterval(this.watchdog);
        this.watchdog = null;
        try {
            this.ws?.close();
        } catch (error: any) {
            console.error('[WS] Error al cerrar:', error?.message ?? error);
        }
    }
}
