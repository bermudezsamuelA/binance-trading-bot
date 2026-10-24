import axios from 'axios';
import * as crypto from 'crypto';
import { config } from '../config/env';
import type { FlexibleProduct } from './earn';
import {
    Execution, SymbolFilters, floorToStep, foreignFeeAssets, isTradable, parseExecution, tradesToResponse
} from './execution';

// Validez de las peticiones firmadas. Binance usa 5000 ms si no se envía; el máximo es 60000.
export const RECV_WINDOW_MS = 10000;
// Sin timeout, una petición colgada bloquearía la venta para siempre
const REQUEST_TIMEOUT_MS = 10000;
// Se vuelve a pedir la hora del servidor cada hora (deriva del reloj local) y siempre tras un -1021
const TIME_RESYNC_MS = 60 * 60 * 1000;
// Esperas al consultar una orden cuyo resultado no llegó (timeout, HTTP 5xx, -1006/-1007)
const RECOVERY_WAITS_MS = [500, 1500, 3000];

// Códigos de error de Binance Spot (https://developers.binance.com/docs/binance-spot-api-docs/errors)
export const ERR_UNEXPECTED_RESP = -1006; // estado de ejecución desconocido
export const ERR_TIMEOUT = -1007;         // estado de ejecución desconocido
export const ERR_INVALID_MESSAGE = -1013; // rechazo antes del motor (p. ej. "Filter failure: NOTIONAL")
export const ERR_TIMESTAMP = -1021;       // timestamp fuera de recvWindow o adelantado al servidor
export const ERR_NEW_ORDER_REJECTED = -2010;
export const ERR_NO_SUCH_ORDER = -2013;

export interface HttpClient {
    get(url: string, config?: any): Promise<{ data: any }>;
    post(url: string, data?: any, config?: any): Promise<{ data: any }>;
    delete(url: string, config?: any): Promise<{ data: any }>;
}

/** Código y mensaje de Binance ({code, msg}) a partir de un error de axios o de cualquier otro error. */
export function binanceError(error: any): { code?: number; msg: string; httpStatus?: number } {
    const data = error?.response?.data;
    const result: { code?: number; msg: string; httpStatus?: number } = {
        msg: data?.msg ?? error?.message ?? String(error)
    };
    if (typeof data?.code === 'number') result.code = data.code;
    if (typeof error?.response?.status === 'number') result.httpStatus = error.response.status;
    return result;
}

/** -2010 "Account has insufficient balance for requested action." */
export function isInsufficientBalance(error: any): boolean {
    const e = binanceError(error);
    return e.code === ERR_NEW_ORDER_REJECTED && /insufficient balance/i.test(e.msg);
}

/** -1013 "Filter failure: NOTIONAL / MIN_NOTIONAL / LOT_SIZE / MARKET_LOT_SIZE": la cantidad no es negociable. */
export function isFilterFailure(error: any): boolean {
    const e = binanceError(error);
    return e.code === ERR_INVALID_MESSAGE && /Filter failure: (NOTIONAL|MIN_NOTIONAL|LOT_SIZE|MARKET_LOT_SIZE)\b/.test(e.msg);
}

/** -1013 por LOT_SIZE / MARKET_LOT_SIZE: el paso o los límites de cantidad guardados pueden estar desactualizados. */
export function isLotSizeFailure(error: any): boolean {
    const e = binanceError(error);
    return e.code === ERR_INVALID_MESSAGE && /Filter failure: (MARKET_)?LOT_SIZE\b/.test(e.msg);
}

/**
 * Sin respuesta, HTTP 5xx o -1006/-1007: según la documentación la orden pudo ejecutarse,
 * no se puede tratar como fallo sin consultarla.
 */
export function isUnknownStatus(error: any): boolean {
    if (error instanceof OrderStatusUnknownError) return true;
    const e = binanceError(error);
    if (e.code === ERR_UNEXPECTED_RESP || e.code === ERR_TIMEOUT) return true;
    if (e.httpStatus !== undefined) return e.httpStatus >= 500;
    return !!(error?.request || error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT' || error?.code === 'ECONNRESET');
}

/** La orden se envió pero no se pudo confirmar si se ejecutó. */
export class OrderStatusUnknownError extends Error {
    public readonly symbol: string;
    public readonly clientOrderId: string;
    constructor(symbol: string, clientOrderId: string, cause: unknown) {
        super(`Estado desconocido de la orden ${clientOrderId} (${symbol}): ${binanceError(cause).msg}`);
        this.name = 'OrderStatusUnknownError';
        this.symbol = symbol;
        this.clientOrderId = clientOrderId;
    }
}

/**
 * La orden quedó sin respuesta y al consultarla Binance dijo que no existe (-2013 dos veces). Puede aparecer tarde
 * (-1007: el motor la procesa después), así que quien la recibe debe volver a consultarla antes de reenviarla.
 */
export class OrderNotFoundError extends Error {
    public readonly symbol: string;
    public readonly clientOrderId: string;
    constructor(symbol: string, clientOrderId: string, cause: unknown) {
        super(`La orden ${clientOrderId} (${symbol}) no aparece en Binance tras quedar sin respuesta: ${binanceError(cause).msg}`);
        this.name = 'OrderNotFoundError';
        this.symbol = symbol;
        this.clientOrderId = clientOrderId;
    }
}

/** newClientOrderId único (máx. 36 caracteres de [.A-Z:/a-z0-9_-]) para poder consultar la orden. */
export function newClientOrderId(side: 'BUY' | 'SELL'): string {
    return `bot_${side === 'BUY' ? 'b' : 's'}_${Date.now().toString(36)}_${crypto.randomBytes(4).toString('hex')}`;
}

type Sizing = { quantity: string } | { quoteOrderQty: string };

export class BinanceRestClient {
    private apiKey = config.API_KEY;
    private apiSecret = config.API_SECRET;
    private baseUrl = config.REST_URL;
    private http: HttpClient;
    private sleep: (ms: number) => Promise<void>;

    // Desfase hora del servidor − hora local (ms): se suma al timestamp de cada petición firmada
    private timeOffsetMs = 0;
    private lastTimeSyncAt = 0;

    private filtersCache = new Map<string, SymbolFilters>();

    constructor(http: HttpClient = axios, options: { sleep?: (ms: number) => Promise<void> } = {}) {
        this.http = http;
        this.sleep = options.sleep ?? (ms => new Promise(resolve => setTimeout(resolve, ms)));
    }

    public get serverTimeOffsetMs(): number {
        return this.timeOffsetMs;
    }

    /**
     * GET /api/v3/time: desfase con la hora del servidor, tomando el punto medio de la petición.
     * Binance rechaza (-1021) timestamps más de 1 s por delante del servidor o más viejos que recvWindow.
     */
    public async syncServerTime(): Promise<number> {
        const t0 = Date.now();
        const response = await this.http.get(`${this.baseUrl}/v3/time`, { timeout: REQUEST_TIMEOUT_MS });
        const t1 = Date.now();
        this.timeOffsetMs = Number(response.data.serverTime) - Math.round((t0 + t1) / 2);
        this.lastTimeSyncAt = t1;
        return this.timeOffsetMs;
    }

    private sign(queryString: string): string {
        return crypto
            .createHmac('sha256', this.apiSecret)
            .update(queryString)
            .digest('hex');
    }

    /**
     * Petición firmada con recvWindow y timestamp corregido por el desfase. La firma se calcula sobre
     * el query ya codificado (percent-encoding), como exige Binance desde 2026-01-15.
     * Ante -1021 resincroniza la hora y reintenta una vez (la orden no llegó al motor: es seguro).
     */
    private async signedRequest(method: 'get' | 'post' | 'delete', path: string,
                                params: Record<string, string | number | boolean>, retried = false): Promise<any> {
        if (Date.now() - this.lastTimeSyncAt > TIME_RESYNC_MS) {
            try {
                await this.syncServerTime();
            } catch (error: any) {
                // Sin hora del servidor se sigue con el desfase anterior; un -1021 volverá a intentarlo
                this.lastTimeSyncAt = Date.now();
                console.warn(`[REST] No se pudo leer la hora del servidor: ${binanceError(error).msg}`);
            }
        }
        const query = Object.entries({ ...params, recvWindow: RECV_WINDOW_MS, timestamp: Date.now() + this.timeOffsetMs })
            .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
            .join('&');
        // Las rutas /sapi/ (cuenta, p. ej. bnbBurn) cuelgan de la raíz del host, no de /api
        const base = path.startsWith('/sapi/') ? this.baseUrl.replace(/\/api$/, '') : this.baseUrl;
        const url = `${base}${path}?${query}&signature=${this.sign(query)}`;
        const options = { headers: { 'X-MBX-APIKEY': this.apiKey }, timeout: REQUEST_TIMEOUT_MS };
        try {
            const response = method === 'post'
                ? await this.http.post(url, null, options)
                : await this.http[method](url, options);
            return response.data;
        } catch (error: any) {
            if (!retried && binanceError(error).code === ERR_TIMESTAMP) {
                console.warn(`[REST] -1021 (timestamp fuera de recvWindow): se resincroniza la hora y se reintenta.`);
                await this.syncServerTime();
                return this.signedRequest(method, path, params, true);
            }
            throw error;
        }
    }

    /** Olvida los filtros guardados del par: la próxima consulta vuelve a leer /exchangeInfo (Binance puede cambiarlos). */
    public invalidateSymbolFilters(symbol: string): void {
        this.filtersCache.delete(symbol.toUpperCase());
    }

    /**
     * Filtros del par desde /exchangeInfo (con caché). Las órdenes MARKET deben cumplir LOT_SIZE y
     * MARKET_LOT_SIZE (se toma el paso más grueso y los límites más estrictos); el mínimo nocional solo
     * cuenta si NOTIONAL.applyMinToMarket (o MIN_NOTIONAL.applyToMarket) es true.
     */
    public async getSymbolFilters(symbol: string): Promise<SymbolFilters> {
        const key = symbol.toUpperCase();
        const cached = this.filtersCache.get(key);
        if (cached) return cached;

        const response = await this.http.get(`${this.baseUrl}/v3/exchangeInfo?symbol=${key}`, { timeout: REQUEST_TIMEOUT_MS });
        const info = response.data.symbols[0];
        const filters: any[] = info.filters;
        const lot = filters.find(f => f.filterType === 'LOT_SIZE');
        const marketLot = filters.find(f => f.filterType === 'MARKET_LOT_SIZE');
        const price = filters.find(f => f.filterType === 'PRICE_FILTER');
        const notional = filters.find(f => f.filterType === 'NOTIONAL');
        const minNotional = filters.find(f => f.filterType === 'MIN_NOTIONAL');

        const num = (v: any) => parseFloat(v ?? '0') || 0;
        let stepSize: string = lot?.stepSize ?? '0.00000001';
        if (marketLot && num(marketLot.stepSize) > num(stepSize)) stepSize = marketLot.stepSize;
        const maxQtys = [num(lot?.maxQty), num(marketLot?.maxQty)].filter(v => v > 0);
        let minNotionalValue = 0;
        if (notional) minNotionalValue = notional.applyMinToMarket ? num(notional.minNotional) : 0;
        else if (minNotional) minNotionalValue = minNotional.applyToMarket ? num(minNotional.minNotional) : 0;

        const result: SymbolFilters = {
            baseAsset: info.baseAsset,
            quoteAsset: info.quoteAsset,
            stepSize,
            minQty: Math.max(num(lot?.minQty), num(marketLot?.minQty)),
            maxQty: maxQtys.length ? Math.min(...maxQtys) : 0,
            tickSize: price?.tickSize ?? '0.00000001',
            minNotional: minNotionalValue,
            quoteOrderQtyMarketAllowed: info.quoteOrderQtyMarketAllowed !== false
        };
        this.filtersCache.set(key, result);
        return result;
    }

    public async getAccountBalance() {
        return this.signedRequest('get', '/v3/account', { omitZeroBalances: true });
    }

    /** Saldo libre por activo (lo bloqueado en órdenes abiertas no se puede vender). */
    public async getFreeBalances(): Promise<Map<string, number>> {
        const account = await this.getAccountBalance();
        const balances = new Map<string, number>();
        for (const b of account.balances ?? []) balances.set(b.asset, parseFloat(b.free) || 0);
        return balances;
    }

    /** GET /sapi/v1/simple-earn/flexible/list: el producto flexible del activo (null si no hay). Solo mainnet. */
    public async getFlexibleProduct(asset: string): Promise<FlexibleProduct | null> {
        const data = await this.signedRequest('get', '/sapi/v1/simple-earn/flexible/list', { asset, current: 1, size: 10 });
        const row = (data?.rows ?? []).find((r: any) => r.asset === asset);
        if (!row) return null;
        return {
            productId: String(row.productId),
            apr: parseFloat(row.latestAnnualPercentageRate) || 0,
            minPurchase: parseFloat(row.minPurchaseAmount) || 0,
            canPurchase: row.canPurchase !== false,
            canRedeem: row.canRedeem !== false,
        };
    }

    /** GET /sapi/v1/simple-earn/flexible/position: cuánto del activo hay en Simple Earn flexible. */
    public async getFlexiblePosition(asset: string): Promise<number> {
        const data = await this.signedRequest('get', '/sapi/v1/simple-earn/flexible/position', { asset, current: 1, size: 10 });
        return (data?.rows ?? []).filter((r: any) => r.asset === asset)
            .reduce((sum: number, r: any) => sum + (parseFloat(r.totalAmount) || 0), 0);
    }

    /** POST /sapi/v1/simple-earn/flexible/subscribe desde la cuenta spot. */
    public async subscribeFlexible(productId: string, amount: string): Promise<void> {
        const data = await this.signedRequest('post', '/sapi/v1/simple-earn/flexible/subscribe', { productId, amount, sourceAccount: 'SPOT' });
        if (data?.success === false) throw new Error(`Simple Earn rechazó la suscripción de ${amount}`);
    }

    /** POST /sapi/v1/simple-earn/flexible/redeem hacia la cuenta spot. */
    public async redeemFlexible(productId: string, amount: string): Promise<void> {
        const data = await this.signedRequest('post', '/sapi/v1/simple-earn/flexible/redeem', { productId, amount, destAccount: 'SPOT' });
        if (data?.success === false) throw new Error(`Simple Earn rechazó el rescate de ${amount}`);
    }

    /** GET /sapi/v1/bnbBurn: si la cuenta paga las comisiones de spot con BNB (solo mainnet; la testnet no tiene /sapi). */
    public async getBnbBurnStatus(): Promise<{ spotBNBBurn: boolean }> {
        const data = await this.signedRequest('get', '/sapi/v1/bnbBurn', {});
        return { spotBNBBurn: data?.spotBNBBurn === true || data?.spotBNBBurn === 'true' };
    }

    /** Último precio del par (público, sin firma). */
    public async getPrice(symbol: string): Promise<number> {
        const response = await this.http.get(`${this.baseUrl}/v3/ticker/price?symbol=${symbol.toUpperCase()}`, { timeout: REQUEST_TIMEOUT_MS });
        const price = parseFloat(response.data.price);
        if (!Number.isFinite(price)) throw new Error(`Precio no válido para ${symbol}`);
        return price;
    }

    /**
     * Precio medio con el que Binance valora las órdenes MARKET en los filtros NOTIONAL/MIN_NOTIONAL
     * (GET /api/v3/avgPrice: media de los últimos avgPriceMins minutos).
     */
    public async getAvgPrice(symbol: string): Promise<number> {
        const response = await this.http.get(`${this.baseUrl}/v3/avgPrice?symbol=${symbol.toUpperCase()}`, { timeout: REQUEST_TIMEOUT_MS });
        const price = parseFloat(response.data.price);
        if (!Number.isFinite(price)) throw new Error(`Precio medio no válido para ${symbol}`);
        return price;
    }

    /** GET /api/v3/order por orderId. null si Binance no la tiene (-2013). */
    public async getOrder(symbol: string, orderId: number): Promise<any | null> {
        try {
            return await this.signedRequest('get', '/v3/order', { symbol: symbol.toUpperCase(), orderId });
        } catch (error: any) {
            if (binanceError(error).code === ERR_NO_SUCH_ORDER) return null;
            throw error;
        }
    }

    /** GET /api/v3/myTrades (por orderId o desde un tradeId), en orden de ejecución. */
    public async getMyTrades(symbol: string, params: { orderId?: number; fromId?: number }): Promise<any[]> {
        const query: Record<string, string | number> = { symbol: symbol.toUpperCase(), limit: 1000 };
        if (params.orderId !== undefined) query.orderId = params.orderId;
        if (params.fromId !== undefined) query.fromId = params.fromId;
        const trades: any[] = await this.signedRequest('get', '/v3/myTrades', query);
        return [...trades].sort((a, b) => Number(a.id) - Number(b.id));
    }

    /** Operaciones de /myTrades -> Execution (con las comisiones valoradas en USDT). */
    public async tradesToExecution(symbol: string, trades: any[], order: any = {}): Promise<Execution> {
        const filters = await this.getSymbolFilters(symbol);
        return this.toExecution(tradesToResponse(trades, order), filters);
    }

    /**
     * Compra a mercado por importe: quoteOrderQty = USDT a gastar (lo que asume el backtest, ~15 USDT).
     * Binance calcula la cantidad respetando LOT_SIZE. Si el par no admite quoteOrderQty, se usa
     * quantity = USDT / precio de referencia redondeada al stepSize.
     */
    public async marketBuy(symbol: string, quoteAmount: number, refPrice: number,
                           clientOrderId: string = newClientOrderId('BUY')): Promise<Execution> {
        const f = await this.getSymbolFilters(symbol);
        if (f.quoteOrderQtyMarketAllowed) {
            return this.placeMarketOrder(symbol, 'BUY', { quoteOrderQty: quoteAmount.toFixed(2) }, clientOrderId);
        }
        const quantity = floorToStep(quoteAmount / refPrice, f.stepSize);
        if (!isTradable(parseFloat(quantity), refPrice, f)) {
            throw new Error(`Compra ${symbol} por debajo del mínimo de Binance (${quantity} @ ${refPrice})`);
        }
        return this.placeMarketOrder(symbol, 'BUY', { quantity }, clientOrderId);
    }

    /** Venta a mercado de una cantidad ya redondeada al stepSize. */
    public async marketSell(symbol: string, quantity: string): Promise<Execution> {
        return this.placeMarketOrder(symbol, 'SELL', { quantity });
    }

    /**
     * POST /api/v3/order type=MARKET, newOrderRespType=FULL. Devuelve lo ejecutado de verdad
     * (executedQty, cummulativeQuoteQty, precio medio y comisiones de cada fill). Si la respuesta no llega
     * (estado desconocido) consulta la orden por su newClientOrderId antes de darla por fallida.
     */
    public async placeMarketOrder(symbol: string, side: 'BUY' | 'SELL', sizing: Sizing,
                                  clientOrderId: string = newClientOrderId(side)): Promise<Execution> {
        const key = symbol.toUpperCase();
        const filters = await this.getSymbolFilters(key);
        const params = {
            symbol: key,
            side,
            type: 'MARKET',
            ...sizing,
            newOrderRespType: 'FULL',
            newClientOrderId: clientOrderId
        };
        let response: any;
        try {
            response = await this.signedRequest('post', '/v3/order', params);
        } catch (error: any) {
            if (!isUnknownStatus(error)) {
                console.error(`Error colocando orden ${side} ${key}:`, error.response?.data || error.message);
                throw error;
            }
            console.warn(`[REST] Orden ${side} ${key} sin respuesta (${binanceError(error).msg}); se consulta ${clientOrderId}...`);
            response = await this.recoverOrder(key, clientOrderId, error);
            // Binance no la tiene (por ahora): quien llama la vuelve a consultar antes de reenviar
            if (response === null) throw new OrderNotFoundError(key, clientOrderId, error);
        }
        return this.toExecution(response, filters);
    }

    /**
     * Busca una orden por newClientOrderId (GET /api/v3/order) y, si se ejecutó, sus fills con comisiones
     * (GET /api/v3/myTrades?orderId). Devuelve null si Binance no la tiene; lanza OrderStatusUnknownError
     * si no se pudo averiguar.
     */
    public async lookupOrder(symbol: string, clientOrderId: string): Promise<Execution | null> {
        const key = symbol.toUpperCase();
        const filters = await this.getSymbolFilters(key);
        const response = await this.recoverOrder(key, clientOrderId, new Error('consulta de orden'));
        return response === null ? null : this.toExecution(response, filters);
    }

    private async recoverOrder(symbol: string, clientOrderId: string, cause: unknown): Promise<any | null> {
        let notFound = 0;
        for (const [i, wait] of RECOVERY_WAITS_MS.entries()) {
            const last = i === RECOVERY_WAITS_MS.length - 1;
            await this.sleep(wait);
            let order: any;
            try {
                order = await this.signedRequest('get', '/v3/order', { symbol, origClientOrderId: clientOrderId });
            } catch (error: any) {
                // -2013 dos veces seguidas: la orden no existe (los datos se leen primero de memoria)
                if (binanceError(error).code === ERR_NO_SUCH_ORDER && ++notFound >= 2) return null;
                continue;
            }
            // Una MARKET aún en curso se vuelve a consultar; si en la última consulta sigue PARTIALLY_FILLED,
            // se toma lo ya ejecutado (mejor que darla por desconocida)
            if (['NEW', 'PENDING_NEW'].includes(order.status) || (order.status === 'PARTIALLY_FILLED' && !last)) continue;
            if (!(parseFloat(order.executedQty) > 0)) return { ...order, fills: [] };
            try {
                const trades = await this.getMyTrades(symbol, { orderId: order.orderId });
                // los fills de myTrades cuadran la cantidad con lo realmente ejecutado
                return trades.length ? tradesToResponse(trades, order) : { ...order, fills: [] };
            } catch {
                continue;
            }
        }
        throw new OrderStatusUnknownError(symbol, clientOrderId, cause);
    }

    /** Respuesta FULL -> Execution, valorando en USDT las comisiones cobradas en otro activo (BNB). */
    private async toExecution(response: any, filters: SymbolFilters): Promise<Execution> {
        const prices: Record<string, number> = {};
        for (const asset of foreignFeeAssets(response, filters.baseAsset, filters.quoteAsset)) {
            try {
                prices[asset] = await this.getPrice(`${asset}${filters.quoteAsset}`);
            } catch (error: any) {
                console.warn(`[REST] No se pudo valorar la comisión en ${asset}: ${binanceError(error).msg}`);
            }
        }
        return parseExecution(response, filters.baseAsset, filters.quoteAsset, prices);
    }

    /**
     * Cancela una orden activa.
     */
    public async cancelOrder(symbol: string, orderId: number) {
        try {
            return await this.signedRequest('delete', '/v3/order', { symbol: symbol.toUpperCase(), orderId });
        } catch (error: any) {
            // Error code -2011 means "Unknown order" (it was likely already filled or canceled)
            if (error.response?.data?.code === -2011) {
                console.log(`⚠️ Orden ${orderId} ya no está activa en el libro.`);
            } else {
                console.error(`🔴 Error cancelando orden ${orderId}:`, error.response?.data || error.message);
            }
            throw error;
        }
    }
}
