// Cálculos puros: redondeos, mínimos, respuesta FULL, comisiones (base / USDT / BNB) y PnL neto.
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    decimalsOf, floorToStep, formatPrice, formatQty, formatUsdt, foreignFeeAssets, isTradable, mergeExecutions, netPnl,
    parseExecution, sellableQuantity, soldQuantity, summarizeFees, tradesToResponse
} from '../src/api/execution';
import { BTC, DOGE, fullResponse } from './helpers';

const close = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`);

test('decimalsOf y floorToStep redondean hacia abajo al stepSize sin notación científica', () => {
    assert.equal(decimalsOf('1.00000000'), 0);
    assert.equal(decimalsOf('0.00001000'), 5);
    assert.equal(floorToStep(183.816, '1.00000000'), '183');
    assert.equal(floorToStep(184, '1.00000000'), '184');
    assert.equal(floorToStep(0.00014985, '0.00001000'), '0.00014');
    assert.equal(floorToStep(0.1 + 0.2, '0.10000000'), '0.3'); // 0.30000000000000004 no baja a 0.2
    assert.equal(floorToStep(0.00000123, '0.00000001'), '0.00000123');
    assert.equal(floorToStep(0, '1.00000000'), '0');
    assert.equal(floorToStep(-5, '0.00100000'), '0.000');
});

test('formatPrice usa los decimales del tickSize (DOGE no sale como 0.08)', () => {
    assert.equal(formatPrice(0.08133, DOGE.tickSize), '0.08133');
    assert.equal(formatPrice(0.0825, DOGE.tickSize), '0.08250');
    assert.equal(formatPrice(0.081234567, DOGE.tickSize), '0.08123');
    assert.equal(formatPrice(65432.1, BTC.tickSize), '65432.10');
    assert.equal(formatPrice(0.0812345), '0.0812345'); // sin tickSize conocido no se recorta a 2 decimales
    assert.equal(formatUsdt(0.0824), '+0.0824 USDT');
    assert.equal(formatUsdt(-0.031), '-0.0310 USDT');
});

test('parseExecution: ejemplo FULL de la documentación (varios fills, comisión en USDT)', () => {
    const resp = {
        symbol: 'BTCUSDT', orderId: 28, orderListId: -1, clientOrderId: '6gCrw2kRUAF9CvJDGP16IP', transactTime: 1507725176595,
        price: '1.00000000', origQty: '10.00000000', executedQty: '10.00000000', origQuoteOrderQty: '0.000000',
        cummulativeQuoteQty: '10.00000000', status: 'FILLED', timeInForce: 'GTC', type: 'MARKET', side: 'SELL',
        workingTime: 1507725176595, selfTradePreventionMode: 'NONE',
        fills: [
            { price: '4000.00000000', qty: '1.00000000', commission: '4.00000000', commissionAsset: 'USDT', tradeId: 56 },
            { price: '3999.00000000', qty: '5.00000000', commission: '19.99500000', commissionAsset: 'USDT', tradeId: 57 },
            { price: '3998.00000000', qty: '2.00000000', commission: '7.99600000', commissionAsset: 'USDT', tradeId: 58 },
            { price: '3997.00000000', qty: '1.00000000', commission: '3.99700000', commissionAsset: 'USDT', tradeId: 59 },
            { price: '3995.00000000', qty: '1.00000000', commission: '3.99500000', commissionAsset: 'USDT', tradeId: 60 }
        ]
    };
    const exec = parseExecution(resp, 'BTC', 'USDT');
    assert.equal(exec.orderId, 28);
    assert.equal(exec.executedQty, 10);
    assert.equal(exec.fills.length, 5);
    close(exec.avgPrice, 1); // precio medio = cummulativeQuoteQty / executedQty
    close(exec.fees.totalQuote, 39.983);
    assert.equal(exec.fees.baseQty, 0);
});

test('parseExecution: precio medio de varios fills y comisión en la moneda base', () => {
    const resp = {
        orderId: 7, clientOrderId: 'x', status: 'FILLED', executedQty: '184.00000000', cummulativeQuoteQty: '14.99600000',
        fills: [
            { price: '0.08140000', qty: '100.00000000', commission: '0.10000000', commissionAsset: 'DOGE' },
            { price: '0.08160000', qty: '84.00000000', commission: '0.08400000', commissionAsset: 'DOGE' }
        ]
    };
    const exec = parseExecution(resp, 'DOGE', 'USDT');
    close(exec.avgPrice, 14.996 / 184);
    close(exec.fees.baseQty, 0.184);
    close(exec.fees.totalQuote, 0.184 * (14.996 / 184));
    assert.equal(exec.fees.detail, '0.184 DOGE');
    // vendible = 184 − 0.184 = 183.816 -> 183 (stepSize 1)
    assert.equal(sellableQuantity(exec.executedQty - exec.fees.baseQty, DOGE), '183');
});

test('parseExecution: cummulativeQuoteQty negativo (no disponible) se reconstruye con los fills', () => {
    const exec = parseExecution({ orderId: 1, executedQty: '2', cummulativeQuoteQty: '-1',
        fills: [{ price: '10', qty: '2', commission: '0', commissionAsset: 'USDT' }] }, 'X', 'USDT');
    close(exec.quoteQty, 20);
    close(exec.avgPrice, 10);
});

test('comisión en BNB: se valora con el precio de BNB; sin precio queda marcada como no valorada', () => {
    const resp = fullResponse({ symbol: 'DOGEUSDT', orderId: 1, side: 'BUY', qty: 184, price: 0.0815, fee: 0.00002, feeAsset: 'BNB' });
    assert.deepEqual(foreignFeeAssets(resp, 'DOGE', 'USDT'), ['BNB']);
    const priced = parseExecution(resp, 'DOGE', 'USDT', { BNB: 600 });
    close(priced.fees.totalQuote, 0.012);
    assert.equal(priced.fees.baseQty, 0); // BNB no reduce la cantidad de DOGE vendible
    assert.deepEqual(priced.fees.unpriced, []);
    const unpriced = parseExecution(resp, 'DOGE', 'USDT');
    assert.equal(unpriced.fees.totalQuote, 0);
    assert.deepEqual(unpriced.fees.unpriced, ['BNB']);
    // Con varias monedas de comisión se suman por activo
    const mixed = summarizeFees([
        { price: 1, qty: 1, commission: 0.5, commissionAsset: 'USDT' },
        { price: 1, qty: 1, commission: 0.001, commissionAsset: 'BNB' },
        { price: 1, qty: 1, commission: 0.25, commissionAsset: 'USDT' }
    ], 'DOGE', 'USDT', 0.08, { BNB: 500 });
    close(mixed.totalQuote, 0.75 + 0.5);
    assert.equal(mixed.detail, '0.75 USDT + 0.001 BNB');
});

test('isTradable: minQty, maxQty y mínimo nocional', () => {
    assert.equal(isTradable(183, 0.08, DOGE), true);
    assert.equal(isTradable(0, 0.08, DOGE), false);
    assert.equal(isTradable(0.9, 0.08, DOGE), false);           // < minQty
    assert.equal(isTradable(12, 0.08, DOGE), false);            // 0.96 USDT < minNotional 1
    assert.equal(isTradable(13, 0.08, DOGE), true);
    assert.equal(isTradable(10_000_000, 0.08, DOGE), false);    // > maxQty
    assert.equal(isTradable(0.00007, 65000, BTC), false);       // 4.55 USDT < 5
    assert.equal(isTradable(0.00008, 65000, BTC), true);
    assert.equal(isTradable(5, 0.001, { ...DOGE, minNotional: 0 }), true); // NOTIONAL no aplicado a MARKET
});

test('sellableQuantity: limita al saldo libre y redondea hacia abajo', () => {
    assert.equal(sellableQuantity(183.816, DOGE), '183');
    assert.equal(sellableQuantity(183.816, DOGE, 150.7), '150');
    assert.equal(sellableQuantity(183.816, DOGE, 0.4), '0');
    assert.equal(sellableQuantity(0.00022978, BTC, 1), '0.00022');
});

test('netPnl: comisión de compra en base no se cuenta dos veces (cuadra con el efectivo)', () => {
    // Compra: 15 USDT -> 184 DOGE, comisión 0.184 DOGE. Venta: 183 DOGE a 0.0825, comisión 0.1 % en USDT.
    const entry = { entryQuote: 15, entryFeeQuote: 0.184 * (15 / 184), entryFeeBaseQty: 0.184, entryPrice: 15 / 184 };
    const sellQuote = 183 * 0.0825;
    const exit = { quoteQty: sellQuote, fees: { baseQty: 0, totalQuote: sellQuote * 0.001, detail: '', unpriced: [] } };
    const cash = (sellQuote - sellQuote * 0.001) - 15; // USDT recibidos netos − USDT pagados
    close(netPnl(entry, exit), cash);
});

test('netPnl: el residuo bajo el stepSize se valora al precio de venta (BTC con comisión en BTC)', () => {
    // Compra 0.00016 BTC a 88334 (14.13344 USDT), comisión 0.00000016 BTC -> neto 0.00015984 -> se venden 0.00015.
    // Quedan 0.00000984 BTC (~0.88 USDT, ~6 % de la posición) en la cuenta: no son una pérdida.
    const entry = { entryQuote: 0.00016 * 88334, entryFeeQuote: 0.00000016 * 88334, entryFeeBaseQty: 0.00000016, entryPrice: 88334 };
    const sellQuote = 0.00015 * 89525;
    const exit = { quoteQty: sellQuote, avgPrice: 89525, fees: { baseQty: 0, totalQuote: sellQuote * 0.001, detail: '', unpriced: [] } };
    const residual = 0.00015984 - 0.00015;
    close(netPnl(entry, exit, residual), 0.00015984 * 89525 - 0.00016 * 88334 - sellQuote * 0.001);
    assert.ok(netPnl(entry, exit, residual) > 0, 'un TP no puede dar pérdida por el redondeo');
    assert.ok(netPnl(entry, exit) < 0);                    // sin residuo: solo caja, cuenta 0.88 USDT como pérdida
});

test('formatQty y el detalle de comisiones nunca usan notación científica', () => {
    assert.equal(formatQty(0.00000016), '0.00000016');      // String(1.6e-7) === '1.6e-7'
    assert.equal(formatQty(183.816), '183.816');
    assert.equal(formatQty(184), '184');
    assert.equal(formatQty(0.000000001), '0');
    const fees = summarizeFees([{ price: 88334, qty: 0.00016, commission: 0.00000016, commissionAsset: 'BTC' }], 'BTC', 'USDT', 88334);
    assert.equal(fees.detail, '0.00000016 BTC');
});

test('netPnl: comisiones en USDT y BNB sí se restan', () => {
    const entry = { entryQuote: 15, entryFeeQuote: 0.012, entryFeeBaseQty: 0, entryPrice: 0.0815 };
    const exit = { quoteQty: 15.2, fees: { baseQty: 0, totalQuote: 0.0152, detail: '', unpriced: [] } };
    close(netPnl(entry, exit), 15.2 - 15 - 0.012 - 0.0152);
});

test('mergeExecutions suma cantidades, importes y comisiones ya valoradas', () => {
    const a = parseExecution(fullResponse({ symbol: 'DOGEUSDT', orderId: 1, side: 'SELL', qty: 100, price: 0.08, fee: 0.0001, feeAsset: 'BNB',
        status: 'EXPIRED' }), 'DOGE', 'USDT', { BNB: 600 });
    const b = parseExecution(fullResponse({ symbol: 'DOGEUSDT', orderId: 2, side: 'SELL', qty: 83, price: 0.079, fee: 0.006557, feeAsset: 'USDT' }),
        'DOGE', 'USDT');
    const m = mergeExecutions([a, b]);
    assert.equal(m.executedQty, 183);
    close(m.quoteQty, 8 + 6.557);
    close(m.avgPrice, (8 + 6.557) / 183);
    close(m.fees.totalQuote, 0.06 + 0.006557);
    assert.equal(m.fills.length, 2);
    assert.equal(m.status, 'FILLED');
    assert.equal(mergeExecutions([a]), a);
});

test('isTradable con margen sobre minNotional (Binance valora las MARKET con el precio medio)', () => {
    assert.equal(isTradable(13, 0.0776, DOGE), true);              // 1.0088 >= 1
    assert.equal(isTradable(13, 0.0776, DOGE, 0.01), false);       // 1.0088 < 1.01
    assert.equal(isTradable(13, 0.0777, DOGE, 0.01), true);        // 1.0101 >= 1.01
    assert.equal(isTradable(5, 0.001, { ...DOGE, minNotional: 0 }, 0.01), true);
});

test('tradesToResponse: operaciones de /myTrades -> respuesta FULL con fills y comisiones', () => {
    const trades = [
        { id: 7, orderId: 41, price: '0.08260000', qty: '100.00000000', quoteQty: '8.26000000', commission: '0.00826000', commissionAsset: 'USDT' },
        { id: 8, orderId: 41, price: '0.08250000', qty: '83.00000000', commission: '0.00007000', commissionAsset: 'BNB' }
    ];
    const resp = tradesToResponse(trades, { status: 'FILLED', clientOrderId: 'bot_s_x' });
    assert.equal(resp.orderId, 41);
    assert.equal(resp.clientOrderId, 'bot_s_x');
    const exec = parseExecution(resp, 'DOGE', 'USDT', { BNB: 600 });
    assert.equal(exec.executedQty, 183);
    close(exec.quoteQty, 8.26 + 83 * 0.0825);                       // sin quoteQty se usa precio × cantidad
    close(exec.fees.totalQuote, 0.00826 + 0.00007 * 600);
    assert.equal(exec.fills.length, 2);
    assert.equal(soldQuantity([exec, exec]), 366);
    assert.equal(soldQuantity(undefined), 0);
});
