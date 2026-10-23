// Dobles de prueba (sin red) para BinanceWSClient: socket, REST, cerebro Python y Telegram.
import './setup-env';
import { BinanceWSClient, SocketLike, WSClientDeps } from '../src/api/ws-client';
import { Execution, SymbolFilters, floorToStep, parseExecution, tradesToResponse } from '../src/api/execution';

export const DOGE: SymbolFilters = {
    baseAsset: 'DOGE', quoteAsset: 'USDT', stepSize: '1.00000000', minQty: 1, maxQty: 9000000,
    tickSize: '0.00001000', minNotional: 1, quoteOrderQtyMarketAllowed: true
};
export const BTC: SymbolFilters = {
    baseAsset: 'BTC', quoteAsset: 'USDT', stepSize: '0.00001000', minQty: 0.00001, maxQty: 9000,
    tickSize: '0.01000000', minNotional: 5, quoteOrderQtyMarketAllowed: true
};

// open_time de una vela de 15 min
export const T0 = 1_800_000_000_000 - (1_800_000_000_000 % 900_000);
export const CANDLE = 900_000;

export function deferred<T = void>() {
    let resolve!: (value: T) => void;
    let reject!: (error: any) => void;
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

export const flush = async (times = 5) => {
    for (let i = 0; i < times; i++) await new Promise(resolve => setImmediate(resolve));
};

/** Error con la forma de axios y el cuerpo {code, msg} de Binance. */
export function binanceHttpError(code: number, msg: string, status = 400): any {
    const error: any = new Error(`Request failed with status code ${status}`);
    error.response = { status, data: { code, msg } };
    return error;
}

/** Respuesta FULL de POST /api/v3/order con un fill. */
export function fullResponse(o: {
    symbol: string; orderId: number; side: 'BUY' | 'SELL'; qty: number; price: number;
    fee: number; feeAsset: string; status?: string; clientOrderId?: string;
}) {
    return {
        symbol: o.symbol, orderId: o.orderId, orderListId: -1, clientOrderId: o.clientOrderId ?? `cid${o.orderId}`,
        transactTime: 1, price: '0.00000000', origQty: o.qty.toFixed(8), executedQty: o.qty.toFixed(8),
        origQuoteOrderQty: '0.00000000', cummulativeQuoteQty: (o.qty * o.price).toFixed(8),
        status: o.status ?? 'FILLED', timeInForce: 'GTC', type: 'MARKET', side: o.side,
        workingTime: 1, selfTradePreventionMode: 'NONE',
        fills: o.qty > 0 ? [{
            price: o.price.toFixed(8), qty: o.qty.toFixed(8), commission: o.fee.toFixed(8),
            commissionAsset: o.feeAsset, tradeId: o.orderId * 10
        }] : []
    };
}

export class FakeSocket implements SocketLike {
    handlers = new Map<string, (...args: any[]) => any>();
    closed = false;
    terminated = false;
    asksAtCreation = 0;   // preguntas al cerebro hechas antes de abrir este socket
    constructor(public url: string) {}
    on(event: string, listener: (...args: any[]) => any) {
        this.handlers.set(event, listener);
        return this;
    }
    close() {
        this.closed = true;
    }
    terminate() {
        this.terminated = true;
    }
    emit(event: string, ...args: any[]): any {
        return this.handlers.get(event)?.(...args);
    }
}

export class FakeBrain {
    asks: { type: string; payload: any }[] = [];
    signals: any[] = [];
    openTrades: any[] = [];
    pendingTrades: any[] = [];
    ledgerOpenResult: any = { status: 'logged' };
    ledgerCloseResult: any = { status: 'updated' };
    ledgerPendingResult: any = { status: 'logged' };
    ledgerCancelResult: any = { status: 'updated' };
    async ask(type: string, payload: any = {}): Promise<any> {
        this.asks.push({ type, payload });
        switch (type) {
            case 'evaluate': return this.signals.shift() ?? { action: 'HOLD' };
            case 'sync_positions': return this.openTrades;
            case 'sync_pending': return this.pendingTrades;
            case 'ledger_open':
                // Como server.py: la compra queda OPEN (su fila PENDING, si la había, deja de estar pendiente)
                if (this.ledgerOpenResult?.status === 'logged') {
                    this.pendingTrades = this.pendingTrades.filter(t => t.client_order_id !== payload.client_order_id);
                    this.openTrades = [...this.openTrades, { ...payload, status: 'OPEN', timestamp: Date.now() }];
                }
                return this.ledgerOpenResult;
            case 'ledger_close': return this.ledgerCloseResult;
            case 'ledger_pending': return this.ledgerPendingResult;
            case 'ledger_cancel': return this.ledgerCancelResult;
            default: return {};
        }
    }
    of(type: string) {
        return this.asks.filter(a => a.type === type);
    }
}

export class FakeTelegram {
    messages: string[] = [];
    async sendMessage(message: string) {
        this.messages.push(message);
    }
}

type SellHook = (symbol: string, qty: string, n: number) => Promise<Execution | void> | Execution | void;

export class FakeRest {
    filters: Record<string, SymbolFilters> = { DOGEUSDT: DOGE, BTCUSDT: BTC };
    buys: { symbol: string; quote: number; ref: number; clientOrderId?: string }[] = [];
    invalidations: string[] = [];
    sells: { symbol: string; qty: string }[] = [];
    lookups: { symbol: string; clientOrderId: string }[] = [];
    // Precio de ejecución por símbolo (si no hay, el de referencia de la señal / 0.0825 en ventas)
    fillPrice: Record<string, number> = {};
    // Activo de la comisión de compra: 'base' (DOGE), 'quote' (USDT) o 'BNB'
    buyFeeAsset: 'base' | 'quote' | 'BNB' = 'base';
    feeRate = 0.001;
    bnbPrice = 600;
    // Ganchos para retrasar o fallar órdenes
    buyHook: ((symbol: string, clientOrderId?: string) => Promise<Execution | void> | Execution | void) | null = null;
    sellHook: SellHook | null = null;
    // Respuestas de lookupOrder en orden (un Error se lanza); vacía -> lookupResult
    lookupQueue: (Execution | null | Error)[] = [];
    lookupResult: Execution | null = null;
    // Precio medio de Binance (avgPrice) por símbolo; si no hay, el de fillPrice o 0.08
    avgPrice: Record<string, number> = {};
    avgPriceCalls = 0;
    // Órdenes de compra por orderId para GET /v3/order (null = no existe); sin entrada -> FILLED
    orders: Record<number, any> = {};
    // Operaciones de la cuenta (para /myTrades)
    trades: any[] = [];
    balances = new Map<string, number>([['DOGE', 1_000_000], ['BTC', 10], ['USDT', 10_000]]);
    balanceError: any = null;
    private nextId = 1000;

    async getSymbolFilters(symbol: string): Promise<SymbolFilters> {
        const f = this.filters[symbol];
        if (!f) throw new Error(`sin filtros para ${symbol}`);
        return f;
    }

    invalidateSymbolFilters(symbol: string): void {
        this.invalidations.push(symbol);
    }

    async marketBuy(symbol: string, quoteAmount: number, refPrice: number, clientOrderId?: string): Promise<Execution> {
        this.buys.push(clientOrderId === undefined ? { symbol, quote: quoteAmount, ref: refPrice }
                                                   : { symbol, quote: quoteAmount, ref: refPrice, clientOrderId });
        if (this.buyHook) {
            const custom = await this.buyHook(symbol, clientOrderId);
            if (custom) return custom;
        }
        const f = await this.getSymbolFilters(symbol);
        const price = this.fillPrice[symbol] ?? refPrice;
        const qty = Number(floorToStep(quoteAmount / price, f.stepSize));
        const feeAsset = this.buyFeeAsset === 'base' ? f.baseAsset : this.buyFeeAsset === 'quote' ? f.quoteAsset : 'BNB';
        const fee = this.buyFeeAsset === 'base' ? qty * this.feeRate
            : this.buyFeeAsset === 'quote' ? qty * price * this.feeRate : qty * price * this.feeRate / this.bnbPrice;
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'BUY', qty, price, fee, feeAsset });
        return parseExecution(resp, f.baseAsset, f.quoteAsset, { BNB: this.bnbPrice });
    }

    async marketSell(symbol: string, quantity: string): Promise<Execution> {
        this.sells.push({ symbol, qty: quantity });
        if (this.sellHook) {
            const custom = await this.sellHook(symbol, quantity, this.sells.length);
            if (custom) return custom;
        }
        return this.sellExecution(symbol, Number(quantity));
    }

    sellExecution(symbol: string, qty: number, status = 'FILLED'): Execution {
        const f = this.filters[symbol]!;
        const price = this.fillPrice[symbol] ?? 0.0825;
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'SELL', qty, price, fee: qty * price * this.feeRate,
            feeAsset: f.quoteAsset, status });
        return parseExecution(resp, f.baseAsset, f.quoteAsset);
    }

    async getFreeBalances(): Promise<Map<string, number>> {
        if (this.balanceError) throw this.balanceError;
        return new Map(this.balances);
    }

    async getPrice(symbol: string): Promise<number> {
        return this.fillPrice[symbol] ?? 0.08;
    }

    async getAvgPrice(symbol: string): Promise<number> {
        this.avgPriceCalls++;
        return this.avgPrice[symbol] ?? this.fillPrice[symbol] ?? 0.08;
    }

    async lookupOrder(symbol: string, clientOrderId: string): Promise<Execution | null> {
        this.lookups.push({ symbol, clientOrderId });
        if (this.lookupQueue.length) {
            const next = this.lookupQueue.shift()!;
            if (next instanceof Error) throw next;
            return next;
        }
        return this.lookupResult;
    }

    async getOrder(_symbol: string, orderId: number): Promise<any | null> {
        if (orderId in this.orders) return this.orders[orderId];
        return { orderId, status: 'FILLED', executedQty: '1.00000000' };
    }

    async getMyTrades(_symbol: string, params: { orderId?: number; fromId?: number }): Promise<any[]> {
        return this.trades.filter(t => (params.orderId === undefined || t.orderId === params.orderId) &&
                                       (params.fromId === undefined || t.id >= params.fromId));
    }

    async tradesToExecution(symbol: string, trades: any[], order: any = {}): Promise<Execution> {
        const f = await this.getSymbolFilters(symbol);
        return parseExecution(tradesToResponse(trades, order), f.baseAsset, f.quoteAsset, { BNB: this.bnbPrice });
    }

    /** Ejecución de compra como la daría Binance (para adoptar una compra sin confirmar). */
    buyExecution(symbol: string, qty: number, price: number): Execution {
        const f = this.filters[symbol]!;
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'BUY', qty, price, fee: qty * this.feeRate, feeAsset: f.baseAsset });
        return parseExecution(resp, f.baseAsset, f.quoteAsset);
    }
}

/** Operación de /myTrades. */
export function trade(o: { id: number; orderId: number; isBuyer: boolean; qty: number; price: number; fee?: number; feeAsset?: string }) {
    return {
        symbol: 'DOGEUSDT', id: o.id, orderId: o.orderId, orderListId: -1, price: o.price.toFixed(8), qty: o.qty.toFixed(8),
        quoteQty: (o.qty * o.price).toFixed(8), commission: (o.fee ?? 0).toFixed(8), commissionAsset: o.feeAsset ?? 'USDT',
        time: o.id, isBuyer: o.isBuyer, isMaker: false, isBestMatch: true
    };
}

export function klineMessage(symbol: string, openTime: number, close: number, closed: boolean) {
    return Buffer.from(JSON.stringify({
        stream: `${symbol.toLowerCase()}@kline_15m`,
        data: {
            e: 'kline', E: openTime + 1000, s: symbol,
            k: { t: openTime, T: openTime + CANDLE - 1, s: symbol, i: '15m', o: String(close), h: String(close),
                 l: String(close), c: String(close), v: '100', x: closed }
        }
    }));
}

/** Cliente con dobles; send() emite una vela en el último socket y devuelve la promesa del handler. */
export async function makeClient(roster = ['DOGEUSDT', 'BTCUSDT'], setup?: (h: { rest: FakeRest; brain: FakeBrain }) => void,
                                 extra: Partial<WSClientDeps> = {}) {
    const rest = new FakeRest();
    const brain = new FakeBrain();
    const telegram = new FakeTelegram();
    const sockets: FakeSocket[] = [];
    setup?.({ rest, brain });
    const client = new BinanceWSClient(roster, 15, {
        rest, brain, telegram, ...extra,
        sleep: async () => {},
        createSocket: (url: string) => {
            const socket = new FakeSocket(url);
            socket.asksAtCreation = brain.asks.length;
            sockets.push(socket);
            return socket;
        }
    });
    await client.start();
    const send = (symbol: string, openTime: number, close: number, closed: boolean): Promise<void> =>
        sockets[sockets.length - 1]!.emit('message', klineMessage(symbol, openTime, close, closed));
    return { client, rest, brain, telegram, sockets, send };
}

export const BUY = (entry: number, tp: number, sl: number) => ({ action: 'BUY', entry_price: entry, take_profit: tp, stop_loss: sl });
