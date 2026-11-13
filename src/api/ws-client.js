"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.BinanceWSClient = exports.STALE_CHECK_MS = exports.STALE_SOCKET_MS = exports.NOTIONAL_MARGIN = exports.LATE_BUY_CANCEL_REASON = exports.LATE_ORDER_RECHECKS_MS = void 0;
exports.positionFromLedger = positionFromLedger;
const ws_1 = __importDefault(require("ws"));
const rest_client_1 = require("./rest-client");
const zmq_client_1 = require("./zmq-client");
const telegram_client_1 = require("./telegram-client");
const env_1 = require("../config/env");
const execution_1 = require("./execution");
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
exports.LATE_ORDER_RECHECKS_MS = [10000, 30000, 90000];
exports.LATE_BUY_CANCEL_REASON = 'NO LLEGÓ A BINANCE (no apareció en ~2 min de consultas)';
// Margen sobre minNotional al decidir si algo es vendible: Binance valora las MARKET con el precio medio reciente.
exports.NOTIONAL_MARGIN = 0.01;
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
exports.STALE_SOCKET_MS = 120000;
exports.STALE_CHECK_MS = 15000;
// Colchón de Break Even para cubrir comisiones de ida y vuelta al cerrar TP1 parcial (0.20%)
const DEFAULT_BE_BUFFER_PCT = 0.002;
/** Posición a partir de una fila OPEN del ledger (las filas antiguas no tienen datos de ejecución). */
function positionFromLedger(trade) {
    const num = (value, fallback) => value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? fallback : Number(value);
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
class BinanceWSClient {
    ws = null;
    baseUrl = `${env_1.config.WS_URL}/stream?streams=`;
    tradeQuoteUsdt;
    rest;
    brain;
    telegram;
    createSocket;
    sleep;
    activePositions = new Map();
    // open_time de la ultima vela cerrada enviada a Python, por simbolo (una evaluacion por vela)
    lastClosedOpenTime = new Map();
    // open_time de la vela en la que se cerro la ultima posicion: la senal de esa misma vela no se opera
    lastExitOpenTime = new Map();
    orderCooldownUntil = new Map();
    // Simbolos con una orden de venta en curso: evita un segundo SELL mientras se espera al REST
    closing = new Set();
    // Simbolos con una compra en curso y los precios vistos mientras tanto: al registrar la posicion se
    // comprueban contra TP/SL (el precio pudo tocarlos antes de que la posicion existiera)
    pendingEntries = new Map();
    // Pausa tras un fallo de venta, por simbolo
    closeRetry = new Map();
    // Ventas sin confirmar ya avisadas por Telegram (un aviso por orden)
    notifiedUnknownSells = new Set();
    // Próximo reintento de la verificación del arranque que falló, por símbolo
    startupCheckRetryAt = new Map();
    // Compras PENDING sin resolver (estado desconocido), por símbolo
    unresolvedBuys = new Map();
    url;
    stopped = false;
    reconnectDelayMs = RECONNECT_MIN_MS;
    // Último mensaje, ping o pong del WebSocket (vigilancia de conexión muerta)
    lastSocketActivityAt = 0;
    watchdog = null;
    /**
     * @param tradeQuoteUsdt USDT por operación por defecto. Lo da Python en el handshake (optimize.NOTIONAL_USDT).
     *                       Si una estrategia personalizada envía `signal.quote_usdt`, se usa ese monto dinámico.
     */
    constructor(roster, tradeQuoteUsdt, deps = {}) {
        if (!Number.isFinite(tradeQuoteUsdt) || tradeQuoteUsdt <= 0) {
            throw new Error(`Tamaño por operación no válido: ${tradeQuoteUsdt}`);
        }
        this.tradeQuoteUsdt = tradeQuoteUsdt;
        this.rest = deps.rest ?? new rest_client_1.BinanceRestClient();
        this.brain = deps.brain ?? zmq_client_1.brain;
        this.telegram = deps.telegram ?? new telegram_client_1.TelegramClient();
        this.createSocket = deps.createSocket ?? ((url) => new ws_1.default(url));
        this.sleep = deps.sleep ?? (ms => new Promise(resolve => setTimeout(resolve, ms)));
        // Velas de la temporalidad que evalua la estrategia: la da Python en el handshake (config.KLINE_INTERVAL)
        const streams = roster.map(symbol => `${symbol.toLowerCase()}@kline_${deps.klineInterval ?? '15m'}`).join('/');
        this.url = `${this.baseUrl}${streams}`;
    }
    /** Recupera las posiciones del ledger y despues abre el WebSocket: ningun precio llega sin ellas. */
    async start() {
        await this.syncStateFromLedger();
        if (this.stopped)
            return;
        this.ws = this.connect();
        if (!this.watchdog) {
            this.watchdog = setInterval(() => this.checkSocketAlive(), exports.STALE_CHECK_MS);
            this.watchdog.unref?.(); // no mantiene vivo el proceso por sí solo
        }
    }
    /** Si el WebSocket lleva STALE_SOCKET_MS sin mensajes ni pings, se corta: el evento 'close' reconecta. */
    checkSocketAlive() {
        if (this.stopped || !this.ws)
            return;
        const idle = Date.now() - this.lastSocketActivityAt;
        if (idle < exports.STALE_SOCKET_MS)
            return;
        console.warn(`[WS] ${Math.round(idle / 1000)} s sin datos ni pings de Binance: se fuerza la reconexión.`);
        this.lastSocketActivityAt = Date.now();
        try {
            if (this.ws.terminate)
                this.ws.terminate();
            else
                this.ws.close();
        }
        catch (error) {
            console.error('[WS] No se pudo cortar la conexión muerta:', error?.message ?? error);
        }
    }
    getPosition(symbol) {
        return this.activePositions.get(symbol);
    }
    // Las velas que falten tras una reconexion las recupera Python (fill_gap) con la siguiente vela cerrada.
    connect() {
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
        ws.on('message', async (data) => {
            alive();
            try {
                const parsedData = JSON.parse(data.toString());
                if (parsedData.data && parsedData.data.e === 'kline') {
                    await this.handleMarketData(parsedData.data);
                }
            }
            catch (err) {
                console.error('[WS] Error procesando mensaje:', err?.message ?? err);
            }
        });
        ws.on('error', (error) => console.error('[WS] Error:', error?.message ?? error));
        ws.on('close', () => {
            console.log('[WS] Connection closed.');
            this.scheduleReconnect();
        });
        return ws;
    }
    scheduleReconnect() {
        if (this.stopped)
            return;
        const delay = this.reconnectDelayMs;
        this.reconnectDelayMs = Math.min(delay * 2, RECONNECT_MAX_MS);
        console.log(`[WS] Reconnecting in ${delay / 1000}s...`);
        setTimeout(() => {
            if (this.stopped)
                return;
            try {
                this.ws = this.connect();
            }
            catch (error) {
                // Un fallo al crear el socket no puede escapar del temporizador: se reintenta más tarde
                console.error('[WS] No se pudo reconectar:', error?.message ?? error);
                this.scheduleReconnect();
            }
        }, delay);
    }
    async handleMarketData(data) {
        const symbol = data.s;
        const kline = data.k;
        const currentPrice = parseFloat(kline.c);
        const openTime = Number(kline.t);
        // 0. Con una compra en curso se guardan los precios: se revisan contra TP/SL al registrar la posicion.
        this.pendingEntries.get(symbol)?.push({ price: currentPrice, openTime });
        //    Una compra PENDING sin resolver se vuelve a consultar (como mucho cada pocos segundos).
        const unresolved = this.unresolvedBuys.get(symbol);
        if (unresolved)
            await this.retryUnresolvedBuy(symbol, unresolved);
        // 1. Cada actualizacion (vela cerrada o no) vigila el TP/SL de la posicion abierta con el precio actual.
        if (this.activePositions.has(symbol)) {
            await this.manageExistingPosition(symbol, currentPrice, openTime);
        }
        // 2. La estrategia solo ve velas CERRADAS (k.x), una vez por vela y simbolo. Tambien con posicion
        //    abierta, para que su ventana no se congele y pueda emitir PARTIAL_CLOSE / UPDATE_SL / FULL_CLOSE.
        if (kline.x !== true)
            return;
        const lastSent = this.lastClosedOpenTime.get(symbol);
        if (lastSent !== undefined && openTime <= lastSent)
            return;
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
    async manageExistingPosition(symbol, currentPrice, openTime) {
        if (this.closing.has(symbol))
            return;
        const position = this.activePositions.get(symbol);
        if (!position)
            return;
        if (position.startupCheckPending && !(await this.retryStartupCheck(symbol, position)))
            return;
        const hitTp = currentPrice >= position.takeProfit;
        const hitSl = currentPrice <= position.stopLoss;
        // Una salida ya decidida (venta fallida o a medias) se completa con cualquier precio, con su motivo y nivel
        if (position.exitReason === undefined && !hitTp && !hitSl)
            return;
        // Si toca el TP1 en modo cierres parciales (50% en TP1 + paso a Break Even) y no es un cierre total en curso:
        if (position.exitReason === undefined &&
            hitTp &&
            !hitSl &&
            position.partialTp1Ratio &&
            position.partialTp1Ratio > 0 &&
            position.partialTp1Ratio < 1 &&
            !position.tp1PartialDone) {
            const bePrice = Number((position.entryPrice * (1 + DEFAULT_BE_BUFFER_PCT)).toFixed(8));
            const newSl = Math.max(position.stopLoss, bePrice);
            console.log(`\n[PARTIAL TP1 HIT] ${symbol} @ ${currentPrice}. Selling ${position.partialTp1Ratio * 100}% & moving SL to BE (${newSl}).`);
            await this.executePartialClose(symbol, position, position.partialTp1Ratio, currentPrice, "TP1 PARCIAL (50%) ASEGURADO + SL A BREAK EVEN ✅", newSl, openTime);
            return;
        }
        // Pausa tras un fallo de venta: solo se adelanta una vez, si el precio cae aun mas bajo el SL
        let override = false;
        const retry = this.closeRetry.get(symbol);
        if (retry && Date.now() < retry.until) {
            if (!(hitSl && retry.slOverride && currentPrice < retry.price))
                return;
            retry.slOverride = false;
            override = true;
            console.log(`[EXIT] ${symbol}: el precio sigue cayendo bajo el SL (${currentPrice} < ${retry.price}); reintento inmediato.`);
        }
        // Modificamos para enviar el motivo exacto del cierre
        if (position.exitReason !== undefined) {
            console.log(`\n[EXIT RETRY] ${symbol} @ ${currentPrice}: se completa la salida (${position.exitReason}).`);
            await this.closePosition(symbol, position, position.exitTrigger ?? currentPrice, position.exitReason, openTime, override);
        }
        else if (hitTp) {
            console.log(`\n[TAKE PROFIT HIT] ${symbol} @ ${currentPrice}. Exiting trade.`);
            await this.closePosition(symbol, position, currentPrice, "TAKE PROFIT ✅", openTime, override);
        }
        else {
            console.log(`\n[STOP LOSS HIT] ${symbol} @ ${currentPrice}. Cutting losses.`);
            await this.closePosition(symbol, position, currentPrice, "STOP LOSS ⚠️", openTime, override);
        }
    }
    async evaluateNewTrade(symbol, marketData, timestamp) {
        let signal;
        try {
            signal = await this.brain.ask('evaluate', {
                symbol: symbol,
                market_data: marketData,
                timestamp: timestamp
            });
        }
        catch (error) {
            console.error(`[BRAIN] ${symbol}: no se pudo evaluar la vela:`, error?.message ?? error);
            return;
        }
        if (!signal || !signal.action)
            return;
        // 1. Señales de gestión dinámica sobre una posición ya abierta (CustomFractalStrategy / PositionManager)
        const existing = this.activePositions.get(symbol);
        if (existing && !this.closing.has(symbol) && !existing.startupCheckPending) {
            if (signal.action === 'UPDATE_SL' && Number.isFinite(Number(signal.new_stop_loss))) {
                const newSl = Number(signal.new_stop_loss);
                if (newSl > existing.stopLoss) {
                    existing.stopLoss = newSl;
                    await this.ledgerUpdateSl(symbol, existing.orderId, newSl);
                    console.log(`[TRAILING SL] ${symbol}: Stop Loss actualizado a $${newSl} (${signal.reason ?? 'Trailing'})`);
                    this.notify(`🛡️ <b>AJUSTE DE STOP LOSS: ${symbol}</b>\n` +
                        `🔹 <b>Nuevo SL:</b> $${newSl}\n` +
                        `ℹ️ <i>${(0, telegram_client_1.escapeHtml)(String(signal.reason ?? 'Trailing Stop'))}</i>`);
                }
                return;
            }
            if (signal.action === 'PARTIAL_CLOSE') {
                const ratio = Number(signal.close_ratio_of_remaining ?? 0.5);
                const newSl = Number.isFinite(Number(signal.new_stop_loss)) ? Number(signal.new_stop_loss) : undefined;
                if (ratio > 0 && ratio < 1) {
                    await this.executePartialClose(symbol, existing, ratio, marketData.close, String(signal.reason ?? 'CIERRE PARCIAL ✅'), newSl, marketData.open_time);
                }
                return;
            }
            if (signal.action === 'FULL_CLOSE') {
                const reason = String(signal.reason ?? 'CIERRE POR ESTRUCTURA / TIME-STOP ✅');
                console.log(`\n[BRAIN EXIT] ${symbol} @ ${marketData.close}: ${reason}`);
                await this.closePosition(symbol, existing, marketData.close, reason, marketData.open_time);
                return;
            }
        }
        // 2. Señal de apertura de nueva posición (BUY)
        if (signal.action === 'BUY' && this.canOpenPosition(symbol, marketData.open_time)) {
            // Sin niveles numéricos la posición nunca se cerraría
            if (!Number.isFinite(signal.take_profit) || !Number.isFinite(signal.stop_loss)) {
                console.error(`[SIGNAL] ${symbol}: BUY sin take_profit/stop_loss numéricos, no se opera.`, signal);
                return;
            }
            await this.openPosition(symbol, signal);
        }
    }
    /**
     * Ejecuta una venta parcial a mercado (ej. 50% en TP1 o 50% del remanente en TP2 por cruce de EMA 50 1H).
     * El tramo vendido se acumula en `position.exitParts` para que el cierre final calcule el PnL neto total exacto.
     */
    async executePartialClose(symbol, position, ratioOfRemaining, triggerPrice, reason, newStopLoss, openTime) {
        if (this.closing.has(symbol))
            return;
        this.closing.add(symbol);
        const parts = position.exitParts ?? (position.exitParts = []);
        try {
            const filters = await this.rest.getSymbolFilters(symbol);
            const currentlyRemaining = Math.max(0, position.netQuantity - (0, execution_1.soldQuantity)(parts));
            const split = (0, execution_1.splitPartialQuantity)(currentlyRemaining, ratioOfRemaining, triggerPrice, filters, exports.NOTIONAL_MARGIN);
            if (!split.canSplit || !(await this.isSellable(symbol, split.sellQtyNum, triggerPrice, filters))) {
                console.warn(`[PARTIAL] ${symbol}: tramo (${split.sellQty}) o remanente (${split.remainingAfterNum}) bajo el mínimo; se omite fraccionamiento.`);
                position.tp1PartialDone = true;
                position.takeProfit = Infinity;
                if (newStopLoss !== undefined && newStopLoss > position.stopLoss) {
                    position.stopLoss = newStopLoss;
                    await this.ledgerUpdateSl(symbol, position.orderId, newStopLoss);
                }
                return;
            }
            const exec = await this.rest.marketSell(symbol, split.sellQty);
            if (exec.executedQty > 0) {
                parts.push(exec);
            }
            position.tp1PartialDone = true;
            position.takeProfit = Infinity;
            if (newStopLoss !== undefined && newStopLoss > position.stopLoss) {
                position.stopLoss = newStopLoss;
            }
            const mergedSoFar = (0, execution_1.mergeExecutions)(parts);
            const newRemainingNet = Math.max(0, position.netQuantity - mergedSoFar.executedQty);
            const partPnl = (0, execution_1.partialNetPnl)(position, position.netQuantity, exec);
            await this.ledgerPartial(symbol, position.orderId, position.stopLoss, mergedSoFar.executedQty, mergedSoFar.quoteQty, mergedSoFar.fees.totalQuote);
            const px = (value) => (0, execution_1.formatPrice)(value, filters.tickSize);
            console.log(`[PARTIAL FILLED] ${symbol}: vendido ${exec.executedQty} @ $${px(exec.avgPrice)} (${(0, execution_1.formatUsdt)(partPnl)}) | Restante: ${(0, execution_1.formatQty)(newRemainingNet)} | SL: $${px(position.stopLoss)}`);
            this.notify(`💰 <b>${(0, telegram_client_1.escapeHtml)(reason)}</b>\n` +
                `🔹 <b>Moneda:</b> ${symbol}\n` +
                `📦 <b>Vendido:</b> ${(0, execution_1.formatQty)(exec.executedQty)} @ $${px(exec.avgPrice)}\n` +
                `💵 <b>PnL tramo:</b> ${(0, execution_1.formatUsdt)(partPnl)}\n` +
                `📊 <b>Restante en posición:</b> ${(0, execution_1.formatQty)(newRemainingNet)} ${filters.baseAsset}\n` +
                `🛡️ <b>Stop Loss actual:</b> $${px(position.stopLoss)}`);
        }
        catch (error) {
            console.error(`[PARTIAL ERROR] ${symbol}: no se pudo ejecutar el cierre parcial:`, (0, rest_client_1.binanceError)(error).msg);
        }
        finally {
            this.closing.delete(symbol);
        }
    }
    // Una posicion por moneda, como el backtest: el BUY se ignora con posicion abierta (o compra en curso), en la
    // misma vela en la que se cerro la anterior (la senal debe ser posterior a la vela de salida) y durante el
    // cooldown por error.
    canOpenPosition(symbol, openTime) {
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
     * Compra MARKET por quoteUsdt (el dinámico `signal.quote_usdt` de RiskManager si viene, o `this.tradeQuoteUsdt`).
     * Antes de enviarla se escribe en el ledger una fila PENDING con su newClientOrderId: si el proceso muere entre
     * la ejecución y el registro, al arrancar se encuentra en Binance.
     */
    async openPosition(symbol, signal) {
        console.log(`\n=========================================`);
        console.log(`[NEW TRADE] Python signal for ${symbol}`);
        this.pendingEntries.set(symbol, []);
        const dynamicQuote = Number(signal.quote_usdt);
        const orderQuoteUsdt = Number.isFinite(dynamicQuote) && dynamicQuote > 0 ? dynamicQuote : this.tradeQuoteUsdt;
        const intent = {
            clientOrderId: (0, rest_client_1.newClientOrderId)('BUY'),
            signalPrice: Number.isFinite(signal.entry_price) ? signal.entry_price : null,
            takeProfit: signal.take_profit,
            stopLoss: signal.stop_loss,
            quoteUsdt: orderQuoteUsdt,
            exitPlan: signal.exit_plan
        };
        let filters;
        try {
            filters = await this.rest.getSymbolFilters(symbol);
        }
        catch (error) {
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
        let exec;
        let adopted = false;
        try {
            exec = await this.rest.marketBuy(symbol, orderQuoteUsdt, signal.entry_price, intent.clientOrderId);
        }
        catch (error) {
            if (!(error instanceof rest_client_1.OrderStatusUnknownError || error instanceof rest_client_1.OrderNotFoundError)) {
                // Rechazada (4xx) o no enviada: la orden no existe en Binance
                this.pendingEntries.delete(symbol);
                await this.ledgerCancel(symbol, intent.clientOrderId, `RECHAZADA: ${(0, rest_client_1.binanceError)(error).msg}`);
                this.handleOrderError(symbol, error);
                return;
            }
            console.warn(`[ORDER UNKNOWN] ${symbol}: compra ${intent.clientOrderId} sin confirmar; se consulta en Binance...`);
            let outcome = null; // OrderNotFoundError: Binance ya dijo "no existe"
            if (error instanceof rest_client_1.OrderStatusUnknownError) {
                try {
                    outcome = await this.resolveUnknownOrder(symbol, intent.clientOrderId);
                }
                catch {
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
                    retryAt: Date.now() + (notFound ? exports.LATE_ORDER_RECHECKS_MS[0] : CLOSE_RETRY_MS)
                });
                this.handleOrderError(symbol, new rest_client_1.OrderStatusUnknownError(symbol, intent.clientOrderId, error));
                return;
            }
            exec = outcome;
            adopted = true;
        }
        if (!(exec.executedQty > 0)) {
            this.pendingEntries.delete(symbol);
            await this.ledgerCancel(symbol, intent.clientOrderId, `SIN EJECUTAR (${exec.status})`);
            console.log(`[ORDER FAILED] ${symbol}: la compra MARKET no se ejecutó (status ${exec.status}).`);
            this.notify(`❌ <b>ERROR DE ORDEN: ${symbol}</b>\nLa compra a mercado no se ejecutó (<i>${(0, telegram_client_1.escapeHtml)(exec.status)}</i>).`);
            this.orderCooldownUntil.set(symbol, Date.now() + ORDER_ERROR_COOLDOWN_MS);
            return;
        }
        await this.registerEntry(symbol, exec, intent, filters, adopted);
    }
    /** Posición a partir de lo ejecutado de verdad y de los niveles absolutos de la estrategia. */
    positionFromExecution(symbol, exec, intent) {
        const pos = {
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
        if (intent.exitPlan && intent.exitPlan.mode === 'SWING_PARCIALES') {
            pos.partialTp1Ratio = Number(intent.exitPlan.tp1_ratio ?? 0.5);
            pos.tp1PartialDone = false;
        }
        return pos;
    }
    /**
     * Registra una compra ejecutada: ledger (la fila PENDING pasa a OPEN), posición activa, aviso y revisión de los
     * precios vistos mientras se compraba (carrera compra/TP-SL).
     */
    async registerEntry(symbol, exec, intent, filters, adopted) {
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
        const px = (value) => (0, execution_1.formatPrice)(value, filters.tickSize);
        const signalText = intent.signalPrice !== null ? px(intent.signalPrice) : '?';
        console.log(`[ENTRY FILLED] ${symbol}: ${exec.executedQty} @ ${px(exec.avgPrice)} (señal ${signalText}), ` +
            `${exec.quoteQty.toFixed(4)} USDT, comisión ${exec.fees.detail || '0'}${adopted ? ' (confirmada tras consultar la orden)' : ''}`);
        this.notify(`🚀 <b>NUEVA COMPRA: ${symbol}</b>\n` +
            `🔹 <b>Precio:</b> $${px(exec.avgPrice)} (señal $${signalText})\n` +
            `📦 <b>Cantidad:</b> ${(0, execution_1.formatQty)(exec.executedQty)} (${exec.quoteQty.toFixed(2)} USDT)\n` +
            `💸 <b>Comisión:</b> ${exec.fees.totalQuote.toFixed(4)} USDT${exec.fees.detail ? ` (${exec.fees.detail})` : ''}\n` +
            `🎯 <b>Target:</b> $${px(position.takeProfit)}\n` +
            `🛡️ <b>Riesgo:</b> $${px(position.stopLoss)}` +
            (adopted ? `\n<i>Orden confirmada tras consultarla en Binance.</i>` : ''));
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
    async retryUnresolvedBuy(symbol, pending) {
        if (pending.inFlight || Date.now() < pending.retryAt)
            return;
        pending.inFlight = true;
        try {
            let exec;
            let filters;
            try {
                exec = await this.rest.lookupOrder(symbol, pending.clientOrderId);
                filters = await this.rest.getSymbolFilters(symbol);
            }
            catch (error) {
                pending.retryAt = Date.now() + CLOSE_RETRY_MS;
                console.warn(`[ORDER UNKNOWN] ${symbol}: la compra ${pending.clientOrderId} sigue sin confirmar (${(0, rest_client_1.binanceError)(error).msg}).`);
                return;
            }
            if (exec === null) {
                pending.notFound += 1;
                if (pending.notFound <= exports.LATE_ORDER_RECHECKS_MS.length) {
                    const waitMs = exports.LATE_ORDER_RECHECKS_MS[pending.notFound - 1];
                    pending.retryAt = Date.now() + waitMs;
                    console.warn(`[ORDER UNKNOWN] ${symbol}: Binance aún no tiene la compra ${pending.clientOrderId} ` +
                        `(${pending.notFound}.ª vez); se vuelve a consultar en ${waitMs / 1000} s.`);
                    return;
                }
                this.unresolvedBuys.delete(symbol);
                this.pendingEntries.delete(symbol);
                await this.ledgerCancel(symbol, pending.clientOrderId, exports.LATE_BUY_CANCEL_REASON);
                this.notify(`ℹ️ <b>COMPRA DESCARTADA: ${symbol}</b>\nLa orden <code>${(0, telegram_client_1.escapeHtml)(pending.clientOrderId)}</code> ` +
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
            if (!this.pendingEntries.has(symbol))
                this.pendingEntries.set(symbol, []);
            console.log(`[ORDER UNKNOWN] ${symbol}: la compra ${pending.clientOrderId} sí se ejecutó; se adopta la posición.`);
            await this.registerEntry(symbol, exec, pending, filters, true);
        }
        finally {
            pending.inFlight = false;
        }
    }
    handleOrderError(symbol, error) {
        if (error instanceof rest_client_1.OrderStatusUnknownError) {
            console.error(`[ORDER UNKNOWN] ${symbol}: ${error.message}`);
            this.notify(`❗ <b>COMPRA SIN CONFIRMAR: ${symbol}</b>\nTras varias consultas no se pudo saber si la orden ` +
                `<code>${(0, telegram_client_1.escapeHtml)(error.clientOrderId)}</code> se ejecutó. Queda PENDIENTE en el ledger y se sigue ` +
                `consultando con cada precio: si se ejecutó, se adopta la posición; si no existe, se cancela.`);
        }
        else {
            const msg = (0, rest_client_1.binanceError)(error).msg;
            console.log(`[ORDER FAILED] ${symbol}:`, msg);
            // Notificación de error crítico en ejecución
            this.notify(`❌ <b>ERROR DE ORDEN: ${symbol}</b>\nNo se abrió la posición: <i>${(0, telegram_client_1.escapeHtml)(msg)}</i>`);
        }
        console.log(`[SYSTEM] Applying 60-second cooldown to ${symbol}...`);
        this.orderCooldownUntil.set(symbol, Date.now() + ORDER_ERROR_COOLDOWN_MS);
    }
    /**
     * Orden con estado desconocido: se consulta por newClientOrderId hasta UNKNOWN_ORDER_LOOKUPS veces.
     * Devuelve la ejecución real, null si Binance no la tiene, o lanza OrderStatusUnknownError.
     */
    async resolveUnknownOrder(symbol, clientOrderId) {
        let lastError = null;
        for (let attempt = 0; attempt < UNKNOWN_ORDER_LOOKUPS; attempt++) {
            if (attempt > 0)
                await this.sleep(UNKNOWN_ORDER_WAIT_MS * attempt);
            try {
                return await this.rest.lookupOrder(symbol, clientOrderId);
            }
            catch (error) {
                lastError = error;
                console.warn(`[ORDER UNKNOWN] ${symbol}: consulta ${attempt + 1}/${UNKNOWN_ORDER_LOOKUPS} de ${clientOrderId} sin respuesta.`);
            }
        }
        throw new rest_client_1.OrderStatusUnknownError(symbol, clientOrderId, lastError);
    }
    async closePosition(symbol, position, triggerPrice, reason, openTime, override = false) {
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
                    if (position.sellNotFound <= exports.LATE_ORDER_RECHECKS_MS.length) {
                        throw new rest_client_1.OrderNotFoundError(symbol, position.unconfirmedSellId, new Error('sigue sin aparecer'));
                    }
                    console.warn(`[EXIT] ${symbol}: la venta ${position.unconfirmedSellId} no apareció en ~2 min; se vende otra vez.`);
                }
                delete position.unconfirmedSellId;
                delete position.sellNotFound;
                if (prior && prior.executedQty > 0)
                    parts.push(prior);
            }
            const outcome = await this.sellRemaining(symbol, position, triggerPrice, filters);
            await this.finishClose(symbol, position, filters, reason, outcome, triggerPrice, openTime);
        }
        catch (error) {
            // La posicion sigue en activePositions (con los tramos ya vendidos): se reintenta mas tarde
            await this.handleCloseError(symbol, position, error, triggerPrice, reason, openTime, override);
        }
        finally {
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
    async sellRemaining(symbol, position, price, f) {
        const parts = position.exitParts ?? (position.exitParts = []);
        let limit = position.netQuantity; // máximo vendible: la posición, o lo libre si Binance dice que hay menos
        let note = '';
        for (let attempt = 0; attempt < 3; attempt++) {
            const qty = (0, execution_1.floorToStep)(limit - (0, execution_1.soldQuantity)(parts), f.stepSize);
            if (!(await this.isSellable(symbol, parseFloat(qty), price, f)))
                break;
            try {
                const exec = await this.rest.marketSell(symbol, qty);
                if (exec.executedQty > 0)
                    parts.push(exec);
            }
            catch (error) {
                if (error instanceof rest_client_1.OrderStatusUnknownError) {
                    position.unconfirmedSellId = error.clientOrderId;
                    const resolved = await this.resolveUnknownOrder(symbol, error.clientOrderId);
                    // "No existe" puede ser que aún no aparezca (-1007): venta dudosa, se reconsulta con espera creciente
                    if (resolved === null) {
                        position.sellNotFound = 1;
                        throw new rest_client_1.OrderNotFoundError(symbol, error.clientOrderId, error);
                    }
                    delete position.unconfirmedSellId;
                    if (resolved.executedQty > 0)
                        parts.push(resolved);
                    continue;
                }
                if (error instanceof rest_client_1.OrderNotFoundError) {
                    position.unconfirmedSellId = error.clientOrderId;
                    position.sellNotFound = 1;
                    throw error;
                }
                if (!(0, rest_client_1.isInsufficientBalance)(error))
                    throw error;
                const free = (await this.rest.getFreeBalances()).get(f.baseAsset) ?? 0;
                if (free >= parseFloat(qty))
                    throw error; // el saldo alcanza: no es eso, se reintenta más tarde
                console.warn(`[EXIT] ${symbol}: saldo insuficiente, libre ${free} ${f.baseAsset} para vender ${qty}.`);
                note = ` (saldo insuficiente: libre ${(0, execution_1.formatQty)(free)} de ${qty} ${f.baseAsset})`;
                limit = (0, execution_1.soldQuantity)(parts) + free;
            }
        }
        const remaining = parseFloat((0, execution_1.floorToStep)(limit - (0, execution_1.soldQuantity)(parts), f.stepSize));
        if (await this.isSellable(symbol, remaining, price, f)) {
            throw new Error(`venta incompleta de ${symbol}: quedan ${remaining} ${f.baseAsset} por vender`);
        }
        const unsold = (0, execution_1.formatQty)(Math.max(0, position.netQuantity - (0, execution_1.soldQuantity)(parts)));
        return {
            note,
            noSaleReason: note ? `SIN SALDO${note}` : `POLVO: ${unsold} ${f.baseAsset} por debajo del mínimo de Binance, no se puede vender`,
            // Con saldo insuficiente, limit ya es lo vendido + lo libre: no se valora lo que no está en la cuenta
            heldQty: Math.max(0, limit - (0, execution_1.soldQuantity)(parts))
        };
    }
    /**
     * ¿Es vendible esta cantidad? minQty/maxQty y mínimo nocional con margen. Cerca del mínimo se usa el precio
     * medio de Binance (avgPrice), que es con el que valora las MARKET, en vez del último precio.
     */
    async isSellable(symbol, qty, price, f) {
        if (!(0, execution_1.isTradable)(qty, price, { ...f, minNotional: 0 }))
            return false;
        if (f.minNotional <= 0)
            return true;
        if (qty * price >= f.minNotional * (1 + NOTIONAL_CHECK_BAND))
            return true;
        let reference = price;
        try {
            reference = await this.rest.getAvgPrice(symbol);
        }
        catch {
            // sin precio medio se usa el último precio
        }
        return (0, execution_1.isTradable)(qty, reference, f, exports.NOTIONAL_MARGIN);
    }
    /**
     * Registra la salida con todos los tramos vendidos (PnL neto real) o, si no se vendió nada, la cierra sin venta.
     * triggerPrice null / openTime undefined: cierre detectado al arrancar (sin vela ni nivel).
     */
    async finishClose(symbol, position, f, reason, outcome, triggerPrice, openTime) {
        const parts = position.exitParts ?? [];
        if (parts.length === 0) {
            await this.closeWithoutSale(symbol, position, outcome.noSaleReason, openTime);
            return;
        }
        const exec = (0, execution_1.mergeExecutions)(parts);
        let note = outcome.note;
        const unsold = parseFloat((0, execution_1.floorToStep)(position.netQuantity - exec.executedQty, f.stepSize));
        if (unsold > 0 && !note)
            note = ` (quedan ${(0, execution_1.formatQty)(unsold)} ${f.baseAsset} sin vender)`;
        // Residuo que sigue en la cuenta (Binance da las cantidades con 8 decimales): se valora al precio de salida
        const residual = Number(Math.max(0, outcome.heldQty ?? (position.netQuantity - exec.executedQty)).toFixed(8));
        this.activePositions.delete(symbol);
        if (openTime !== undefined)
            this.lastExitOpenTime.set(symbol, openTime);
        this.closeRetry.delete(symbol);
        const pnl = (0, execution_1.netPnl)(position, exec, residual);
        const px = (value) => (0, execution_1.formatPrice)(value, f.tickSize);
        console.log(`[EXIT CONFIRMED] ${symbol} closed. Order ID: ${exec.orderId} | ${exec.executedQty} @ ${px(exec.avgPrice)} ` +
            `| PnL neto ${(0, execution_1.formatUsdt)(pnl)}${residual > 0 ? ` (residuo ${(0, execution_1.formatQty)(residual)} ${f.baseAsset})` : ''}`);
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
        this.notify(`<b>${(0, telegram_client_1.escapeHtml)(reason)}</b>\n` +
            `🔹 <b>Moneda:</b> ${symbol}\n` +
            `🔹 <b>Entrada:</b> $${px(position.entryPrice)}\n` +
            `🔹 <b>Salida:</b> $${px(exec.avgPrice)}${triggerPrice !== null ? ` (nivel $${px(triggerPrice)})` : ''}\n` +
            `💸 <b>Comisiones:</b> ${fees.toFixed(4)} USDT\n` +
            (residual > 0 ? `🧹 <b>Residuo sin vender:</b> ${(0, execution_1.formatQty)(residual)} ${f.baseAsset} ` +
                `(${(residual * exec.avgPrice).toFixed(4)} USDT, incluido en el PnL)\n` : '') +
            `💰 <b>PnL neto:</b> ${(0, execution_1.formatUsdt)(pnl)}` +
            (note ? `\n<i>${(0, telegram_client_1.escapeHtml)(note.trim())}</i>` : ''));
    }
    async handleCloseError(symbol, position, error, triggerPrice, reason, openTime, override) {
        const msg = (0, rest_client_1.binanceError)(error).msg;
        console.error(`[ERROR] Closing position for ${symbol}:`, msg);
        if (error instanceof rest_client_1.OrderStatusUnknownError) {
            position.unconfirmedSellId = error.clientOrderId;
            this.setCloseRetry(symbol, CLOSE_UNKNOWN_RETRY_MS, triggerPrice, false);
            if (!this.notifiedUnknownSells.has(error.clientOrderId)) {
                this.notifiedUnknownSells.add(error.clientOrderId);
                this.notify(`❗ <b>VENTA SIN CONFIRMAR: ${symbol}</b>\nSe consultará la orden <code>${(0, telegram_client_1.escapeHtml)(error.clientOrderId)}</code> ` +
                    `antes de volver a vender.`);
            }
            return;
        }
        if (error instanceof rest_client_1.OrderNotFoundError) {
            // Venta dudosa: sin respuesta y "no existe" al consultarla, puede aparecer tarde. Se reconsulta pasados
            // 10, 30 y 90 s (LATE_ORDER_RECHECKS_MS) antes de volver a vender, sin adelanto por el SL
            position.unconfirmedSellId = error.clientOrderId;
            position.sellNotFound ??= 1;
            const waitMs = exports.LATE_ORDER_RECHECKS_MS[Math.min(position.sellNotFound, exports.LATE_ORDER_RECHECKS_MS.length) - 1];
            this.setCloseRetry(symbol, waitMs, triggerPrice, false);
            if (position.sellNotFound === 1) {
                this.notify(`❗ <b>VENTA SIN CONFIRMAR: ${symbol}</b>\nBinance aún no muestra la orden ` +
                    `<code>${(0, telegram_client_1.escapeHtml)(error.clientOrderId)}</code>; se consulta durante ~2 min antes de volver a vender.`);
            }
            return;
        }
        if ((0, rest_client_1.isFilterFailure)(error)) {
            // Binance rechaza la cantidad (NOTIONAL/LOT_SIZE). Solo es polvo si, valorada con su precio medio (con el
            // que juzga las MARKET), no llega al mínimo con margen; si es vendible se reintenta con espera creciente.
            const rejections = (position.filterRejections ?? 0) + 1;
            position.filterRejections = rejections;
            // El paso o los límites de cantidad guardados pueden estar desactualizados: se vuelven a leer
            if ((0, rest_client_1.isLotSizeFailure)(error))
                this.rest.invalidateSymbolFilters(symbol);
            try {
                const f = await this.rest.getSymbolFilters(symbol);
                let dust = false;
                try {
                    const avg = await this.rest.getAvgPrice(symbol);
                    const qty = parseFloat((0, execution_1.floorToStep)(position.netQuantity - (0, execution_1.soldQuantity)(position.exitParts), f.stepSize));
                    dust = !(0, execution_1.isTradable)(qty, avg, f, exports.NOTIONAL_MARGIN);
                }
                catch {
                    // sin precio medio no se puede confirmar que sea polvo: se reintenta
                }
                if (dust) {
                    await this.finishClose(symbol, position, f, reason, { note: ` (resto no vendible: ${msg})`,
                        noSaleReason: `POLVO: Binance rechaza la venta (${msg}) y con su precio medio no llega al mínimo` }, triggerPrice, openTime);
                    return;
                }
            }
            catch (inner) {
                console.error(`[ERROR] ${symbol}: no se pudo comprobar el rechazo por filtro:`, (0, rest_client_1.binanceError)(inner).msg);
            }
            const waitMs = Math.min(CLOSE_RETRY_MS * 2 ** (rejections - 1), FILTER_RETRY_MAX_MS);
            this.setCloseRetry(symbol, waitMs, triggerPrice, false);
            if (rejections === FILTER_ALERT_FROM ||
                (rejections > FILTER_ALERT_FROM && (rejections - FILTER_ALERT_FROM) % FILTER_ALERT_EVERY === 0)) {
                this.notify(`⚠️ <b>VENTA RECHAZADA: ${symbol}</b>\nBinance rechazó la venta ${rejections} veces ` +
                    `(<i>${(0, telegram_client_1.escapeHtml)(msg)}</i>), pero con su precio medio la posición es vendible: se reintenta cada ` +
                    `${Math.round(waitMs / 1000)} s.`);
            }
            return;
        }
        // Error genérico: pausa de 5 s; el reintento inmediato por caída bajo el SL no se encadena
        this.setCloseRetry(symbol, CLOSE_RETRY_MS, triggerPrice, !override);
    }
    setCloseRetry(symbol, waitMs, price, slOverride) {
        this.closeRetry.set(symbol, { until: Date.now() + waitMs, price, slOverride });
    }
    /** Cierra la posición en el ledger sin venta (polvo, sin saldo u orden inexistente): sin PnL, con el motivo. */
    async closeWithoutSale(symbol, position, reason, openTime) {
        this.activePositions.delete(symbol);
        if (openTime !== undefined)
            this.lastExitOpenTime.set(symbol, openTime);
        this.closeRetry.delete(symbol);
        console.warn(`[EXIT] ${symbol}: posición ${position.orderId} cerrada en el ledger sin venta. ${reason}`);
        await this.ledgerClose({ order_id: position.orderId, symbol, pnl: null, reason });
        this.notify(`⚠️ <b>CIERRE SIN VENTA: ${symbol}</b>\n${(0, telegram_client_1.escapeHtml)(reason)}`);
    }
    /** Fila PENDING antes de enviar la compra. false si el ledger no la registró (entonces no se compra). */
    async ledgerPending(symbol, intent) {
        try {
            const result = await this.brain.ask('ledger_pending', {
                client_order_id: intent.clientOrderId,
                symbol,
                signal_price: intent.signalPrice,
                take_profit: intent.takeProfit,
                stop_loss: intent.stopLoss
            });
            if (result?.status !== 'logged')
                throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            return true;
        }
        catch (error) {
            console.error(`[LEDGER] No se pudo registrar la compra pendiente de ${symbol}:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar la compra pendiente de ${symbol}; no se envía la orden.`);
            return false;
        }
    }
    /** La fila PENDING pasa a CANCELLED: la compra no existe en Binance (rechazada, sin ejecutar o no llegó). */
    async ledgerCancel(symbol, clientOrderId, reason) {
        try {
            const result = await this.brain.ask('ledger_cancel', { client_order_id: clientOrderId, symbol, reason });
            if (result?.status !== 'updated')
                throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Compra ${clientOrderId} marcada como CANCELLED (${reason}).`);
        }
        catch (error) {
            console.error(`[LEDGER] No se pudo cancelar la compra pendiente ${clientOrderId}:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo marcar como cancelada la compra pendiente de ${symbol} ` +
                `(<code>${(0, telegram_client_1.escapeHtml)(clientOrderId)}</code>).`);
        }
    }
    /** Compra confirmada: con clientOrderId su fila PENDING pasa a OPEN con los fills reales. false si falló. */
    async ledgerOpen(position, exec, signalPrice, clientOrderId) {
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
            if (result?.status !== 'logged')
                throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Trade logged securely in Python CSV Ledger.`);
            return true;
        }
        catch (error) {
            console.error(`[LEDGER] Failed to log trade to Python ledger:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar la compra de ${position.symbol} (orden ${position.orderId}).`);
            return false;
        }
    }
    async ledgerUpdateSl(symbol, orderId, newStopLoss) {
        try {
            await this.brain.ask('ledger_update_sl', {
                order_id: orderId,
                symbol,
                stop_loss: newStopLoss
            });
        }
        catch (error) {
            console.error(`[LEDGER] No se pudo actualizar el Stop Loss en el ledger para ${symbol}:`, error?.message ?? error);
        }
    }
    async ledgerPartial(symbol, orderId, stopLoss, soldQty, soldQuote, soldFeeUsdt) {
        try {
            await this.brain.ask('ledger_partial', {
                order_id: orderId,
                symbol,
                stop_loss: stopLoss,
                take_profit: null,
                sold_quantity: soldQty,
                sold_quote: soldQuote,
                sold_fee_usdt: soldFeeUsdt
            });
        }
        catch (error) {
            console.error(`[LEDGER] No se pudo registrar el cierre parcial en el ledger para ${symbol}:`, error?.message ?? error);
        }
    }
    async ledgerClose(payload) {
        try {
            const result = await this.brain.ask('ledger_close', payload);
            if (result?.status !== 'updated')
                throw new Error(result?.message ?? result?.error ?? JSON.stringify(result));
            console.log(`[LEDGER] Trade ${payload.order_id} marked as CLOSED.`);
        }
        catch (error) {
            console.error(`[LEDGER] Failed to update Python ledger closure:`, error?.message ?? error);
            this.notify(`⚠️ <b>LEDGER:</b> no se pudo registrar el cierre de la orden ${payload.order_id}.`);
        }
    }
    // Telegram no debe retrasar las órdenes ni dejar promesas rechazadas sin capturar
    notify(message) {
        try {
            Promise.resolve(this.telegram.sendMessage(message)).catch((error) => console.error('[TELEGRAM] No se pudo enviar el aviso:', error?.message ?? error));
        }
        catch (error) {
            console.error('[TELEGRAM] No se pudo enviar el aviso:', error?.message ?? error);
        }
    }
    async currentPrice(symbol, fallback) {
        try {
            return await this.rest.getPrice(symbol);
        }
        catch {
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
    async syncStateFromLedger() {
        // 0. Compras PENDING (el proceso murió con la compra en vuelo): ejecutadas -> se adoptan (su fila pasa a OPEN y
        //    siguen la verificación normal); inexistentes -> CANCELLED; sin respuesta -> se reintentan con los precios.
        const adopted = await this.resolveStartupPendingBuys();
        let openTrades;
        try {
            openTrades = await this.brain.ask('sync_positions');
        }
        catch (error) {
            console.error(`[SYNC] Failed to sync state from ledger.`, error);
            return;
        }
        if (!Array.isArray(openTrades)) {
            console.error(`[SYNC] Respuesta inesperada del ledger:`, openTrades);
            return;
        }
        // Adoptadas cuya fila no se pudo pasar a OPEN: se gestionan igual (se compraron)
        for (const trade of adopted) {
            if (!openTrades.some((t) => t.symbol === trade.symbol && Number(t.order_id) === Number(trade.order_id))) {
                openTrades.push(trade);
            }
        }
        // Una posicion por moneda: si el ledger tiene varias OPEN del mismo simbolo se gestiona la mas reciente
        const latest = new Map();
        for (const trade of openTrades) {
            const previous = latest.get(trade.symbol);
            if (previous) {
                console.warn(`[SYNC] ${trade.symbol}: varias posiciones OPEN en el ledger; se gestiona solo la más reciente.`);
            }
            if (!previous || Number(trade.timestamp ?? 0) >= Number(previous.timestamp ?? 0))
                latest.set(trade.symbol, trade);
        }
        let balances = null;
        if (latest.size > 0) {
            try {
                balances = await this.rest.getFreeBalances();
            }
            catch (error) {
                console.warn(`[SYNC] No se pudo leer el saldo (${(0, rest_client_1.binanceError)(error).msg}); saldo sin comprobar.`);
            }
        }
        for (const trade of latest.values()) {
            const position = positionFromLedger(trade);
            try {
                if (!(await this.verifyStartupOrder(position)))
                    continue;
                if (!balances)
                    throw new Error('saldo no disponible');
                if (!(await this.checkStartupBalance(position, balances)))
                    continue;
            }
            catch (error) {
                position.startupCheckPending = true;
                const msg = (0, rest_client_1.binanceError)(error).msg;
                console.warn(`[SYNC] ${position.symbol}: no se pudo verificar la posición ${position.orderId} en Binance ` +
                    `(${msg}); no se gestiona hasta verificarla (se reintenta con los próximos precios).`);
                this.notify(`⚠️ <b>POSICIÓN SIN VERIFICAR: ${position.symbol}</b>\nBinance no respondió al arrancar ` +
                    `(<i>${(0, telegram_client_1.escapeHtml)(msg)}</i>). No se venderá hasta poder verificarla; se reintenta con cada precio.`);
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
    async resolveStartupPendingBuys() {
        let pendingRows;
        try {
            pendingRows = await this.brain.ask('sync_pending');
        }
        catch (error) {
            console.error(`[SYNC] No se pudieron leer las compras pendientes del ledger:`, error?.message ?? error);
            return [];
        }
        if (!Array.isArray(pendingRows))
            return [];
        // Una consulta por fila, todas a la vez y sin esperas: lo que no se resuelva en el acto ("no existe" por ahora o
        // sin respuesta) se sigue consultando en segundo plano con los precios, sin retrasar la conexión del WebSocket.
        const adopted = await Promise.all(pendingRows.map(row => this.resolveStartupPendingRow(row)));
        return adopted.filter(row => row !== null);
    }
    /** Fila PENDING del arranque. Devuelve la fila OPEN de una compra adoptada cuyo ledger no se pudo actualizar. */
    async resolveStartupPendingRow(row) {
        const symbol = String(row.symbol);
        const intent = {
            clientOrderId: String(row.client_order_id ?? ''),
            signalPrice: Number.isFinite(row.signal_price) ? row.signal_price : null,
            takeProfit: Number.isFinite(row.take_profit) ? row.take_profit : Infinity,
            stopLoss: Number.isFinite(row.stop_loss) ? row.stop_loss : -Infinity
        };
        if (!intent.clientOrderId) {
            console.warn(`[SYNC] ${symbol}: fila PENDING sin client_order_id; no se puede consultar.`);
            return null;
        }
        let exec; // undefined: Binance no respondió
        try {
            exec = await this.rest.lookupOrder(symbol, intent.clientOrderId);
        }
        catch (error) {
            console.warn(`[SYNC] ${symbol}: la compra pendiente ${intent.clientOrderId} no se pudo consultar ` +
                `(${(0, rest_client_1.binanceError)(error).msg}); se reintenta con los próximos precios.`);
        }
        if (exec === undefined || exec === null) {
            // Compra dudosa: queda PENDING, la moneda no abre otra compra y se resuelve con los precios (pendingEntries
            // los guarda para revisar el TP/SL si se adopta). "No existe": espera creciente, puede aparecer tarde.
            const notFound = exec === null ? 1 : 0;
            this.unresolvedBuys.set(symbol, {
                ...intent, notFound, retryAt: Date.now() + (notFound ? exports.LATE_ORDER_RECHECKS_MS[0] : CLOSE_RETRY_MS)
            });
            if (!this.pendingEntries.has(symbol))
                this.pendingEntries.set(symbol, []);
            this.notify(`⚠️ <b>COMPRA PENDIENTE SIN VERIFICAR: ${symbol}</b>\n` +
                (notFound ? 'Binance aún no la muestra' : 'Binance no respondió al arrancar') +
                `; se consulta <code>${(0, telegram_client_1.escapeHtml)(intent.clientOrderId)}</code> con los próximos precios.`);
            return null;
        }
        if (!(exec.executedQty > 0)) {
            await this.ledgerCancel(symbol, intent.clientOrderId, `SIN EJECUTAR (${exec.status}, detectado al arrancar)`);
            return null;
        }
        const position = this.positionFromExecution(symbol, exec, intent);
        console.warn(`[SYNC] ${symbol}: la compra pendiente ${intent.clientOrderId} se ejecutó antes del reinicio; se adopta.`);
        this.notify(`🔁 <b>COMPRA RECUPERADA: ${symbol}</b>\nLa orden <code>${(0, telegram_client_1.escapeHtml)(intent.clientOrderId)}</code> se ` +
            `ejecutó antes del reinicio (${(0, execution_1.formatQty)(exec.executedQty)} a $${(0, execution_1.formatPrice)(exec.avgPrice)}); se gestiona como posición abierta.`);
        if (await this.ledgerOpen(position, exec, intent.signalPrice, intent.clientOrderId))
            return null;
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
    async retryStartupCheck(symbol, position) {
        if (Date.now() < (this.startupCheckRetryAt.get(symbol) ?? 0))
            return false;
        this.closing.add(symbol); // ningún otro precio toca la posición mientras se verifica
        try {
            if (!(await this.verifyStartupOrder(position)))
                return false;
            if (!(await this.checkStartupBalance(position, await this.rest.getFreeBalances())))
                return false;
            delete position.startupCheckPending;
            this.startupCheckRetryAt.delete(symbol);
            console.log(`[SYNC] ${symbol}: posición ${position.orderId} verificada en Binance; se gestiona desde ahora.`);
            return this.activePositions.get(symbol) === position;
        }
        catch (error) {
            this.startupCheckRetryAt.set(symbol, Date.now() + CLOSE_RETRY_MS);
            console.warn(`[SYNC] ${symbol}: la posición ${position.orderId} sigue sin verificar (${(0, rest_client_1.binanceError)(error).msg}).`);
            return false;
        }
        finally {
            this.closing.delete(symbol);
        }
    }
    /** La compra existe y se ejecutó, y no se vendió ya. false si la posición quedó cerrada en el ledger. */
    async verifyStartupOrder(position) {
        const { symbol } = position;
        const order = await this.rest.getOrder(symbol, position.orderId);
        if (order === null) {
            await this.closeWithoutSale(symbol, position, `ORDEN INEXISTENTE al arrancar: Binance no tiene la compra ${position.orderId}`);
            return false;
        }
        if (!(parseFloat(order.executedQty) > 0)) {
            await this.closeWithoutSale(symbol, position, `COMPRA SIN EJECUTAR al arrancar: la orden ${position.orderId} está ${order.status} sin nada ejecutado`);
            return false;
        }
        // Ventas posteriores a la compra que el ledger no registró (p. ej. el bot se cortó tras vender)
        const buyTrades = await this.rest.getMyTrades(symbol, { orderId: position.orderId });
        if (buyTrades.length === 0)
            return true;
        const lastBuyTradeId = Math.max(...buyTrades.map(t => Number(t.id)));
        const later = await this.rest.getMyTrades(symbol, { fromId: lastBuyTradeId + 1 });
        const f = await this.rest.getSymbolFilters(symbol);
        const sellable = parseFloat((0, execution_1.sellableQuantity)(position.netQuantity, f));
        const sells = [];
        let sold = 0;
        for (const trade of later) {
            if (trade.isBuyer) {
                // Otra compra del mismo par (manual u otra posición): las ventas que siguen ya no son seguro de esta
                console.warn(`[SYNC] ${symbol}: hay otra compra (orden ${trade.orderId}) después de la ${position.orderId}; ` +
                    `solo se cuentan las ventas anteriores a ella.`);
                break;
            }
            if (sold >= sellable)
                break;
            sells.push(trade);
            sold += parseFloat(trade.qty);
        }
        if (sells.length === 0)
            return true;
        position.exitParts = [await this.rest.tradesToExecution(symbol, sells, { orderId: sells[0].orderId })];
        const remaining = parseFloat((0, execution_1.floorToStep)(position.netQuantity - (0, execution_1.soldQuantity)(position.exitParts), f.stepSize));
        const price = await this.currentPrice(symbol, position.entryPrice);
        if (await this.isSellable(symbol, remaining, price, f)) {
            // Si takeProfit es Infinity (take_profit vacío en el ledger tras record_partial_exit), las ventas previas
            // son tramos parciales (TP1/TP2): se conservan en exitParts y la posición sigue abierta esperando SL o TP3.
            if (!Number.isFinite(position.takeProfit)) {
                position.tp1PartialDone = true;
                console.log(`[SYNC] ${symbol}: cierre parcial previo recuperado (${sold} ${f.baseAsset} vendidos); continúa abierta por ${remaining} ${f.baseAsset}.`);
                return true;
            }
            // La salida total ya estaba en marcha antes del reinicio: se completa con el primer precio
            console.warn(`[SYNC] ${symbol}: ya se vendieron ${sold} ${f.baseAsset} de la posición; se vende el resto (${remaining}).`);
            position.exitReason = 'SALIDA EN CURSO (iniciada antes de arrancar)';
            return true;
        }
        await this.finishClose(symbol, position, f, 'VENTA YA EJECUTADA (detectada al arrancar)', { note: '', noSaleReason: '' }, null);
        return false;
    }
    async checkStartupBalance(position, balances) {
        const { symbol } = position;
        const f = await this.rest.getSymbolFilters(symbol);
        const free = balances.get(f.baseAsset) ?? 0;
        const sold = (0, execution_1.soldQuantity)(position.exitParts);
        const needed = parseFloat((0, execution_1.sellableQuantity)(position.netQuantity - sold, f));
        const available = parseFloat((0, execution_1.sellableQuantity)(position.netQuantity - sold, f, free));
        const price = await this.currentPrice(symbol, position.entryPrice);
        if (await this.isSellable(symbol, available, price, f)) {
            if (available < needed) {
                console.warn(`[SYNC] ${symbol}: saldo libre ${free} ${f.baseAsset} menor que la posición (${needed}); se venderá ${available}.`);
                position.netQuantity = sold + available;
            }
            return true;
        }
        const reason = free < needed
            ? `SIN SALDO al arrancar: libre ${(0, execution_1.formatQty)(free)} ${f.baseAsset}, la posición necesita ${needed}`
            : `POLVO al arrancar: ${(0, execution_1.formatQty)(position.netQuantity - sold)} ${f.baseAsset} por debajo del mínimo de Binance`;
        console.warn(`[SYNC] ${symbol}: ${reason}. Se cierra en el ledger.`);
        // Con tramos ya vendidos se registra esa salida real; si no, cierre sin venta
        await this.finishClose(symbol, position, f, 'VENTA YA EJECUTADA (detectada al arrancar)', { note: ` (resto: ${reason})`, noSaleReason: reason, heldQty: Math.min(free, Math.max(0, position.netQuantity - sold)) }, null);
        return false;
    }
    close() {
        this.stopped = true;
        if (this.watchdog)
            clearInterval(this.watchdog);
        this.watchdog = null;
        try {
            this.ws?.close();
        }
        catch (error) {
            console.error('[WS] Error al cerrar:', error?.message ?? error);
        }
    }
}
exports.BinanceWSClient = BinanceWSClient;
//# sourceMappingURL=ws-client.js.map