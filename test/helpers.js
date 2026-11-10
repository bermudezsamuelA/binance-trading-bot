"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BUY = exports.FakeRest = exports.FakeTelegram = exports.FakeBrain = exports.FakeSocket = exports.flush = exports.CANDLE = exports.T0 = exports.BTC = exports.DOGE = void 0;
exports.deferred = deferred;
exports.binanceHttpError = binanceHttpError;
exports.fullResponse = fullResponse;
exports.trade = trade;
exports.klineMessage = klineMessage;
exports.makeClient = makeClient;
// Dobles de prueba (sin red) para BinanceWSClient: socket, REST, cerebro Python y Telegram.
require("./setup-env");
const ws_client_1 = require("../src/api/ws-client");
const execution_1 = require("../src/api/execution");
exports.DOGE = {
    baseAsset: 'DOGE', quoteAsset: 'USDT', stepSize: '1.00000000', minQty: 1, maxQty: 9000000,
    tickSize: '0.00001000', minNotional: 1, quoteOrderQtyMarketAllowed: true
};
exports.BTC = {
    baseAsset: 'BTC', quoteAsset: 'USDT', stepSize: '0.00001000', minQty: 0.00001, maxQty: 9000,
    tickSize: '0.01000000', minNotional: 5, quoteOrderQtyMarketAllowed: true
};
// open_time de una vela de 15 min
exports.T0 = 1_800_000_000_000 - (1_800_000_000_000 % 900_000);
exports.CANDLE = 900_000;
function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}
const flush = async (times = 5) => {
    for (let i = 0; i < times; i++)
        await new Promise(resolve => setImmediate(resolve));
};
exports.flush = flush;
/** Error con la forma de axios y el cuerpo {code, msg} de Binance. */
function binanceHttpError(code, msg, status = 400) {
    const error = new Error(`Request failed with status code ${status}`);
    error.response = { status, data: { code, msg } };
    return error;
}
/** Respuesta FULL de POST /api/v3/order con un fill. */
function fullResponse(o) {
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
class FakeSocket {
    url;
    handlers = new Map();
    closed = false;
    terminated = false;
    asksAtCreation = 0; // preguntas al cerebro hechas antes de abrir este socket
    constructor(url) {
        this.url = url;
    }
    on(event, listener) {
        this.handlers.set(event, listener);
        return this;
    }
    close() {
        this.closed = true;
    }
    terminate() {
        this.terminated = true;
    }
    emit(event, ...args) {
        return this.handlers.get(event)?.(...args);
    }
}
exports.FakeSocket = FakeSocket;
class FakeBrain {
    asks = [];
    signals = [];
    openTrades = [];
    pendingTrades = [];
    ledgerOpenResult = { status: 'logged' };
    ledgerCloseResult = { status: 'updated' };
    ledgerPendingResult = { status: 'logged' };
    ledgerCancelResult = { status: 'updated' };
    async ask(type, payload = {}) {
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
    of(type) {
        return this.asks.filter(a => a.type === type);
    }
}
exports.FakeBrain = FakeBrain;
class FakeTelegram {
    messages = [];
    async sendMessage(message) {
        this.messages.push(message);
    }
}
exports.FakeTelegram = FakeTelegram;
class FakeRest {
    filters = { DOGEUSDT: exports.DOGE, BTCUSDT: exports.BTC };
    buys = [];
    invalidations = [];
    sells = [];
    lookups = [];
    // Precio de ejecución por símbolo (si no hay, el de referencia de la señal / 0.0825 en ventas)
    fillPrice = {};
    // Activo de la comisión de compra: 'base' (DOGE), 'quote' (USDT) o 'BNB'
    buyFeeAsset = 'base';
    feeRate = 0.001;
    bnbPrice = 600;
    // Ganchos para retrasar o fallar órdenes
    buyHook = null;
    sellHook = null;
    // Respuestas de lookupOrder en orden (un Error se lanza); vacía -> lookupResult
    lookupQueue = [];
    lookupResult = null;
    // Precio medio de Binance (avgPrice) por símbolo; si no hay, el de fillPrice o 0.08
    avgPrice = {};
    avgPriceCalls = 0;
    // Órdenes de compra por orderId para GET /v3/order (null = no existe); sin entrada -> FILLED
    orders = {};
    // Operaciones de la cuenta (para /myTrades)
    trades = [];
    balances = new Map([['DOGE', 1_000_000], ['BTC', 10], ['USDT', 10_000]]);
    balanceError = null;
    nextId = 1000;
    async getSymbolFilters(symbol) {
        const f = this.filters[symbol];
        if (!f)
            throw new Error(`sin filtros para ${symbol}`);
        return f;
    }
    invalidateSymbolFilters(symbol) {
        this.invalidations.push(symbol);
    }
    async marketBuy(symbol, quoteAmount, refPrice, clientOrderId) {
        this.buys.push(clientOrderId === undefined ? { symbol, quote: quoteAmount, ref: refPrice }
            : { symbol, quote: quoteAmount, ref: refPrice, clientOrderId });
        if (this.buyHook) {
            const custom = await this.buyHook(symbol, clientOrderId);
            if (custom)
                return custom;
        }
        const f = await this.getSymbolFilters(symbol);
        const price = this.fillPrice[symbol] ?? refPrice;
        const qty = Number((0, execution_1.floorToStep)(quoteAmount / price, f.stepSize));
        const feeAsset = this.buyFeeAsset === 'base' ? f.baseAsset : this.buyFeeAsset === 'quote' ? f.quoteAsset : 'BNB';
        const fee = this.buyFeeAsset === 'base' ? qty * this.feeRate
            : this.buyFeeAsset === 'quote' ? qty * price * this.feeRate : qty * price * this.feeRate / this.bnbPrice;
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'BUY', qty, price, fee, feeAsset });
        return (0, execution_1.parseExecution)(resp, f.baseAsset, f.quoteAsset, { BNB: this.bnbPrice });
    }
    async marketSell(symbol, quantity) {
        this.sells.push({ symbol, qty: quantity });
        if (this.sellHook) {
            const custom = await this.sellHook(symbol, quantity, this.sells.length);
            if (custom)
                return custom;
        }
        return this.sellExecution(symbol, Number(quantity));
    }
    sellExecution(symbol, qty, status = 'FILLED') {
        const f = this.filters[symbol];
        const price = this.fillPrice[symbol] ?? 0.0825;
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'SELL', qty, price, fee: qty * price * this.feeRate,
            feeAsset: f.quoteAsset, status });
        return (0, execution_1.parseExecution)(resp, f.baseAsset, f.quoteAsset);
    }
    async getFreeBalances() {
        if (this.balanceError)
            throw this.balanceError;
        return new Map(this.balances);
    }
    async getPrice(symbol) {
        return this.fillPrice[symbol] ?? 0.08;
    }
    async getAvgPrice(symbol) {
        this.avgPriceCalls++;
        return this.avgPrice[symbol] ?? this.fillPrice[symbol] ?? 0.08;
    }
    async lookupOrder(symbol, clientOrderId) {
        this.lookups.push({ symbol, clientOrderId });
        if (this.lookupQueue.length) {
            const next = this.lookupQueue.shift();
            if (next instanceof Error)
                throw next;
            return next;
        }
        return this.lookupResult;
    }
    async getOrder(_symbol, orderId) {
        if (orderId in this.orders)
            return this.orders[orderId];
        return { orderId, status: 'FILLED', executedQty: '1.00000000' };
    }
    async getMyTrades(_symbol, params) {
        return this.trades.filter(t => (params.orderId === undefined || t.orderId === params.orderId) &&
            (params.fromId === undefined || t.id >= params.fromId));
    }
    async tradesToExecution(symbol, trades, order = {}) {
        const f = await this.getSymbolFilters(symbol);
        return (0, execution_1.parseExecution)((0, execution_1.tradesToResponse)(trades, order), f.baseAsset, f.quoteAsset, { BNB: this.bnbPrice });
    }
    /** Ejecución de compra como la daría Binance (para adoptar una compra sin confirmar). */
    buyExecution(symbol, qty, price) {
        const f = this.filters[symbol];
        const resp = fullResponse({ symbol, orderId: this.nextId++, side: 'BUY', qty, price, fee: qty * this.feeRate, feeAsset: f.baseAsset });
        return (0, execution_1.parseExecution)(resp, f.baseAsset, f.quoteAsset);
    }
}
exports.FakeRest = FakeRest;
/** Operación de /myTrades. */
function trade(o) {
    return {
        symbol: 'DOGEUSDT', id: o.id, orderId: o.orderId, orderListId: -1, price: o.price.toFixed(8), qty: o.qty.toFixed(8),
        quoteQty: (o.qty * o.price).toFixed(8), commission: (o.fee ?? 0).toFixed(8), commissionAsset: o.feeAsset ?? 'USDT',
        time: o.id, isBuyer: o.isBuyer, isMaker: false, isBestMatch: true
    };
}
function klineMessage(symbol, openTime, close, closed) {
    return Buffer.from(JSON.stringify({
        stream: `${symbol.toLowerCase()}@kline_15m`,
        data: {
            e: 'kline', E: openTime + 1000, s: symbol,
            k: { t: openTime, T: openTime + exports.CANDLE - 1, s: symbol, i: '15m', o: String(close), h: String(close),
                l: String(close), c: String(close), v: '100', x: closed }
        }
    }));
}
/** Cliente con dobles; send() emite una vela en el último socket y devuelve la promesa del handler. */
async function makeClient(roster = ['DOGEUSDT', 'BTCUSDT'], setup) {
    const rest = new FakeRest();
    const brain = new FakeBrain();
    const telegram = new FakeTelegram();
    const sockets = [];
    setup?.({ rest, brain });
    const client = new ws_client_1.BinanceWSClient(roster, 15, {
        rest, brain, telegram,
        sleep: async () => { },
        createSocket: (url) => {
            const socket = new FakeSocket(url);
            socket.asksAtCreation = brain.asks.length;
            sockets.push(socket);
            return socket;
        }
    });
    await client.start();
    const send = (symbol, openTime, close, closed) => sockets[sockets.length - 1].emit('message', klineMessage(symbol, openTime, close, closed));
    return { client, rest, brain, telegram, sockets, send };
}
const BUY = (entry, tp, sl) => ({ action: 'BUY', entry_price: entry, take_profit: tp, stop_loss: sl });
exports.BUY = BUY;
//# sourceMappingURL=helpers.js.map