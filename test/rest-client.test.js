"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
// BinanceRestClient con un HTTP falso: parámetros de la orden MARKET, firma, hora del servidor (-1021),
// filtros, saldo insuficiente y recuperación de órdenes con estado desconocido.
require("./setup-env");
const node_test_1 = require("node:test");
const strict_1 = __importDefault(require("node:assert/strict"));
const crypto = __importStar(require("crypto"));
const rest_client_1 = require("../src/api/rest-client");
const helpers_1 = require("./helpers");
const NOW = 1_800_000_000_000;
class FakeHttp {
    route;
    calls = [];
    serverTime = NOW;
    constructor(route) {
        this.route = route;
    }
    handle(method, url, config) {
        const parsed = new URL(url);
        const query = url.split('?')[1] ?? '';
        this.calls.push({ method, path: parsed.pathname, params: parsed.searchParams, query, headers: config?.headers });
        if (parsed.pathname === '/api/v3/time')
            return { data: { serverTime: this.serverTime } };
        return { data: this.route(method, parsed.pathname, parsed.searchParams) };
    }
    async get(url, config) { return this.handle('get', url, config); }
    async post(url, _data, config) { return this.handle('post', url, config); }
    async delete(url, config) { return this.handle('delete', url, config); }
    of(path) { return this.calls.filter(c => c.path === path); }
}
const exchangeInfo = (overrides = {}, filters) => ({
    symbols: [{
            symbol: 'DOGEUSDT', baseAsset: 'DOGE', quoteAsset: 'USDT', quoteOrderQtyMarketAllowed: true, ...overrides,
            filters: filters ?? [
                { filterType: 'PRICE_FILTER', minPrice: '0.00001000', maxPrice: '1000.00000000', tickSize: '0.00001000' },
                { filterType: 'LOT_SIZE', minQty: '1.00000000', maxQty: '9000000.00000000', stepSize: '1.00000000' },
                { filterType: 'MARKET_LOT_SIZE', minQty: '0.00000000', maxQty: '2500000.00000000', stepSize: '0.00000000' },
                { filterType: 'NOTIONAL', minNotional: '1.00000000', applyMinToMarket: true, maxNotional: '9000000.00000000',
                    applyMaxToMarket: false, avgPriceMins: 5 }
            ]
        }]
});
const networkError = () => Object.assign(new Error('timeout of 10000ms exceeded'), { code: 'ECONNABORTED', request: {} });
function makeRest(route) {
    const http = new FakeHttp((method, path, params) => {
        if (path === '/api/v3/exchangeInfo')
            return exchangeInfo();
        return route(method, path, params);
    });
    const rest = new rest_client_1.BinanceRestClient(http, { sleep: async () => { } });
    return { http, rest };
}
const signatureOk = (call) => {
    const [unsigned, signature] = call.query.split('&signature=');
    return crypto.createHmac('sha256', 'test-secret').update(unsigned).digest('hex') === signature;
};
(0, node_test_1.beforeEach)(() => {
    node_test_1.mock.method(Date, 'now', () => NOW);
    node_test_1.mock.method(console, 'log', () => { });
    node_test_1.mock.method(console, 'warn', () => { });
    node_test_1.mock.method(console, 'error', () => { });
});
(0, node_test_1.afterEach)(() => node_test_1.mock.restoreAll());
(0, node_test_1.test)('getSymbolFilters: LOT_SIZE + MARKET_LOT_SIZE + NOTIONAL (applyMinToMarket), con caché', async () => {
    const { http, rest } = makeRest(() => { throw new Error('no esperado'); });
    const f = await rest.getSymbolFilters('dogeusdt');
    strict_1.default.deepEqual(f, {
        baseAsset: 'DOGE', quoteAsset: 'USDT', stepSize: '1.00000000', minQty: 1, maxQty: 2500000,
        tickSize: '0.00001000', minNotional: 1, quoteOrderQtyMarketAllowed: true
    });
    await rest.getSymbolFilters('DOGEUSDT');
    strict_1.default.equal(http.of('/api/v3/exchangeInfo').length, 1);
});
(0, node_test_1.test)('getSymbolFilters: NOTIONAL sin applyMinToMarket no limita la MARKET; MARKET_LOT_SIZE más grueso manda', async () => {
    const http = new FakeHttp(() => exchangeInfo({}, [
        { filterType: 'PRICE_FILTER', tickSize: '0.01000000' },
        { filterType: 'LOT_SIZE', minQty: '0.00001000', maxQty: '9000.00000000', stepSize: '0.00001000' },
        { filterType: 'MARKET_LOT_SIZE', minQty: '0.00010000', maxQty: '50.00000000', stepSize: '0.00010000' },
        { filterType: 'NOTIONAL', minNotional: '5.00000000', applyMinToMarket: false, maxNotional: '9000000', applyMaxToMarket: false }
    ]));
    const f = await new rest_client_1.BinanceRestClient(http).getSymbolFilters('BTCUSDT');
    strict_1.default.equal(f.stepSize, '0.00010000');
    strict_1.default.equal(f.minQty, 0.0001);
    strict_1.default.equal(f.maxQty, 50);
    strict_1.default.equal(f.minNotional, 0);
});
(0, node_test_1.test)('marketBuy: MARKET con quoteOrderQty, respuesta FULL, recvWindow, timestamp con desfase y firma válida', async () => {
    const { http, rest } = makeRest((method, path) => {
        strict_1.default.equal(method, 'post');
        strict_1.default.equal(path, '/api/v3/order');
        return (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 55, side: 'BUY', qty: 184, price: 0.08152, fee: 0.184, feeAsset: 'DOGE' });
    });
    http.serverTime = NOW + 2500;
    await rest.syncServerTime();
    strict_1.default.equal(rest.serverTimeOffsetMs, 2500);
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    const [order] = http.of('/api/v3/order');
    const p = order.params;
    strict_1.default.equal(p.get('symbol'), 'DOGEUSDT');
    strict_1.default.equal(p.get('side'), 'BUY');
    strict_1.default.equal(p.get('type'), 'MARKET');
    strict_1.default.equal(p.get('quoteOrderQty'), '15.00');
    strict_1.default.equal(p.get('quantity'), null);
    strict_1.default.equal(p.get('price'), null);
    strict_1.default.equal(p.get('timeInForce'), null);
    strict_1.default.equal(p.get('newOrderRespType'), 'FULL');
    strict_1.default.match(p.get('newClientOrderId'), /^bot_b_[0-9a-z]+_[0-9a-f]{8}$/);
    strict_1.default.ok(p.get('newClientOrderId').length <= 36);
    strict_1.default.equal(p.get('recvWindow'), String(rest_client_1.RECV_WINDOW_MS));
    strict_1.default.equal(p.get('timestamp'), String(NOW + 2500));
    strict_1.default.equal(order.headers['X-MBX-APIKEY'], 'test-key');
    strict_1.default.ok(signatureOk(order), 'firma HMAC-SHA256 del query codificado');
    strict_1.default.equal(exec.orderId, 55);
    strict_1.default.equal(exec.executedQty, 184);
    strict_1.default.ok(Math.abs(exec.avgPrice - 0.08152) < 1e-12);
    strict_1.default.ok(Math.abs(exec.fees.baseQty - 0.184) < 1e-12);
});
(0, node_test_1.test)('marketBuy: sin quoteOrderQtyMarketAllowed usa quantity = USDT / precio redondeada al stepSize', async () => {
    const http = new FakeHttp((method, path, params) => {
        if (path === '/api/v3/exchangeInfo')
            return exchangeInfo({ quoteOrderQtyMarketAllowed: false });
        return (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 1, side: 'BUY', qty: Number(params.get('quantity')), price: 0.0815,
            fee: 0, feeAsset: 'DOGE' });
    });
    const rest = new rest_client_1.BinanceRestClient(http, { sleep: async () => { } });
    await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    const p = http.of('/api/v3/order')[0].params;
    strict_1.default.equal(p.get('quantity'), '184');
    strict_1.default.equal(p.get('quoteOrderQty'), null);
});
(0, node_test_1.test)('marketSell: MARKET SELL por cantidad', async () => {
    const { http, rest } = makeRest(() => (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 9, side: 'SELL', qty: 183, price: 0.0825, fee: 0.0150975, feeAsset: 'USDT' }));
    const exec = await rest.marketSell('DOGEUSDT', '183');
    const p = http.of('/api/v3/order')[0].params;
    strict_1.default.equal(p.get('side'), 'SELL');
    strict_1.default.equal(p.get('type'), 'MARKET');
    strict_1.default.equal(p.get('quantity'), '183');
    strict_1.default.match(p.get('newClientOrderId'), /^bot_s_/);
    strict_1.default.ok(Math.abs(exec.fees.totalQuote - 0.0150975) < 1e-12);
});
(0, node_test_1.test)('-1021: resincroniza la hora del servidor y reintenta una sola vez', async () => {
    let posts = 0;
    const { http, rest } = makeRest(() => {
        posts++;
        if (posts === 1)
            throw (0, helpers_1.binanceHttpError)(-1021, 'Timestamp for this request is outside of the recvWindow.');
        return (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 2, side: 'SELL', qty: 10, price: 0.08, fee: 0, feeAsset: 'USDT' });
    });
    http.serverTime = NOW;
    await rest.syncServerTime();
    http.serverTime = NOW - 3000; // el reloj local se adelantó 3 s
    await rest.marketSell('DOGEUSDT', '10');
    const orders = http.of('/api/v3/order');
    strict_1.default.equal(orders.length, 2);
    strict_1.default.equal(orders[0].params.get('timestamp'), String(NOW));
    strict_1.default.equal(orders[1].params.get('timestamp'), String(NOW - 3000));
    strict_1.default.equal(http.of('/api/v3/time').length, 2);
    // Dos -1021 seguidos: no hay bucle, se lanza el error
    const again = makeRest(() => { throw (0, helpers_1.binanceHttpError)(-1021, 'Timestamp for this request was 1000ms ahead of the server\'s time.'); });
    await strict_1.default.rejects(again.rest.marketSell('DOGEUSDT', '10'), (e) => e.response.data.code === -1021);
    strict_1.default.equal(again.http.of('/api/v3/order').length, 2);
});
(0, node_test_1.test)('saldo insuficiente (-2010) se propaga sin consultar la orden', async () => {
    const { http, rest } = makeRest(() => {
        throw (0, helpers_1.binanceHttpError)(-2010, 'Account has insufficient balance for requested action.');
    });
    await strict_1.default.rejects(rest.marketSell('DOGEUSDT', '184'), (e) => (0, rest_client_1.isInsufficientBalance)(e));
    strict_1.default.equal(http.of('/api/v3/order').filter(c => c.method === 'get').length, 0);
    strict_1.default.equal((0, rest_client_1.isInsufficientBalance)((0, helpers_1.binanceHttpError)(-2010, 'Market orders are not supported for this symbol.')), false);
});
(0, node_test_1.test)('isUnknownStatus: sin respuesta, HTTP 5xx y -1006/-1007 son estado desconocido; 4xx no', () => {
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)(networkError()), true);
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)((0, helpers_1.binanceHttpError)(-1000, 'Internal error', 503)), true);
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)((0, helpers_1.binanceHttpError)(-1007, 'Timeout waiting for response from backend server.', 408)), true);
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)((0, helpers_1.binanceHttpError)(-1006, 'An unexpected response was received from the message bus.', 400)), true);
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: NOTIONAL')), false);
    strict_1.default.equal((0, rest_client_1.isUnknownStatus)(new Error('cualquier otro')), false);
});
(0, node_test_1.test)('estado desconocido: consulta la orden por newClientOrderId y toma los fills de /myTrades', async () => {
    let sentId = '';
    const { http, rest } = makeRest((method, path, params) => {
        if (path === '/api/v3/order' && method === 'post') {
            sentId = params.get('newClientOrderId');
            throw networkError();
        }
        if (path === '/api/v3/order' && method === 'get') {
            strict_1.default.equal(params.get('origClientOrderId'), sentId);
            return { symbol: 'DOGEUSDT', orderId: 77, clientOrderId: sentId, status: 'FILLED', executedQty: '184.00000000',
                cummulativeQuoteQty: '15.00000000', type: 'MARKET', side: 'BUY' };
        }
        if (path === '/api/v3/myTrades') {
            strict_1.default.equal(params.get('orderId'), '77');
            return [{ symbol: 'DOGEUSDT', id: 1, orderId: 77, price: '0.08152174', qty: '184.00000000', quoteQty: '15.0',
                    commission: '0.18400000', commissionAsset: 'DOGE', isBuyer: true }];
        }
        throw new Error(`ruta inesperada ${method} ${path}`);
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    strict_1.default.equal(exec.orderId, 77);
    strict_1.default.equal(exec.clientOrderId, sentId);
    strict_1.default.equal(exec.executedQty, 184);
    strict_1.default.ok(Math.abs(exec.avgPrice - 15 / 184) < 1e-12);
    strict_1.default.ok(Math.abs(exec.fees.baseQty - 0.184) < 1e-12);
    strict_1.default.equal(http.of('/api/v3/order').filter(c => c.method === 'post').length, 1); // nunca se reenvía
});
(0, node_test_1.test)('estado desconocido y la orden no existe (-2013 dos veces): OrderNotFoundError con el id (puede aparecer tarde)', async () => {
    let sentId = '';
    const { rest } = makeRest((method, _path, params) => {
        if (method === 'post') {
            sentId = params.get('newClientOrderId');
            throw networkError();
        }
        throw (0, helpers_1.binanceHttpError)(-2013, 'Order does not exist.');
    });
    await strict_1.default.rejects(rest.marketSell('DOGEUSDT', '10'), (e) => e instanceof rest_client_1.OrderNotFoundError && e.clientOrderId === sentId && /timeout/.test(e.message));
});
(0, node_test_1.test)('marketBuy con newClientOrderId dado por quien llama (el de la fila PENDING)', async () => {
    const { http, rest } = makeRest(() => (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 8, side: 'BUY', qty: 184, price: 0.0815, fee: 0.184, feeAsset: 'DOGE' }));
    await rest.marketBuy('DOGEUSDT', 15, 0.0815, 'bot_b_fijo_123');
    strict_1.default.equal(http.of('/api/v3/order')[0].params.get('newClientOrderId'), 'bot_b_fijo_123');
});
(0, node_test_1.test)('invalidateSymbolFilters: la siguiente consulta vuelve a leer /exchangeInfo; isLotSizeFailure', async () => {
    const { http, rest } = makeRest(() => { throw new Error('no esperado'); });
    await rest.getSymbolFilters('DOGEUSDT');
    await rest.getSymbolFilters('DOGEUSDT');
    rest.invalidateSymbolFilters('dogeusdt');
    await rest.getSymbolFilters('DOGEUSDT');
    strict_1.default.equal(http.of('/api/v3/exchangeInfo').length, 2);
    strict_1.default.equal((0, rest_client_1.isLotSizeFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: LOT_SIZE')), true);
    strict_1.default.equal((0, rest_client_1.isLotSizeFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: MARKET_LOT_SIZE')), true);
    strict_1.default.equal((0, rest_client_1.isLotSizeFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: NOTIONAL')), false);
});
(0, node_test_1.test)('estado desconocido sin poder consultar: OrderStatusUnknownError con el newClientOrderId', async () => {
    let sentId = '';
    const { http, rest } = makeRest((method, _path, params) => {
        if (method === 'post')
            sentId = params.get('newClientOrderId');
        throw networkError();
    });
    await strict_1.default.rejects(rest.marketSell('DOGEUSDT', '10'), (e) => e instanceof rest_client_1.OrderStatusUnknownError && e.clientOrderId === sentId);
    strict_1.default.equal(http.of('/api/v3/order').filter(c => c.method === 'get').length, 3);
});
(0, node_test_1.test)('orden MARKET consultada que expiró sin ejecutarse: executedQty 0', async () => {
    const { rest } = makeRest((method) => {
        if (method === 'post')
            throw (0, helpers_1.binanceHttpError)(-1000, 'Internal error', 502);
        return { symbol: 'DOGEUSDT', orderId: 5, clientOrderId: 'x', status: 'EXPIRED', executedQty: '0.00000000',
            cummulativeQuoteQty: '0.00000000' };
    });
    const exec = await rest.marketSell('DOGEUSDT', '10');
    strict_1.default.equal(exec.executedQty, 0);
    strict_1.default.equal(exec.status, 'EXPIRED');
});
(0, node_test_1.test)('lookupOrder: null si Binance no tiene la orden', async () => {
    const { rest } = makeRest(() => { throw (0, helpers_1.binanceHttpError)(-2013, 'Order does not exist.'); });
    strict_1.default.equal(await rest.lookupOrder('DOGEUSDT', 'bot_s_x'), null);
});
(0, node_test_1.test)('comisión en BNB: se consulta BNBUSDT para valorarla en USDT', async () => {
    const { http, rest } = makeRest((_method, path, params) => {
        if (path === '/api/v3/ticker/price') {
            strict_1.default.equal(params.get('symbol'), 'BNBUSDT');
            return { symbol: 'BNBUSDT', price: '600.00000000' };
        }
        return (0, helpers_1.fullResponse)({ symbol: 'DOGEUSDT', orderId: 3, side: 'BUY', qty: 184, price: 0.0815, fee: 0.00002, feeAsset: 'BNB' });
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    strict_1.default.ok(Math.abs(exec.fees.totalQuote - 0.012) < 1e-12);
    strict_1.default.equal(exec.fees.baseQty, 0);
    strict_1.default.equal(http.of('/api/v3/ticker/price').length, 1);
});
(0, node_test_1.test)('getFreeBalances: saldo libre de /account (firmado, omitZeroBalances)', async () => {
    const { http, rest } = makeRest(() => ({
        balances: [{ asset: 'DOGE', free: '183.81600000', locked: '0.00000000' }, { asset: 'USDT', free: '985.0', locked: '10' }]
    }));
    const balances = await rest.getFreeBalances();
    strict_1.default.equal(balances.get('DOGE'), 183.816);
    strict_1.default.equal(balances.get('USDT'), 985);
    const call = http.of('/api/v3/account')[0];
    strict_1.default.equal(call.params.get('omitZeroBalances'), 'true');
    strict_1.default.ok(signatureOk(call));
});
(0, node_test_1.test)('isFilterFailure: -1013 por NOTIONAL/LOT_SIZE, no otros -1013 ni otros códigos', () => {
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: NOTIONAL')), true);
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: MIN_NOTIONAL')), true);
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: LOT_SIZE')), true);
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: MARKET_LOT_SIZE')), true);
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-1013, 'Filter failure: PERCENT_PRICE_BY_SIDE')), false);
    strict_1.default.equal((0, rest_client_1.isFilterFailure)((0, helpers_1.binanceHttpError)(-2010, 'Filter failure: NOTIONAL')), false);
});
(0, node_test_1.test)('getAvgPrice: GET /api/v3/avgPrice (público)', async () => {
    const { http, rest } = makeRest((_m, path, params) => {
        strict_1.default.equal(path, '/api/v3/avgPrice');
        strict_1.default.equal(params.get('symbol'), 'DOGEUSDT');
        return { mins: 5, price: '0.08123000', closeTime: NOW };
    });
    strict_1.default.equal(await rest.getAvgPrice('dogeusdt'), 0.08123);
    strict_1.default.equal(http.of('/api/v3/avgPrice')[0].params.get('signature'), null);
});
(0, node_test_1.test)('getOrder por orderId (firmado); null si no existe (-2013)', async () => {
    const { http, rest } = makeRest((_m, _p, params) => {
        if (params.get('orderId') === '404')
            throw (0, helpers_1.binanceHttpError)(-2013, 'Order does not exist.');
        return { orderId: Number(params.get('orderId')), status: 'FILLED', executedQty: '184.00000000' };
    });
    strict_1.default.equal((await rest.getOrder('DOGEUSDT', 40)).status, 'FILLED');
    strict_1.default.equal(await rest.getOrder('DOGEUSDT', 404), null);
    strict_1.default.ok(signatureOk(http.of('/api/v3/order')[0]));
    await strict_1.default.rejects(makeRest(() => { throw (0, helpers_1.binanceHttpError)(-1000, 'Internal error', 503); }).rest.getOrder('DOGEUSDT', 1));
});
(0, node_test_1.test)('getMyTrades: parámetros orderId / fromId y orden por id', async () => {
    const { http, rest } = makeRest(() => [{ id: 9 }, { id: 3 }, { id: 5 }]);
    strict_1.default.deepEqual((await rest.getMyTrades('DOGEUSDT', { fromId: 3 })).map(t => t.id), [3, 5, 9]);
    await rest.getMyTrades('DOGEUSDT', { orderId: 40 });
    const [a, b] = http.of('/api/v3/myTrades');
    strict_1.default.equal(a.params.get('fromId'), '3');
    strict_1.default.equal(a.params.get('orderId'), null);
    strict_1.default.equal(b.params.get('orderId'), '40');
    strict_1.default.equal(b.params.get('limit'), '1000');
});
(0, node_test_1.test)('estado desconocido: PARTIALLY_FILLED en la última consulta se toma con lo ejecutado', async () => {
    let gets = 0;
    const { rest } = makeRest((method, path) => {
        if (method === 'post')
            throw networkError();
        if (path === '/api/v3/order') {
            gets++;
            return { symbol: 'DOGEUSDT', orderId: 70, clientOrderId: 'x', status: 'PARTIALLY_FILLED', executedQty: '50.00000000',
                cummulativeQuoteQty: '4.00000000' };
        }
        return [{ id: 1, orderId: 70, price: '0.08000000', qty: '50.00000000', quoteQty: '4.00000000', commission: '0.05',
                commissionAsset: 'DOGE' }];
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.08);
    strict_1.default.equal(gets, 3); // las dos primeras PARTIALLY_FILLED se vuelven a consultar
    strict_1.default.equal(exec.executedQty, 50);
    strict_1.default.equal(exec.status, 'PARTIALLY_FILLED');
});
//# sourceMappingURL=rest-client.test.js.map