// BinanceRestClient con un HTTP falso: parámetros de la orden MARKET, firma, hora del servidor (-1021),
// filtros, saldo insuficiente y recuperación de órdenes con estado desconocido.
import './setup-env';
import { afterEach, beforeEach, mock, test } from 'node:test';
import assert from 'node:assert/strict';
import * as crypto from 'crypto';
import {
    BinanceRestClient, HttpClient, OrderNotFoundError, OrderStatusUnknownError, RECV_WINDOW_MS, isFilterFailure,
    isInsufficientBalance, isLotSizeFailure,
    isUnknownStatus
} from '../src/api/rest-client';
import { binanceHttpError, fullResponse } from './helpers';

const NOW = 1_800_000_000_000;

interface Call { method: string; path: string; params: URLSearchParams; query: string; headers: any }
type Route = (method: string, path: string, params: URLSearchParams) => any;

class FakeHttp implements HttpClient {
    calls: Call[] = [];
    serverTime = NOW;
    constructor(public route: Route) {}
    private handle(method: string, url: string, config: any) {
        const parsed = new URL(url);
        const query = url.split('?')[1] ?? '';
        this.calls.push({ method, path: parsed.pathname, params: parsed.searchParams, query, headers: config?.headers });
        if (parsed.pathname === '/api/v3/time') return { data: { serverTime: this.serverTime } };
        return { data: this.route(method, parsed.pathname, parsed.searchParams) };
    }
    async get(url: string, config?: any) { return this.handle('get', url, config); }
    async post(url: string, _data?: any, config?: any) { return this.handle('post', url, config); }
    async delete(url: string, config?: any) { return this.handle('delete', url, config); }
    of(path: string) { return this.calls.filter(c => c.path === path); }
}

const exchangeInfo = (overrides: any = {}, filters?: any[]) => ({
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

function makeRest(route: Route) {
    const http = new FakeHttp((method, path, params) => {
        if (path === '/api/v3/exchangeInfo') return exchangeInfo();
        return route(method, path, params);
    });
    const rest = new BinanceRestClient(http, { sleep: async () => {} });
    return { http, rest };
}

const signatureOk = (call: Call) => {
    const [unsigned, signature] = call.query.split('&signature=');
    return crypto.createHmac('sha256', 'test-secret').update(unsigned!).digest('hex') === signature;
};

beforeEach(() => {
    mock.method(Date, 'now', () => NOW);
    mock.method(console, 'log', () => {});
    mock.method(console, 'warn', () => {});
    mock.method(console, 'error', () => {});
});
afterEach(() => mock.restoreAll());

test('getSymbolFilters: LOT_SIZE + MARKET_LOT_SIZE + NOTIONAL (applyMinToMarket), con caché', async () => {
    const { http, rest } = makeRest(() => { throw new Error('no esperado'); });
    const f = await rest.getSymbolFilters('dogeusdt');
    assert.deepEqual(f, {
        baseAsset: 'DOGE', quoteAsset: 'USDT', stepSize: '1.00000000', minQty: 1, maxQty: 2500000,
        tickSize: '0.00001000', minNotional: 1, quoteOrderQtyMarketAllowed: true
    });
    await rest.getSymbolFilters('DOGEUSDT');
    assert.equal(http.of('/api/v3/exchangeInfo').length, 1);
});

test('getSymbolFilters: NOTIONAL sin applyMinToMarket no limita la MARKET; MARKET_LOT_SIZE más grueso manda', async () => {
    const http = new FakeHttp(() => exchangeInfo({}, [
        { filterType: 'PRICE_FILTER', tickSize: '0.01000000' },
        { filterType: 'LOT_SIZE', minQty: '0.00001000', maxQty: '9000.00000000', stepSize: '0.00001000' },
        { filterType: 'MARKET_LOT_SIZE', minQty: '0.00010000', maxQty: '50.00000000', stepSize: '0.00010000' },
        { filterType: 'NOTIONAL', minNotional: '5.00000000', applyMinToMarket: false, maxNotional: '9000000', applyMaxToMarket: false }
    ]));
    const f = await new BinanceRestClient(http).getSymbolFilters('BTCUSDT');
    assert.equal(f.stepSize, '0.00010000');
    assert.equal(f.minQty, 0.0001);
    assert.equal(f.maxQty, 50);
    assert.equal(f.minNotional, 0);
});

test('marketBuy: MARKET con quoteOrderQty, respuesta FULL, recvWindow, timestamp con desfase y firma válida', async () => {
    const { http, rest } = makeRest((method, path) => {
        assert.equal(method, 'post');
        assert.equal(path, '/api/v3/order');
        return fullResponse({ symbol: 'DOGEUSDT', orderId: 55, side: 'BUY', qty: 184, price: 0.08152, fee: 0.184, feeAsset: 'DOGE' });
    });
    http.serverTime = NOW + 2500;
    await rest.syncServerTime();
    assert.equal(rest.serverTimeOffsetMs, 2500);

    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    const [order] = http.of('/api/v3/order');
    const p = order!.params;
    assert.equal(p.get('symbol'), 'DOGEUSDT');
    assert.equal(p.get('side'), 'BUY');
    assert.equal(p.get('type'), 'MARKET');
    assert.equal(p.get('quoteOrderQty'), '15.00');
    assert.equal(p.get('quantity'), null);
    assert.equal(p.get('price'), null);
    assert.equal(p.get('timeInForce'), null);
    assert.equal(p.get('newOrderRespType'), 'FULL');
    assert.match(p.get('newClientOrderId')!, /^bot_b_[0-9a-z]+_[0-9a-f]{8}$/);
    assert.ok(p.get('newClientOrderId')!.length <= 36);
    assert.equal(p.get('recvWindow'), String(RECV_WINDOW_MS));
    assert.equal(p.get('timestamp'), String(NOW + 2500));
    assert.equal(order!.headers['X-MBX-APIKEY'], 'test-key');
    assert.ok(signatureOk(order!), 'firma HMAC-SHA256 del query codificado');

    assert.equal(exec.orderId, 55);
    assert.equal(exec.executedQty, 184);
    assert.ok(Math.abs(exec.avgPrice - 0.08152) < 1e-12);
    assert.ok(Math.abs(exec.fees.baseQty - 0.184) < 1e-12);
});

test('marketBuy: sin quoteOrderQtyMarketAllowed usa quantity = USDT / precio redondeada al stepSize', async () => {
    const http = new FakeHttp((method, path, params) => {
        if (path === '/api/v3/exchangeInfo') return exchangeInfo({ quoteOrderQtyMarketAllowed: false });
        return fullResponse({ symbol: 'DOGEUSDT', orderId: 1, side: 'BUY', qty: Number(params.get('quantity')), price: 0.0815,
            fee: 0, feeAsset: 'DOGE' });
    });
    const rest = new BinanceRestClient(http, { sleep: async () => {} });
    await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    const p = http.of('/api/v3/order')[0]!.params;
    assert.equal(p.get('quantity'), '184');
    assert.equal(p.get('quoteOrderQty'), null);
});

test('marketSell: MARKET SELL por cantidad', async () => {
    const { http, rest } = makeRest(() =>
        fullResponse({ symbol: 'DOGEUSDT', orderId: 9, side: 'SELL', qty: 183, price: 0.0825, fee: 0.0150975, feeAsset: 'USDT' }));
    const exec = await rest.marketSell('DOGEUSDT', '183');
    const p = http.of('/api/v3/order')[0]!.params;
    assert.equal(p.get('side'), 'SELL');
    assert.equal(p.get('type'), 'MARKET');
    assert.equal(p.get('quantity'), '183');
    assert.match(p.get('newClientOrderId')!, /^bot_s_/);
    assert.ok(Math.abs(exec.fees.totalQuote - 0.0150975) < 1e-12);
});

test('-1021: resincroniza la hora del servidor y reintenta una sola vez', async () => {
    let posts = 0;
    const { http, rest } = makeRest(() => {
        posts++;
        if (posts === 1) throw binanceHttpError(-1021, 'Timestamp for this request is outside of the recvWindow.');
        return fullResponse({ symbol: 'DOGEUSDT', orderId: 2, side: 'SELL', qty: 10, price: 0.08, fee: 0, feeAsset: 'USDT' });
    });
    http.serverTime = NOW;
    await rest.syncServerTime();
    http.serverTime = NOW - 3000; // el reloj local se adelantó 3 s
    await rest.marketSell('DOGEUSDT', '10');
    const orders = http.of('/api/v3/order');
    assert.equal(orders.length, 2);
    assert.equal(orders[0]!.params.get('timestamp'), String(NOW));
    assert.equal(orders[1]!.params.get('timestamp'), String(NOW - 3000));
    assert.equal(http.of('/api/v3/time').length, 2);

    // Dos -1021 seguidos: no hay bucle, se lanza el error
    const again = makeRest(() => { throw binanceHttpError(-1021, 'Timestamp for this request was 1000ms ahead of the server\'s time.'); });
    await assert.rejects(again.rest.marketSell('DOGEUSDT', '10'), (e: any) => e.response.data.code === -1021);
    assert.equal(again.http.of('/api/v3/order').length, 2);
});

test('saldo insuficiente (-2010) se propaga sin consultar la orden', async () => {
    const { http, rest } = makeRest(() => {
        throw binanceHttpError(-2010, 'Account has insufficient balance for requested action.');
    });
    await assert.rejects(rest.marketSell('DOGEUSDT', '184'), (e: any) => isInsufficientBalance(e));
    assert.equal(http.of('/api/v3/order').filter(c => c.method === 'get').length, 0);
    assert.equal(isInsufficientBalance(binanceHttpError(-2010, 'Market orders are not supported for this symbol.')), false);
});

test('isUnknownStatus: sin respuesta, HTTP 5xx y -1006/-1007 son estado desconocido; 4xx no', () => {
    assert.equal(isUnknownStatus(networkError()), true);
    assert.equal(isUnknownStatus(binanceHttpError(-1000, 'Internal error', 503)), true);
    assert.equal(isUnknownStatus(binanceHttpError(-1007, 'Timeout waiting for response from backend server.', 408)), true);
    assert.equal(isUnknownStatus(binanceHttpError(-1006, 'An unexpected response was received from the message bus.', 400)), true);
    assert.equal(isUnknownStatus(binanceHttpError(-1013, 'Filter failure: NOTIONAL')), false);
    assert.equal(isUnknownStatus(new Error('cualquier otro')), false);
});

test('estado desconocido: consulta la orden por newClientOrderId y toma los fills de /myTrades', async () => {
    let sentId = '';
    const { http, rest } = makeRest((method, path, params) => {
        if (path === '/api/v3/order' && method === 'post') {
            sentId = params.get('newClientOrderId')!;
            throw networkError();
        }
        if (path === '/api/v3/order' && method === 'get') {
            assert.equal(params.get('origClientOrderId'), sentId);
            return { symbol: 'DOGEUSDT', orderId: 77, clientOrderId: sentId, status: 'FILLED', executedQty: '184.00000000',
                     cummulativeQuoteQty: '15.00000000', type: 'MARKET', side: 'BUY' };
        }
        if (path === '/api/v3/myTrades') {
            assert.equal(params.get('orderId'), '77');
            return [{ symbol: 'DOGEUSDT', id: 1, orderId: 77, price: '0.08152174', qty: '184.00000000', quoteQty: '15.0',
                      commission: '0.18400000', commissionAsset: 'DOGE', isBuyer: true }];
        }
        throw new Error(`ruta inesperada ${method} ${path}`);
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    assert.equal(exec.orderId, 77);
    assert.equal(exec.clientOrderId, sentId);
    assert.equal(exec.executedQty, 184);
    assert.ok(Math.abs(exec.avgPrice - 15 / 184) < 1e-12);
    assert.ok(Math.abs(exec.fees.baseQty - 0.184) < 1e-12);
    assert.equal(http.of('/api/v3/order').filter(c => c.method === 'post').length, 1); // nunca se reenvía
});

test('estado desconocido y la orden no existe (-2013 dos veces): OrderNotFoundError con el id (puede aparecer tarde)', async () => {
    let sentId = '';
    const { rest } = makeRest((method, _path, params) => {
        if (method === 'post') {
            sentId = params.get('newClientOrderId')!;
            throw networkError();
        }
        throw binanceHttpError(-2013, 'Order does not exist.');
    });
    await assert.rejects(rest.marketSell('DOGEUSDT', '10'),
        (e: any) => e instanceof OrderNotFoundError && e.clientOrderId === sentId && /timeout/.test(e.message));
});

test('marketBuy con newClientOrderId dado por quien llama (el de la fila PENDING)', async () => {
    const { http, rest } = makeRest(() =>
        fullResponse({ symbol: 'DOGEUSDT', orderId: 8, side: 'BUY', qty: 184, price: 0.0815, fee: 0.184, feeAsset: 'DOGE' }));
    await rest.marketBuy('DOGEUSDT', 15, 0.0815, 'bot_b_fijo_123');
    assert.equal(http.of('/api/v3/order')[0]!.params.get('newClientOrderId'), 'bot_b_fijo_123');
});

test('invalidateSymbolFilters: la siguiente consulta vuelve a leer /exchangeInfo; isLotSizeFailure', async () => {
    const { http, rest } = makeRest(() => { throw new Error('no esperado'); });
    await rest.getSymbolFilters('DOGEUSDT');
    await rest.getSymbolFilters('DOGEUSDT');
    rest.invalidateSymbolFilters('dogeusdt');
    await rest.getSymbolFilters('DOGEUSDT');
    assert.equal(http.of('/api/v3/exchangeInfo').length, 2);
    assert.equal(isLotSizeFailure(binanceHttpError(-1013, 'Filter failure: LOT_SIZE')), true);
    assert.equal(isLotSizeFailure(binanceHttpError(-1013, 'Filter failure: MARKET_LOT_SIZE')), true);
    assert.equal(isLotSizeFailure(binanceHttpError(-1013, 'Filter failure: NOTIONAL')), false);
});

test('estado desconocido sin poder consultar: OrderStatusUnknownError con el newClientOrderId', async () => {
    let sentId = '';
    const { http, rest } = makeRest((method, _path, params) => {
        if (method === 'post') sentId = params.get('newClientOrderId')!;
        throw networkError();
    });
    await assert.rejects(rest.marketSell('DOGEUSDT', '10'),
        (e: any) => e instanceof OrderStatusUnknownError && e.clientOrderId === sentId);
    assert.equal(http.of('/api/v3/order').filter(c => c.method === 'get').length, 3);
});

test('orden MARKET consultada que expiró sin ejecutarse: executedQty 0', async () => {
    const { rest } = makeRest((method) => {
        if (method === 'post') throw binanceHttpError(-1000, 'Internal error', 502);
        return { symbol: 'DOGEUSDT', orderId: 5, clientOrderId: 'x', status: 'EXPIRED', executedQty: '0.00000000',
                 cummulativeQuoteQty: '0.00000000' };
    });
    const exec = await rest.marketSell('DOGEUSDT', '10');
    assert.equal(exec.executedQty, 0);
    assert.equal(exec.status, 'EXPIRED');
});

test('lookupOrder: null si Binance no tiene la orden', async () => {
    const { rest } = makeRest(() => { throw binanceHttpError(-2013, 'Order does not exist.'); });
    assert.equal(await rest.lookupOrder('DOGEUSDT', 'bot_s_x'), null);
});

test('comisión en BNB: se consulta BNBUSDT para valorarla en USDT', async () => {
    const { http, rest } = makeRest((_method, path, params) => {
        if (path === '/api/v3/ticker/price') {
            assert.equal(params.get('symbol'), 'BNBUSDT');
            return { symbol: 'BNBUSDT', price: '600.00000000' };
        }
        return fullResponse({ symbol: 'DOGEUSDT', orderId: 3, side: 'BUY', qty: 184, price: 0.0815, fee: 0.00002, feeAsset: 'BNB' });
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.0815);
    assert.ok(Math.abs(exec.fees.totalQuote - 0.012) < 1e-12);
    assert.equal(exec.fees.baseQty, 0);
    assert.equal(http.of('/api/v3/ticker/price').length, 1);
});

test('getFreeBalances: saldo libre de /account (firmado, omitZeroBalances)', async () => {
    const { http, rest } = makeRest(() => ({
        balances: [{ asset: 'DOGE', free: '183.81600000', locked: '0.00000000' }, { asset: 'USDT', free: '985.0', locked: '10' }]
    }));
    const balances = await rest.getFreeBalances();
    assert.equal(balances.get('DOGE'), 183.816);
    assert.equal(balances.get('USDT'), 985);
    const call = http.of('/api/v3/account')[0]!;
    assert.equal(call.params.get('omitZeroBalances'), 'true');
    assert.ok(signatureOk(call));
});

test('isFilterFailure: -1013 por NOTIONAL/LOT_SIZE, no otros -1013 ni otros códigos', () => {
    assert.equal(isFilterFailure(binanceHttpError(-1013, 'Filter failure: NOTIONAL')), true);
    assert.equal(isFilterFailure(binanceHttpError(-1013, 'Filter failure: MIN_NOTIONAL')), true);
    assert.equal(isFilterFailure(binanceHttpError(-1013, 'Filter failure: LOT_SIZE')), true);
    assert.equal(isFilterFailure(binanceHttpError(-1013, 'Filter failure: MARKET_LOT_SIZE')), true);
    assert.equal(isFilterFailure(binanceHttpError(-1013, 'Filter failure: PERCENT_PRICE_BY_SIDE')), false);
    assert.equal(isFilterFailure(binanceHttpError(-2010, 'Filter failure: NOTIONAL')), false);
});

test('getAvgPrice: GET /api/v3/avgPrice (público)', async () => {
    const { http, rest } = makeRest((_m, path, params) => {
        assert.equal(path, '/api/v3/avgPrice');
        assert.equal(params.get('symbol'), 'DOGEUSDT');
        return { mins: 5, price: '0.08123000', closeTime: NOW };
    });
    assert.equal(await rest.getAvgPrice('dogeusdt'), 0.08123);
    assert.equal(http.of('/api/v3/avgPrice')[0]!.params.get('signature'), null);
});

test('getOrder por orderId (firmado); null si no existe (-2013)', async () => {
    const { http, rest } = makeRest((_m, _p, params) => {
        if (params.get('orderId') === '404') throw binanceHttpError(-2013, 'Order does not exist.');
        return { orderId: Number(params.get('orderId')), status: 'FILLED', executedQty: '184.00000000' };
    });
    assert.equal((await rest.getOrder('DOGEUSDT', 40)).status, 'FILLED');
    assert.equal(await rest.getOrder('DOGEUSDT', 404), null);
    assert.ok(signatureOk(http.of('/api/v3/order')[0]!));
    await assert.rejects(makeRest(() => { throw binanceHttpError(-1000, 'Internal error', 503); }).rest.getOrder('DOGEUSDT', 1));
});

test('getMyTrades: parámetros orderId / fromId y orden por id', async () => {
    const { http, rest } = makeRest(() => [{ id: 9 }, { id: 3 }, { id: 5 }]);
    assert.deepEqual((await rest.getMyTrades('DOGEUSDT', { fromId: 3 })).map(t => t.id), [3, 5, 9]);
    await rest.getMyTrades('DOGEUSDT', { orderId: 40 });
    const [a, b] = http.of('/api/v3/myTrades');
    assert.equal(a!.params.get('fromId'), '3');
    assert.equal(a!.params.get('orderId'), null);
    assert.equal(b!.params.get('orderId'), '40');
    assert.equal(b!.params.get('limit'), '1000');
});

test('estado desconocido: PARTIALLY_FILLED en la última consulta se toma con lo ejecutado', async () => {
    let gets = 0;
    const { rest } = makeRest((method, path) => {
        if (method === 'post') throw networkError();
        if (path === '/api/v3/order') {
            gets++;
            return { symbol: 'DOGEUSDT', orderId: 70, clientOrderId: 'x', status: 'PARTIALLY_FILLED', executedQty: '50.00000000',
                     cummulativeQuoteQty: '4.00000000' };
        }
        return [{ id: 1, orderId: 70, price: '0.08000000', qty: '50.00000000', quoteQty: '4.00000000', commission: '0.05',
                  commissionAsset: 'DOGE' }];
    });
    const exec = await rest.marketBuy('DOGEUSDT', 15, 0.08);
    assert.equal(gets, 3);                                    // las dos primeras PARTIALLY_FILLED se vuelven a consultar
    assert.equal(exec.executedQty, 50);
    assert.equal(exec.status, 'PARTIALLY_FILLED');
});

test('bnbBurn: firmada en /sapi/v1/bnbBurn (raíz del host, no /api)', async () => {
    const { http, rest } = makeRest((_m, path) => {
        assert.equal(path, '/sapi/v1/bnbBurn');
        return { spotBNBBurn: true, interestBNBBurn: false };
    });
    assert.deepEqual(await rest.getBnbBurnStatus(), { spotBNBBurn: true });
    const call = http.of('/sapi/v1/bnbBurn')[0]!;
    assert.ok(signatureOk(call));
    assert.equal(call.headers['X-MBX-APIKEY'], process.env.BINANCE_API_KEY);
});
