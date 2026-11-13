import { Execution, SymbolFilters } from './execution';
export declare const RECV_WINDOW_MS = 10000;
export declare const ERR_UNEXPECTED_RESP = -1006;
export declare const ERR_TIMEOUT = -1007;
export declare const ERR_INVALID_MESSAGE = -1013;
export declare const ERR_TIMESTAMP = -1021;
export declare const ERR_NEW_ORDER_REJECTED = -2010;
export declare const ERR_NO_SUCH_ORDER = -2013;
export interface HttpClient {
    get(url: string, config?: any): Promise<{
        data: any;
    }>;
    post(url: string, data?: any, config?: any): Promise<{
        data: any;
    }>;
    delete(url: string, config?: any): Promise<{
        data: any;
    }>;
}
/** Código y mensaje de Binance ({code, msg}) a partir de un error de axios o de cualquier otro error. */
export declare function binanceError(error: any): {
    code?: number;
    msg: string;
    httpStatus?: number;
};
/** -2010 "Account has insufficient balance for requested action." */
export declare function isInsufficientBalance(error: any): boolean;
/** -1013 "Filter failure: NOTIONAL / MIN_NOTIONAL / LOT_SIZE / MARKET_LOT_SIZE": la cantidad no es negociable. */
export declare function isFilterFailure(error: any): boolean;
/** -1013 por LOT_SIZE / MARKET_LOT_SIZE: el paso o los límites de cantidad guardados pueden estar desactualizados. */
export declare function isLotSizeFailure(error: any): boolean;
/**
 * Sin respuesta, HTTP 5xx o -1006/-1007: según la documentación la orden pudo ejecutarse,
 * no se puede tratar como fallo sin consultarla.
 */
export declare function isUnknownStatus(error: any): boolean;
/** La orden se envió pero no se pudo confirmar si se ejecutó. */
export declare class OrderStatusUnknownError extends Error {
    readonly symbol: string;
    readonly clientOrderId: string;
    constructor(symbol: string, clientOrderId: string, cause: unknown);
}
/**
 * La orden quedó sin respuesta y al consultarla Binance dijo que no existe (-2013 dos veces). Puede aparecer tarde
 * (-1007: el motor la procesa después), así que quien la recibe debe volver a consultarla antes de reenviarla.
 */
export declare class OrderNotFoundError extends Error {
    readonly symbol: string;
    readonly clientOrderId: string;
    constructor(symbol: string, clientOrderId: string, cause: unknown);
}
/** newClientOrderId único (máx. 36 caracteres de [.A-Z:/a-z0-9_-]) para poder consultar la orden. */
export declare function newClientOrderId(side: 'BUY' | 'SELL'): string;
type Sizing = {
    quantity: string;
} | {
    quoteOrderQty: string;
};
export declare class BinanceRestClient {
    private apiKey;
    private apiSecret;
    private baseUrl;
    private http;
    private sleep;
    private timeOffsetMs;
    private lastTimeSyncAt;
    private filtersCache;
    constructor(http?: HttpClient, options?: {
        sleep?: (ms: number) => Promise<void>;
    });
    get serverTimeOffsetMs(): number;
    /**
     * GET /api/v3/time: desfase con la hora del servidor, tomando el punto medio de la petición.
     * Binance rechaza (-1021) timestamps más de 1 s por delante del servidor o más viejos que recvWindow.
     */
    syncServerTime(): Promise<number>;
    private sign;
    /**
     * Petición firmada con recvWindow y timestamp corregido por el desfase. La firma se calcula sobre
     * el query ya codificado (percent-encoding), como exige Binance desde 2026-01-15.
     * Ante -1021 resincroniza la hora y reintenta una vez (la orden no llegó al motor: es seguro).
     */
    private signedRequest;
    /** Olvida los filtros guardados del par: la próxima consulta vuelve a leer /exchangeInfo (Binance puede cambiarlos). */
    invalidateSymbolFilters(symbol: string): void;
    /**
     * Filtros del par desde /exchangeInfo (con caché). Las órdenes MARKET deben cumplir LOT_SIZE y
     * MARKET_LOT_SIZE (se toma el paso más grueso y los límites más estrictos); el mínimo nocional solo
     * cuenta si NOTIONAL.applyMinToMarket (o MIN_NOTIONAL.applyToMarket) es true.
     */
    getSymbolFilters(symbol: string): Promise<SymbolFilters>;
    getAccountBalance(): Promise<any>;
    /** Saldo libre por activo (lo bloqueado en órdenes abiertas no se puede vender). */
    getFreeBalances(): Promise<Map<string, number>>;
    /** Último precio del par (público, sin firma). */
    getPrice(symbol: string): Promise<number>;
    /**
     * Precio medio con el que Binance valora las órdenes MARKET en los filtros NOTIONAL/MIN_NOTIONAL
     * (GET /api/v3/avgPrice: media de los últimos avgPriceMins minutos).
     */
    getAvgPrice(symbol: string): Promise<number>;
    /** GET /api/v3/order por orderId. null si Binance no la tiene (-2013). */
    getOrder(symbol: string, orderId: number): Promise<any | null>;
    /** GET /api/v3/myTrades (por orderId o desde un tradeId), en orden de ejecución. */
    getMyTrades(symbol: string, params: {
        orderId?: number;
        fromId?: number;
    }): Promise<any[]>;
    /** Operaciones de /myTrades -> Execution (con las comisiones valoradas en USDT). */
    tradesToExecution(symbol: string, trades: any[], order?: any): Promise<Execution>;
    /**
     * Compra a mercado por importe: quoteOrderQty = USDT a gastar (lo que asume el backtest, ~15 USDT).
     * Binance calcula la cantidad respetando LOT_SIZE. Si el par no admite quoteOrderQty, se usa
     * quantity = USDT / precio de referencia redondeada al stepSize.
     */
    marketBuy(symbol: string, quoteAmount: number, refPrice: number, clientOrderId?: string): Promise<Execution>;
    /** Venta a mercado de una cantidad ya redondeada al stepSize. */
    marketSell(symbol: string, quantity: string): Promise<Execution>;
    /**
     * POST /api/v3/order type=MARKET, newOrderRespType=FULL. Devuelve lo ejecutado de verdad
     * (executedQty, cummulativeQuoteQty, precio medio y comisiones de cada fill). Si la respuesta no llega
     * (estado desconocido) consulta la orden por su newClientOrderId antes de darla por fallida.
     */
    placeMarketOrder(symbol: string, side: 'BUY' | 'SELL', sizing: Sizing, clientOrderId?: string): Promise<Execution>;
    /**
     * Busca una orden por newClientOrderId (GET /api/v3/order) y, si se ejecutó, sus fills con comisiones
     * (GET /api/v3/myTrades?orderId). Devuelve null si Binance no la tiene; lanza OrderStatusUnknownError
     * si no se pudo averiguar.
     */
    lookupOrder(symbol: string, clientOrderId: string): Promise<Execution | null>;
    private recoverOrder;
    /** Respuesta FULL -> Execution, valorando en USDT las comisiones cobradas en otro activo (BNB). */
    private toExecution;
    /**
     * Cancela una orden activa.
     */
    cancelOrder(symbol: string, orderId: number): Promise<any>;
}
export {};
//# sourceMappingURL=rest-client.d.ts.map