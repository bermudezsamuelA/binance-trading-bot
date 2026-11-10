import { BinanceRestClient } from './rest-client';
import { EntryCost, Execution } from './execution';
export declare const LATE_ORDER_RECHECKS_MS: number[];
export declare const LATE_BUY_CANCEL_REASON = "NO LLEG\u00D3 A BINANCE (no apareci\u00F3 en ~2 min de consultas)";
export declare const NOTIONAL_MARGIN = 0.01;
export declare const STALE_SOCKET_MS = 120000;
export declare const STALE_CHECK_MS = 15000;
export interface ExitPlanConfig {
    mode?: string;
    tp1_ratio?: number;
    tp2_ratio?: number;
    tp3_ratio?: number;
    time_stop_hours?: number;
}
export interface Position extends EntryCost {
    symbol: string;
    orderId: number;
    takeProfit: number;
    stopLoss: number;
    quantity: number;
    netQuantity: number;
    exitReason?: string;
    exitTrigger?: number;
    exitParts?: Execution[];
    partialTp1Ratio?: number;
    tp1PartialDone?: boolean;
    unconfirmedSellId?: string;
    sellNotFound?: number;
    filterRejections?: number;
    startupCheckPending?: boolean;
}
type RestApi = Pick<BinanceRestClient, 'getSymbolFilters' | 'invalidateSymbolFilters' | 'marketBuy' | 'marketSell' | 'getFreeBalances' | 'getPrice' | 'getAvgPrice' | 'lookupOrder' | 'getOrder' | 'getMyTrades' | 'tradesToExecution'>;
export interface SocketLike {
    on(event: string, listener: (...args: any[]) => any): unknown;
    close(): void;
    terminate?(): void;
}
export interface WSClientDeps {
    rest: RestApi;
    brain: {
        ask(type: string, payload?: any): Promise<any>;
    };
    telegram: {
        sendMessage(message: string): Promise<void>;
    };
    createSocket: (url: string) => SocketLike;
    sleep: (ms: number) => Promise<void>;
    klineInterval: string;
}
/** Posición a partir de una fila OPEN del ledger (las filas antiguas no tienen datos de ejecución). */
export declare function positionFromLedger(trade: any): Position;
export declare class BinanceWSClient {
    private ws;
    private baseUrl;
    private tradeQuoteUsdt;
    private rest;
    private brain;
    private telegram;
    private createSocket;
    private sleep;
    private activePositions;
    private lastClosedOpenTime;
    private lastExitOpenTime;
    private orderCooldownUntil;
    private closing;
    private pendingEntries;
    private closeRetry;
    private notifiedUnknownSells;
    private startupCheckRetryAt;
    private unresolvedBuys;
    private url;
    private stopped;
    private reconnectDelayMs;
    private lastSocketActivityAt;
    private watchdog;
    /**
     * @param tradeQuoteUsdt USDT por operación por defecto. Lo da Python en el handshake (optimize.NOTIONAL_USDT).
     *                       Si una estrategia personalizada envía `signal.quote_usdt`, se usa ese monto dinámico.
     */
    constructor(roster: string[], tradeQuoteUsdt: number, deps?: Partial<WSClientDeps>);
    /** Recupera las posiciones del ledger y despues abre el WebSocket: ningun precio llega sin ellas. */
    start(): Promise<void>;
    /** Si el WebSocket lleva STALE_SOCKET_MS sin mensajes ni pings, se corta: el evento 'close' reconecta. */
    private checkSocketAlive;
    getPosition(symbol: string): Readonly<Position> | undefined;
    private connect;
    private scheduleReconnect;
    private handleMarketData;
    private manageExistingPosition;
    private evaluateNewTrade;
    /**
     * Ejecuta una venta parcial a mercado (ej. 50% en TP1 o 50% del remanente en TP2 por cruce de EMA 50 1H).
     * El tramo vendido se acumula en `position.exitParts` para que el cierre final calcule el PnL neto total exacto.
     */
    private executePartialClose;
    private canOpenPosition;
    /**
     * Compra MARKET por quoteUsdt (el dinámico `signal.quote_usdt` de RiskManager si viene, o `this.tradeQuoteUsdt`).
     * Antes de enviarla se escribe en el ledger una fila PENDING con su newClientOrderId: si el proceso muere entre
     * la ejecución y el registro, al arrancar se encuentra en Binance.
     */
    private openPosition;
    /** Posición a partir de lo ejecutado de verdad y de los niveles absolutos de la estrategia. */
    private positionFromExecution;
    /**
     * Registra una compra ejecutada: ledger (la fila PENDING pasa a OPEN), posición activa, aviso y revisión de los
     * precios vistos mientras se compraba (carrera compra/TP-SL).
     */
    private registerEntry;
    /**
     * Vuelve a consultar una compra dudosa (PENDING sin resolver) cuando toca: sin respuesta, cada CLOSE_RETRY_MS; tras
     * un "no existe", pasados 10, 30 y 90 s (LATE_ORDER_RECHECKS_MS). Ejecutada: se adopta como posición abierta y los
     * precios vistos mientras tanto se revisan contra su TP/SL. "No existe" también en la última consulta (≈ 2 min):
     * la fila pasa a CANCELLED y la moneda vuelve a poder comprar.
     */
    private retryUnresolvedBuy;
    private handleOrderError;
    /**
     * Orden con estado desconocido: se consulta por newClientOrderId hasta UNKNOWN_ORDER_LOOKUPS veces.
     * Devuelve la ejecución real, null si Binance no la tiene, o lanza OrderStatusUnknownError.
     */
    private resolveUnknownOrder;
    private closePosition;
    /**
     * Vende a mercado lo que falte de la posición (cada tramo ejecutado se guarda en position.exitParts).
     * - Saldo insuficiente (p. ej. una comisión no prevista): se vende lo libre.
     * - MARKET llenada en parte o sin llenar (libro sin liquidez): se intenta con el resto.
     * - Tramo sin confirmar: se consulta; si sigue desconocido, se lanza y la posición espera.
     * Si al terminar aún queda algo vendible, lanza (se reintenta); lo que quede por debajo del mínimo es polvo.
     */
    private sellRemaining;
    /**
     * ¿Es vendible esta cantidad? minQty/maxQty y mínimo nocional con margen. Cerca del mínimo se usa el precio
     * medio de Binance (avgPrice), que es con el que valora las MARKET, en vez del último precio.
     */
    private isSellable;
    /**
     * Registra la salida con todos los tramos vendidos (PnL neto real) o, si no se vendió nada, la cierra sin venta.
     * triggerPrice null / openTime undefined: cierre detectado al arrancar (sin vela ni nivel).
     */
    private finishClose;
    private handleCloseError;
    private setCloseRetry;
    /** Cierra la posición en el ledger sin venta (polvo, sin saldo u orden inexistente): sin PnL, con el motivo. */
    private closeWithoutSale;
    /** Fila PENDING antes de enviar la compra. false si el ledger no la registró (entonces no se compra). */
    private ledgerPending;
    /** La fila PENDING pasa a CANCELLED: la compra no existe en Binance (rechazada, sin ejecutar o no llegó). */
    private ledgerCancel;
    /** Compra confirmada: con clientOrderId su fila PENDING pasa a OPEN con los fills reales. false si falló. */
    private ledgerOpen;
    private ledgerUpdateSl;
    private ledgerPartial;
    private ledgerClose;
    private notify;
    private currentPrice;
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
    syncStateFromLedger(): Promise<void>;
    /**
     * Resuelve las compras PENDING del ledger por su client_order_id. Devuelve, como filas OPEN, las adoptadas cuya
     * fila no se pudo actualizar (las demás ya vuelven en sync_positions).
     */
    private resolveStartupPendingBuys;
    /** Fila PENDING del arranque. Devuelve la fila OPEN de una compra adoptada cuyo ledger no se pudo actualizar. */
    private resolveStartupPendingRow;
    /**
     * Repite la verificación del arranque que falló (como mucho cada CLOSE_RETRY_MS). true si la posición sigue
     * abierta y ya se puede gestionar con este precio; false si sigue sin verificar o quedó cerrada en el ledger.
     */
    private retryStartupCheck;
    /** La compra existe y se ejecutó, y no se vendió ya. false si la posición quedó cerrada en el ledger. */
    private verifyStartupOrder;
    private checkStartupBalance;
    close(): void;
}
export {};
//# sourceMappingURL=ws-client.d.ts.map