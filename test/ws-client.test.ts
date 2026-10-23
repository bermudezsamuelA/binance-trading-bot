// BinanceWSClient con dobles (sin red): velas, entradas/salidas MARKET, carreras, saldo, polvo, filtros,
// órdenes sin confirmar, cooldown, reconexión, verificación al arrancar y promesas sin capturar.
import './setup-env';
import { afterEach, beforeEach, mock, test } from 'node:test';
import assert from 'node:assert/strict';
import { OrderNotFoundError, OrderStatusUnknownError } from '../src/api/rest-client';
import {
    BinanceWSClient, LATE_BUY_CANCEL_REASON, LATE_ORDER_RECHECKS_MS, STALE_CHECK_MS, STALE_SOCKET_MS, positionFromLedger
} from '../src/api/ws-client';
import {
    BUY, CANDLE, FakeBrain, FakeRest, FakeSocket, FakeTelegram, T0, binanceHttpError, deferred, flush, klineMessage,
    makeClient, trade
} from './helpers';

const close = (a: number, b: number, eps = 1e-7) => assert.ok(Math.abs(a - b) <= eps, `${a} != ${b}`);
let now = T0;

beforeEach(() => {
    now = T0;
    mock.method(Date, 'now', () => now);
    mock.method(console, 'log', () => {});
    mock.method(console, 'warn', () => {});
    mock.method(console, 'error', () => {});
});
afterEach(() => mock.restoreAll());

/** Abre una posición DOGE con señal BUY en la vela T0 (entrada 0.0815, TP 0.0825, SL 0.0805). */
async function openDoge(h: Awaited<ReturnType<typeof makeClient>>, entry = 0.0815) {
    h.brain.signals.push(BUY(entry, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, entry, true);
    assert.ok(h.client.getPosition('DOGEUSDT'), 'posición abierta');
}

test('suscripción kline_15m y el WebSocket se abre después de sincronizar el ledger', async () => {
    const h = await makeClient();
    assert.equal(h.sockets.length, 1);
    assert.match(h.sockets[0]!.url, /\/stream\?streams=dogeusdt@kline_15m\/btcusdt@kline_15m$/);
    // primero las compras PENDING (sin confirmar) y luego las posiciones OPEN
    assert.deepEqual(h.brain.asks.slice(0, 2).map(a => a.type), ['sync_pending', 'sync_positions']);
});

test('velas en formación no se evalúan; la cerrada se evalúa una vez (dedup por open_time)', async () => {
    const h = await makeClient();
    await h.send('DOGEUSDT', T0, 0.08, false);
    await h.send('DOGEUSDT', T0, 0.081, false);
    assert.equal(h.brain.of('evaluate').length, 0);
    await h.send('DOGEUSDT', T0, 0.0812, true);
    assert.equal(h.brain.of('evaluate').length, 1);
    assert.equal(h.brain.of('evaluate')[0]!.payload.market_data.open_time, T0);
    assert.equal(h.brain.of('evaluate')[0]!.payload.market_data.close, 0.0812);
    await h.send('DOGEUSDT', T0, 0.0812, true);           // repetida
    await h.send('DOGEUSDT', T0 - CANDLE, 0.08, true);    // vieja
    assert.equal(h.brain.of('evaluate').length, 1);
    await h.send('BTCUSDT', T0, 65000, true);             // otro símbolo, misma vela
    assert.equal(h.brain.of('evaluate').length, 2);
});

test('vela cerrada duplicada mientras Python tarda: una sola evaluación', async () => {
    const h = await makeClient();
    const gate = deferred();
    const ask = h.brain.ask.bind(h.brain);
    h.brain.ask = async (type: string, payload?: any) => {
        if (type === 'evaluate') await gate.promise;
        return ask(type, payload);
    };
    const first = h.send('DOGEUSDT', T0, 0.08, true);
    const second = h.send('DOGEUSDT', T0, 0.08, true);
    gate.resolve();
    await Promise.all([first, second]);
    assert.equal(h.brain.of('evaluate').length, 1);
});

test('BUY: compra MARKET de 15 USDT y posición con lo ejecutado de verdad (precio medio, cantidad, comisión)', async () => {
    const h = await makeClient();
    h.rest.fillPrice.DOGEUSDT = 0.08152;     // la compra se llena algo por encima de la señal
    await openDoge(h);
    assert.equal(h.rest.buys.length, 1);
    const { clientOrderId, ...buy } = h.rest.buys[0]!;
    assert.deepEqual(buy, { symbol: 'DOGEUSDT', quote: 15, ref: 0.0815 });
    // la fila PENDING se escribe ANTES de enviar la compra, con el mismo newClientOrderId que la orden
    const [pending] = h.brain.of('ledger_pending');
    assert.equal(pending!.payload.client_order_id, clientOrderId);
    assert.match(clientOrderId!, /^bot_b_/);
    assert.deepEqual({ ...pending!.payload, client_order_id: 'x' },
        { client_order_id: 'x', symbol: 'DOGEUSDT', signal_price: 0.0815, take_profit: 0.0825, stop_loss: 0.0805 });
    assert.ok(h.brain.asks.findIndex(a => a.type === 'ledger_pending') < h.brain.asks.findIndex(a => a.type === 'ledger_open'));
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.equal(p.quantity, 184);                         // floor(15 / 0.08152)
    close(p.entryPrice, 0.08152);
    close(p.netQuantity, 184 - 0.184);                     // comisión 0.1 % cobrada en DOGE
    close(p.entryQuote, 184 * 0.08152);
    assert.equal(p.takeProfit, 0.0825);                    // niveles absolutos de la estrategia, sin tocar
    assert.equal(p.stopLoss, 0.0805);

    const [open] = h.brain.of('ledger_open');
    assert.equal(open!.payload.order_id, p.orderId);
    close(open!.payload.entry_price, 0.08152);
    assert.equal(open!.payload.signal_price, 0.0815);
    assert.equal(open!.payload.quantity, 184);
    close(open!.payload.net_quantity, 183.816);
    close(open!.payload.entry_fee_usdt, 0.184 * 0.08152);
    assert.equal(open!.payload.entry_fees, '0.184 DOGE');
    const msg = h.telegram.messages.find(m => m.includes('NUEVA COMPRA'))!;
    assert.match(msg, /\$0\.08152 \(señal \$0\.08150\)/);
    assert.match(msg, /Target:<\/b> \$0\.08250/);
    assert.match(msg, /Riesgo:<\/b> \$0\.08050/);
});

test('BUY sin take_profit/stop_loss numéricos no se opera', async () => {
    const h = await makeClient();
    h.brain.signals.push({ action: 'BUY', entry_price: 0.0815, take_profit: null, stop_loss: 0.0805 });
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.equal(h.rest.buys.length, 0);
});

test('con posición abierta la vela cerrada va a Python pero el BUY se ignora', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.brain.signals.push(BUY(0.0816, 0.0826, 0.0806));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0816, true);
    assert.equal(h.brain.of('evaluate').length, 2);
    assert.equal(h.rest.buys.length, 1);
});

test('TP con precio de vela en formación: venta MARKET de la cantidad vendible y PnL neto real', async () => {
    const h = await makeClient();
    await openDoge(h);
    const p = { ...h.client.getPosition('DOGEUSDT')! };
    h.rest.fillPrice.DOGEUSDT = 0.08249;                   // se vende un poco por debajo del nivel
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.deepEqual(h.rest.sells, [{ symbol: 'DOGEUSDT', qty: '183' }]); // 184 − 0.184 DOGE -> 183
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);

    const [closed] = h.brain.of('ledger_close');
    const quote = 183 * 0.08249;
    // efectivo (recibido neto − pagado) + los 0.816 DOGE que quedan en la cuenta, valorados al precio de venta
    const expected = (quote - quote * 0.001) - p.entryQuote + 0.816 * 0.08249;
    close(closed!.payload.pnl, expected);
    close(closed!.payload.residual_quantity, 0.816);
    assert.equal(closed!.payload.symbol, 'DOGEUSDT');
    close(closed!.payload.exit_price, 0.08249);
    assert.equal(closed!.payload.exit_quantity, 183);
    close(closed!.payload.exit_quote, quote);
    close(closed!.payload.exit_fee_usdt, quote * 0.001);
    assert.equal(closed!.payload.exit_trigger_price, 0.0826);
    assert.equal(closed!.payload.reason, 'TAKE PROFIT ✅');
    const msg = h.telegram.messages.find(m => m.includes('TAKE PROFIT'))!;
    assert.match(msg, /Salida:<\/b> \$0\.08249 \(nivel \$0\.08260\)/);
    assert.match(msg, /PnL neto:<\/b> [+-]\d+\.\d{4} USDT/);
    assert.match(msg, /Comisiones:<\/b> 0\.0\d{3} USDT/);
});

test('BTC con comisión en BTC: un TP no da pérdida por el residuo bajo el stepSize (se valora en el PnL)', async () => {
    const h = await makeClient(['BTCUSDT']);
    h.rest.fillPrice.BTCUSDT = 88000;
    h.brain.signals.push(BUY(88000, 89000, 87000));
    await h.send('BTCUSDT', T0, 88000, true);
    const p = { ...h.client.getPosition('BTCUSDT')! };
    assert.equal(p.quantity, 0.00017);                      // floor(15 / 88000, 0.00001)
    close(p.netQuantity, 0.00016983);                       // −0.00000017 BTC de comisión
    h.rest.fillPrice.BTCUSDT = 89000;
    await h.send('BTCUSDT', T0 + CANDLE, 89000, false);
    assert.deepEqual(h.rest.sells, [{ symbol: 'BTCUSDT', qty: '0.00016' }]);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.symbol, 'BTCUSDT');
    close(closed!.payload.residual_quantity, 0.00000983, 1e-12);
    const quote = 0.00016 * 89000;
    close(closed!.payload.pnl, quote * 0.999 + 0.00000983 * 89000 - p.entryQuote);
    assert.ok(closed!.payload.pnl > 0, `TP con PnL ${closed!.payload.pnl}`);
    assert.ok(h.telegram.messages.some(m => m.includes('Residuo sin vender:</b> 0.00000983 BTC')));
});

test('SL: venta con el precio actual por debajo del stop', async () => {
    const h = await makeClient();
    await openDoge(h);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0806, false);
    assert.equal(h.rest.sells.length, 0);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.reason, 'STOP LOSS ⚠️');
});

test('BUY en la vela de salida se ignora; en la siguiente se opera', async () => {
    const h = await makeClient();
    await openDoge(h);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);   // TP dentro de la vela T0+15m
    h.brain.signals.push(BUY(0.0826, 0.0836, 0.0816));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, true);    // cierre de esa misma vela con BUY
    assert.equal(h.rest.buys.length, 1);
    h.brain.signals.push(BUY(0.0827, 0.0837, 0.0817));
    await h.send('DOGEUSDT', T0 + 2 * CANDLE, 0.0827, true);
    assert.equal(h.rest.buys.length, 2);
});

test('sin doble SELL con actualizaciones solapadas mientras la venta está en curso', async () => {
    const h = await makeClient();
    await openDoge(h);
    const gate = deferred();
    h.rest.sellHook = async () => { await gate.promise; };
    const a = h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    const b = h.send('DOGEUSDT', T0 + CANDLE, 0.0827, false);
    const c = h.send('DOGEUSDT', T0 + CANDLE, 0.0828, true);
    await flush();
    gate.resolve();
    await Promise.all([a, b, c]);
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.brain.of('ledger_close').length, 1);
});

test('carrera: el precio toca el SL mientras se coloca la compra -> cierre inmediato al registrar la posición', async () => {
    const h = await makeClient();
    const gate = deferred();
    h.rest.buyHook = async () => { await gate.promise; };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    const buying = h.send('DOGEUSDT', T0, 0.0815, true);
    await flush();
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0804, false);   // bajo el SL antes de que exista la posición
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0810, false);   // y vuelve a subir
    assert.equal(h.rest.sells.length, 0);
    gate.resolve();
    await buying;
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.reason, 'STOP LOSS ⚠️');
    assert.equal(closed!.payload.exit_trigger_price, 0.0804);
    // el ledger_open llega antes que el ledger_close
    const types = h.brain.asks.map(a => a.type).filter(t => t.startsWith('ledger'));
    assert.deepEqual(types, ['ledger_pending', 'ledger_open', 'ledger_close']);
});

test('carrera: precios dentro del rango durante la compra no cierran nada', async () => {
    const h = await makeClient();
    const gate = deferred();
    h.rest.buyHook = async () => { await gate.promise; };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    const buying = h.send('DOGEUSDT', T0, 0.0815, true);
    await flush();
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0806, false);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0824, false);
    gate.resolve();
    await buying;
    assert.equal(h.rest.sells.length, 0);
    assert.ok(h.client.getPosition('DOGEUSDT'));
});

test('saldo insuficiente al vender: se vende lo libre y se anota en el motivo', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => {
        if (n === 1) throw binanceHttpError(-2010, 'Account has insufficient balance for requested action.');
    };
    h.rest.balances.set('DOGE', 150.4);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183', '150']);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 150);
    assert.match(closed!.payload.reason, /^TAKE PROFIT ✅ \(saldo insuficiente: libre 150\.4 de 183 DOGE\)$/);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

test('saldo insuficiente y lo libre es polvo: se cierra en el ledger sin venta (sin reintentos infinitos)', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = () => { throw binanceHttpError(-2010, 'Account has insufficient balance for requested action.'); };
    h.rest.balances.set('DOGE', 0.6);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 1);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.pnl, null);
    assert.match(closed!.payload.reason, /^SIN SALDO/);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0827, false);
    assert.equal(h.rest.sells.length, 1);
    assert.ok(h.telegram.messages.some(m => m.includes('CIERRE SIN VENTA')));
});

test('posición por debajo del mínimo (polvo): no se envía la venta, se cierra con motivo POLVO', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [{ order_id: 1, symbol: 'DOGEUSDT', entry_price: 0.08, take_profit: 0.0825, stop_loss: 0.0805,
            quantity: 0.9, net_quantity: 0.9, timestamp: 1 }];
        rest.balances.set('DOGE', 0.9);
    });
    // al arrancar 0.9 DOGE no es vendible: se cierra ya en la sincronización
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.match(h.brain.of('ledger_close')[0]!.payload.reason, /^POLVO al arrancar: 0\.9 DOGE/);

    // y si el polvo aparece con la posición en marcha (precio hundido bajo el mínimo nocional)
    const h2 = await makeClient(['DOGEUSDT'], ({ brain }) => {
        brain.openTrades = [{ order_id: 2, symbol: 'DOGEUSDT', entry_price: 0.08, take_profit: 0.0825, stop_loss: 0.0805,
            quantity: 13, net_quantity: 13, timestamp: 1 }];
    });
    assert.ok(h2.client.getPosition('DOGEUSDT'));
    h2.rest.avgPrice.DOGEUSDT = 0.07;                        // precio medio de Binance también hundido
    await h2.send('DOGEUSDT', T0, 0.07, false);              // 13 × 0.07 = 0.91 USDT < 1
    assert.equal(h2.rest.sells.length, 0);
    const [closed] = h2.brain.of('ledger_close');
    assert.match(closed!.payload.reason, /^POLVO: 13 DOGE/);
    assert.equal(closed!.payload.pnl, null);
});

test('venta MARKET llenada en parte (EXPIRED): se vende el resto y se registra la suma', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (s, _q, n) => (n === 1 ? h.rest.sellExecution(s, 100, 'EXPIRED') : undefined);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183', '83']);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 183);
    assert.equal(closed!.payload.reason, 'TAKE PROFIT ✅');
});

test('error de venta genérico: la posición sigue y se reintenta pasados 5 s', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => {
        if (n === 1) throw binanceHttpError(-1003, 'Too much request weight used', 429);
    };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.ok(h.client.getPosition('DOGEUSDT'));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 1);                    // dentro de los 5 s no se reintenta
    now += 5001;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 2);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

const unknownSell = (id = 'bot_s_abc') => new OrderStatusUnknownError('DOGEUSDT', id, new Error('timeout'));

test('venta sin confirmar que se resuelve al consultarla: un solo SELL y cantidad real', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw unknownSell(); };
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 183)];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    assert.equal(h.rest.sells.length, 1);
    assert.deepEqual(h.rest.lookups, [{ symbol: 'DOGEUSDT', clientOrderId: 'bot_s_abc' }]);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.exit_quantity, 183);
});

test('venta sin confirmar tras varias consultas: espera 30 s, no adelanta por el SL y luego consulta antes de vender', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw unknownSell(); };
    h.rest.lookupQueue = [unknownSell(), unknownSell(), unknownSell()];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    assert.ok(h.client.getPosition('DOGEUSDT'));
    assert.equal(h.rest.lookups.length, 3);
    assert.equal(h.telegram.messages.filter(m => m.includes('VENTA SIN CONFIRMAR')).length, 1);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);   // más bajo el SL: con venta sin confirmar no se adelanta
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.rest.lookups.length, 3);
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 183)];
    now += 30001;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0804, false);
    assert.equal(h.rest.sells.length, 1);                    // la venta "desconocida" sí se ejecutó
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.exit_quantity, 183);
});

test('segundo tramo de una venta parcial sin confirmar: se consulta y la cantidad registrada cuadra', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (s, _q, n) => {
        if (n === 1) return h.rest.sellExecution(s, 100, 'EXPIRED');
        if (n === 2) throw unknownSell('bot_s_2');
    };
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 83)];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183', '83']);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 183);
    close(closed!.payload.exit_quote, 183 * 0.0825);
    assert.equal(closed!.payload.reason, 'TAKE PROFIT ✅');
});

test('segundo tramo sin confirmar y sin respuesta: la posición espera con lo vendido y al resolverse suma ambos tramos', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (s, _q, n) => {
        if (n === 1) return h.rest.sellExecution(s, 100, 'EXPIRED');
        if (n === 2) throw unknownSell('bot_s_2');
    };
    h.rest.lookupQueue = [unknownSell('bot_s_2'), unknownSell('bot_s_2'), unknownSell('bot_s_2')];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.ok(h.client.getPosition('DOGEUSDT'));
    assert.equal(h.brain.of('ledger_close').length, 0);
    // la consulta posterior encuentra el tramo: no se vende otra vez
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 83)];
    now += 30001;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 2);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.exit_quantity, 183);
});

test('rechazo por filtro (-1013 NOTIONAL) confirmado con el precio medio: polvo sin reintentos', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = () => { throw binanceHttpError(-1013, 'Filter failure: NOTIONAL'); };
    h.rest.avgPrice.DOGEUSDT = 0.005;                        // 183 × 0.005 = 0.92 USDT < 1
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.pnl, null);
    assert.match(closed!.payload.reason, /^POLVO: Binance rechaza la venta \(Filter failure: NOTIONAL\)/);
});

test('rechazo por filtro con precio medio vendible: nunca es polvo; esperas 5, 10, 20, 40, 60, 60 s y aviso desde el tercero', async () => {
    const h = await makeClient();
    await openDoge(h);
    let rejectUntil = 7;
    h.rest.sellHook = (_s, _q, n) => {
        if (n <= rejectUntil) throw binanceHttpError(-1013, 'Filter failure: LOT_SIZE');
    };
    const alerts = () => h.telegram.messages.filter(m => m.includes('VENTA RECHAZADA')).length;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);   // rechazo 1
    assert.equal(alerts(), 0);
    for (const [i, wait] of [5000, 10000, 20000, 40000, 60000, 60000].entries()) {
        now += wait - 1;
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
        assert.equal(h.rest.sells.length, i + 1, `antes de ${wait} ms no se reintenta`);
        now += 1;
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);   // rechazo i + 2
        assert.equal(h.rest.sells.length, i + 2);
        assert.ok(h.client.getPosition('DOGEUSDT'), 'con el precio medio es vendible: no se da por polvo');
        if (i + 2 === 3) assert.equal(alerts(), 1);             // aviso en el tercer rechazo...
    }
    assert.equal(alerts(), 1);                                  // ...y no en cada uno de los siguientes
    // LOT_SIZE: en cada rechazo se olvida la caché de exchangeInfo del par antes de reintentar
    assert.deepEqual(h.rest.invalidations, Array(7).fill('DOGEUSDT'));
    assert.equal(h.brain.of('ledger_close').length, 0);
    // Binance acepta por fin: cierre normal
    now += 60000;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.reason, 'TAKE PROFIT ✅');
});

test('rechazo por filtro: el polvo se confirma con el margen sobre el mínimo (no basta con superarlo)', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = () => { throw binanceHttpError(-1013, 'Filter failure: NOTIONAL'); };
    h.rest.avgPrice.DOGEUSDT = 0.00548;                       // 183 × 0.00548 = 1.0028: sobre 1, bajo 1 × 1.01
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.match(h.brain.of('ledger_close')[0]!.payload.reason, /^POLVO: Binance rechaza la venta \(Filter failure: NOTIONAL\)/);
    assert.deepEqual(h.rest.invalidations, []);               // NOTIONAL no invalida la caché de cantidades
});

test('resto por debajo del mínimo tras vender una parte: se registra lo vendido con PnL, sin intentar el resto', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (s, _q, n) => (n === 1 ? h.rest.sellExecution(s, 170, 'EXPIRED') : undefined);
    h.rest.avgPrice.DOGEUSDT = 0.05;                          // 13 × 0.05 = 0.65 USDT < 1
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 1);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 170);
    assert.equal(typeof closed!.payload.pnl, 'number');
    assert.match(closed!.payload.reason, /^TAKE PROFIT ✅ \(quedan 13 DOGE sin vender\)$/);
});

test('Binance rechaza el resto tras vender una parte: se reintenta mientras sea vendible y se registra lo vendido al ser polvo', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (s, _q, n) => {
        if (n === 1) return h.rest.sellExecution(s, 170, 'EXPIRED');
        throw binanceHttpError(-1013, 'Filter failure: NOTIONAL');
    };
    h.rest.avgPrice.DOGEUSDT = 0.08;                          // 13 × 0.08 = 1.04: vendible con margen, Binance lo rechaza
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.ok(h.client.getPosition('DOGEUSDT'));             // lo vendido queda guardado en la posición
    for (const wait of [5000, 10000, 20000]) {
        now += wait;
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    }
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183', '13', '13', '13', '13']);
    assert.ok(h.client.getPosition('DOGEUSDT'));             // sigue sin ser polvo
    // el precio medio baja: 13 × 0.07 = 0.91 < 1 -> ya no es vendible; se registra lo vendido con su PnL
    h.rest.avgPrice.DOGEUSDT = 0.07;
    now += 40000;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells.length, 5);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 170);
    assert.equal(typeof closed!.payload.pnl, 'number');
    assert.match(closed!.payload.reason, /^TAKE PROFIT ✅ \(quedan 13 DOGE sin vender\)$/);
});

test('margen sobre minNotional: cerca del mínimo se usa el precio medio de Binance', async () => {
    const setup = (rest: any, brain: any) => {
        brain.openTrades = [{ order_id: 5, symbol: 'DOGEUSDT', entry_price: 0.08, take_profit: 0.0825, stop_loss: 0.0805,
            quantity: 13, net_quantity: 13, timestamp: 1 }];
        rest.fillPrice.DOGEUSDT = 0.08;
    };
    // último precio 0.07 (0.91 USDT) pero precio medio 0.08 (1.04 USDT): Binance la acepta, se vende
    const a = await makeClient(['DOGEUSDT'], ({ rest, brain }) => setup(rest, brain));
    a.rest.avgPrice.DOGEUSDT = 0.08;
    await a.send('DOGEUSDT', T0, 0.07, false);
    assert.equal(a.rest.sells.length, 1);
    // 13 × 0.0776 = 1.0088 USDT: supera el mínimo (1) pero no el margen del 1 %: polvo sin intentarlo
    const b = await makeClient(['DOGEUSDT'], ({ rest, brain }) => setup(rest, brain));
    b.rest.avgPrice.DOGEUSDT = 0.0776;
    await b.send('DOGEUSDT', T0, 0.0776, false);
    assert.equal(b.rest.sells.length, 0);
    assert.match(b.brain.of('ledger_close')[0]!.payload.reason, /^POLVO: 13 DOGE/);
    // lejos del mínimo no se consulta el precio medio
    const c = await makeClient();
    await openDoge(c);
    c.rest.avgPriceCalls = 0;
    await c.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(c.rest.avgPriceCalls, 0);
});

test('pausa de 5 s tras un fallo: un único reintento inmediato si el precio cae aún más bajo el SL', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => {
        if (n <= 2) throw binanceHttpError(-1003, 'Too much request weight used', 429);
    };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0804, false);   // SL, falla -> pausa
    assert.equal(h.rest.sells.length, 1);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0804, false);   // mismo precio: espera
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0806, false);   // sobre el SL: nada
    assert.equal(h.rest.sells.length, 1);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0803, false);   // más abajo: reintento inmediato (falla otra vez)
    assert.equal(h.rest.sells.length, 2);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);   // el adelanto no se encadena
    assert.equal(h.rest.sells.length, 2);
    now += 5001;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);
    assert.equal(h.rest.sells.length, 3);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

test('pausa tras un fallo en TP: no hay reintento inmediato aunque el precio suba', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => {
        if (n === 1) throw binanceHttpError(-1003, 'Too much request weight used', 429);
    };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0830, false);
    assert.equal(h.rest.sells.length, 1);
});

test('cooldown de 60 s tras un error de compra, por símbolo', async () => {
    const h = await makeClient();
    h.rest.buyHook = (symbol) => {
        if (symbol === 'DOGEUSDT' && h.rest.buys.length === 1) throw binanceHttpError(-1013, 'Filter failure: NOTIONAL');
    };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.ok(h.telegram.messages.some(m => m.includes('ERROR DE ORDEN: DOGEUSDT') && m.includes('Filter failure: NOTIONAL')));

    now += 30_000;
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, true);     // dentro del cooldown: ignorado (la vela sí se evalúa)
    assert.equal(h.rest.buys.length, 1);
    assert.equal(h.brain.of('evaluate').length, 2);

    h.brain.signals.push(BUY(65000, 66000, 64000));
    await h.send('BTCUSDT', T0 + CANDLE, 65000, true);        // otro símbolo no está afectado
    assert.ok(h.client.getPosition('BTCUSDT'));

    now += 30_001;
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + 2 * CANDLE, 0.0815, true);
    assert.ok(h.client.getPosition('DOGEUSDT'));
});

test('compra MARKET sin ejecutar (EXPIRED, executedQty 0): no hay posición y hay cooldown', async () => {
    const h = await makeClient();
    h.rest.buyHook = (symbol) => {
        if (h.rest.buys.length === 1) {
            return { orderId: 1, clientOrderId: 'x', status: 'EXPIRED', executedQty: 0, quoteQty: 0, avgPrice: 0, fills: [],
                     fees: { baseQty: 0, totalQuote: 0, detail: '', unpriced: [] } };
        }
        return undefined;
    };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_open').length, 0);
    assert.equal(h.brain.of('ledger_cancel')[0]!.payload.reason, 'SIN EJECUTAR (EXPIRED)');
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, true);
    assert.equal(h.rest.buys.length, 1);
});

// La orden sin confirmar lleva el newClientOrderId que generó Node (el de la fila PENDING)
const unknownBuy = (cid = 'bot_b_xyz') => new OrderStatusUnknownError('DOGEUSDT', cid, new Error('timeout'));

test('compra sin confirmar que resulta ejecutada: se adopta con los fills reales y ledger_open', async () => {
    const h = await makeClient();
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    h.rest.lookupQueue = [unknownBuy(), h.rest.buyExecution('DOGEUSDT', 184, 0.08153)];  // 2.ª consulta la encuentra
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.ok(p, 'posición adoptada');
    assert.equal(p.quantity, 184);
    close(p.entryPrice, 0.08153);
    close(p.netQuantity, 183.816);
    assert.equal(h.rest.lookups.length, 2);
    const [open] = h.brain.of('ledger_open');
    assert.equal(open!.payload.order_id, p.orderId);
    close(open!.payload.entry_price, 0.08153);
    assert.ok(h.telegram.messages.some(m => m.includes('NUEVA COMPRA') && m.includes('confirmada tras consultarla')));
});

test('compra sin confirmar resuelta: los precios vistos mientras tanto se revisan contra el SL', async () => {
    const h = await makeClient();
    const gate = deferred();
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    const lookup = h.rest.lookupOrder.bind(h.rest);
    h.rest.lookupOrder = async (s: string, id: string) => { await gate.promise; return lookup(s, id); };
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    const buying = h.send('DOGEUSDT', T0, 0.0815, true);
    await flush();
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0804, false);   // bajo el SL mientras se consultaba la compra
    gate.resolve();
    await buying;
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.reason, 'STOP LOSS ⚠️');
});

/** Precio de DOGE en la vela T0 + CANDLE pasados `ms` desde ahora (avanza el reloj de la prueba). */
async function tickAfter(h: Awaited<ReturnType<typeof makeClient>>, ms: number, price = 0.0815, closed = false) {
    now += ms;
    await h.send('DOGEUSDT', T0 + CANDLE, price, closed);
}

test('compra "no existe": se reconsulta a los 10, 30 y 90 s antes de cancelarla; mientras, bloquea compras y no frena el handler', async () => {
    const h = await makeClient();
    const sleeps: number[] = [];
    (h.client as any).sleep = async (ms: number) => { sleeps.push(ms); };
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    h.rest.lookupQueue = [null];                                  // la primera consulta: "no existe" (por ahora)
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    const cid = h.rest.buys[0]!.clientOrderId!;
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.rest.lookups.length, 1);
    assert.deepEqual(sleeps, []);                                 // ninguna espera dentro del handler
    assert.equal(h.brain.of('ledger_cancel').length, 0);          // la fila sigue PENDING (compra dudosa)
    const lookupsAt = (n: number) => assert.equal(h.rest.lookups.length, n);
    await tickAfter(h, LATE_ORDER_RECHECKS_MS[0]! - 1);  lookupsAt(1);   // antes de 10 s: no se consulta
    h.rest.lookupQueue = [null];
    await tickAfter(h, 1);                                 lookupsAt(2);   // 10 s: "no existe" otra vez
    await tickAfter(h, LATE_ORDER_RECHECKS_MS[1]! - 1);  lookupsAt(2);
    h.rest.lookupQueue = [null];
    await tickAfter(h, 1);                                 lookupsAt(3);   // +30 s
    // a +129 s (pasado el cooldown de 60 s, antes de la última consulta) la moneda sigue sin abrir otra compra
    now += LATE_ORDER_RECHECKS_MS[2]! - 1;
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + 2 * CANDLE, 0.0815, true);
    assert.equal(h.rest.buys.length, 1);
    lookupsAt(3);
    assert.equal(h.brain.of('ledger_cancel').length, 0);
    h.rest.lookupQueue = [null];
    await tickAfter(h, 1);                                 lookupsAt(4);   // +90 s: ya no existe -> CANCELLED
    const [cancel] = h.brain.of('ledger_cancel');
    assert.deepEqual(cancel!.payload, { client_order_id: cid, symbol: 'DOGEUSDT', reason: LATE_BUY_CANCEL_REASON });
    assert.ok(h.telegram.messages.some(m => m.includes('COMPRA DESCARTADA: DOGEUSDT')));
    // la moneda vuelve a poder comprar
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + 3 * CANDLE, 0.0815, true);
    assert.equal(h.rest.buys.length, 2);
});

test('compra "no existe" que aparece tarde (a los ~40 s): se adopta y los precios vistos durante la duda se revisan contra el SL', async () => {
    const h = await makeClient();
    h.rest.buyHook = (_s, cid) => { throw new OrderNotFoundError('DOGEUSDT', cid!, new Error('timeout')); };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.equal(h.rest.lookups.length, 0);                       // Binance ya dijo "no existe": primera espera de 10 s
    await tickAfter(h, 2000, 0.0804);                              // bajo el SL mientras la compra es dudosa
    h.rest.lookupQueue = [null];
    await tickAfter(h, LATE_ORDER_RECHECKS_MS[0]!, 0.0810);       // 10 s: sigue sin aparecer
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    await tickAfter(h, LATE_ORDER_RECHECKS_MS[1]!, 0.0810);       // +30 s: aparece -> se adopta
    assert.equal(h.brain.of('ledger_cancel').length, 0);
    assert.equal(h.brain.of('ledger_open')[0]!.payload.client_order_id, h.rest.buys[0]!.clientOrderId);
    // el precio de 0.0804 visto durante la duda ya tocó el SL: se vende al adoptarla
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.reason, 'STOP LOSS ⚠️');
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

test('compra sin confirmar tras todas las consultas: queda PENDING, bloquea compras y se resuelve con los precios', async () => {
    const h = await makeClient();
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    h.rest.lookupQueue = [unknownBuy(), unknownBuy(), unknownBuy()];
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    const cid = h.rest.buys[0]!.clientOrderId!;
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.rest.lookups.length, 3);
    assert.ok(h.telegram.messages.some(m => m.includes('COMPRA SIN CONFIRMAR') && m.includes(cid)));
    assert.equal(h.brain.of('ledger_cancel').length, 0);         // la fila sigue PENDING
    // mientras no se resuelva no se abre otra compra de la moneda (ni siquiera pasado el cooldown)
    now += 61_000;
    h.rest.lookupQueue = [unknownBuy()];
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, true);
    assert.equal(h.rest.buys.length, 1);
    assert.equal(h.rest.lookups.length, 4);                       // se reconsultó con este precio
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, false);         // dentro de los 5 s: no se consulta
    assert.equal(h.rest.lookups.length, 4);
    // Binance responde: se ejecutó -> se adopta (su fila PENDING pasa a OPEN)
    now += 5001;
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, false);
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.equal(p.quantity, 184);
    assert.equal(h.brain.of('ledger_open')[0]!.payload.client_order_id, cid);
});

test('compra sin resolver adoptada: mientras se registra en el ledger no se abre otra compra de la moneda', async () => {
    const h = await makeClient();
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    h.rest.lookupQueue = [unknownBuy(), unknownBuy(), unknownBuy()];
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);                  // queda PENDING sin resolver
    assert.equal(h.rest.buys.length, 1);
    // Binance responde que sí se ejecutó, pero registrarla en el ledger tarda
    h.rest.buyHook = null;
    now += 61_000;                                                // pasado el cooldown del error
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    const gate = deferred();
    const ask = h.brain.ask.bind(h.brain);
    h.brain.ask = async (type: string, payload?: any) => {
        if (type === 'ledger_open') await gate.promise;
        return ask(type, payload);
    };
    const adopting = h.send('DOGEUSDT', T0 + CANDLE, 0.0815, false);
    await flush();
    // vela cerrada con BUY mientras se registra la compra adoptada: no puede abrir una segunda posición
    h.brain.signals.push(BUY(0.0816, 0.0826, 0.0806));
    const closed = h.send('DOGEUSDT', T0 + CANDLE, 0.0816, true);
    await flush();
    gate.resolve();
    await Promise.all([adopting, closed]);
    assert.equal(h.rest.buys.length, 1, 'una segunda compra con la primera aún sin registrar');
    assert.equal(h.client.getPosition('DOGEUSDT')!.quantity, 184);
    assert.equal(h.brain.of('ledger_pending').length, 1);
});

test('compra sin respuesta que después resulta no existir: el primer "no existe" inicia las esperas de 10, 30 y 90 s', async () => {
    const h = await makeClient();
    h.rest.buyHook = (_s, cid) => { throw unknownBuy(cid); };
    h.rest.lookupQueue = [unknownBuy(), unknownBuy(), unknownBuy()];
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);                   // sin respuesta: se reintenta cada 5 s
    assert.equal(h.rest.lookups.length, 3);
    h.rest.lookupQueue = [null];
    await tickAfter(h, 5001);                                     // primer "no existe": aún no se cancela
    assert.equal(h.rest.lookups.length, 4);
    for (const wait of LATE_ORDER_RECHECKS_MS) {
        await tickAfter(h, wait - 1);                             // antes de la espera: ni consulta ni cancelación
        assert.equal(h.brain.of('ledger_cancel').length, 0);
        h.rest.lookupQueue = [null];
        await tickAfter(h, 1);
    }
    assert.equal(h.rest.lookups.length, 4 + LATE_ORDER_RECHECKS_MS.length);
    assert.equal(h.brain.of('ledger_cancel')[0]!.payload.reason, LATE_BUY_CANCEL_REASON);
    // ya se puede comprar otra vez
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0 + 2 * CANDLE, 0.0815, true);
    assert.equal(h.rest.buys.length, 2);
});

test('compra rechazada por Binance o sin ejecutar: su fila PENDING pasa a CANCELLED', async () => {
    const h = await makeClient();
    h.rest.buyHook = () => { throw binanceHttpError(-2010, 'Account has insufficient balance for requested action.'); };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.match(h.brain.of('ledger_cancel')[0]!.payload.reason, /^RECHAZADA: Account has insufficient balance/);
    assert.equal(h.brain.of('ledger_cancel')[0]!.payload.client_order_id, h.rest.buys[0]!.clientOrderId);
});

test('si el ledger no registra la compra PENDING, no se envía la orden', async () => {
    const h = await makeClient();
    h.brain.ledgerPendingResult = { error: 'Permission denied' };
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);
    assert.equal(h.rest.buys.length, 0);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.ok(h.telegram.messages.some(m => m.includes('compra pendiente') && m.includes('no se envía')));
});

test('el tamaño por operación es el que se le pasa (el de Python) y debe ser positivo', async () => {
    const rest = new FakeRest();
    const brain = new FakeBrain();
    const sockets: FakeSocket[] = [];
    const client = new BinanceWSClient(['DOGEUSDT'], 20, {
        rest, brain, telegram: new FakeTelegram(), sleep: async () => {},
        createSocket: url => { const s = new FakeSocket(url); sockets.push(s); return s; }
    });
    await client.start();
    brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await sockets[0]!.emit('message', klineMessage('DOGEUSDT', T0, 0.0815, true));
    assert.deepEqual(rest.buys.map(({ clientOrderId, ...b }) => b), [{ symbol: 'DOGEUSDT', quote: 20, ref: 0.0815 }]);
    assert.throws(() => new BinanceWSClient(['DOGEUSDT'], 0), /Tamaño por operación/);
    assert.throws(() => new BinanceWSClient(['DOGEUSDT'], Number.NaN), /Tamaño por operación/);
});

test('se suscribe a las velas que da Python en el handshake (config.KLINE_INTERVAL)', async () => {
    const sockets: FakeSocket[] = [];
    const client = new BinanceWSClient(['DOGEUSDT', 'BTCUSDT'], 15, {
        rest: new FakeRest(), brain: new FakeBrain(), telegram: new FakeTelegram(), sleep: async () => {},
        createSocket: url => { const s = new FakeSocket(url); sockets.push(s); return s; }, klineInterval: '1h'
    });
    await client.start();
    assert.match(sockets[0]!.url, /\/stream\?streams=dogeusdt@kline_1h\/btcusdt@kline_1h$/);
});

test('si el ledger falla al abrir, la posición se gestiona igual y se avisa', async () => {
    const h = await makeClient();
    h.brain.ledgerOpenResult = { error: 'Permission denied' };
    await openDoge(h);
    assert.ok(h.telegram.messages.some(m => m.includes('LEDGER') && m.includes('compra')));
});

test('comisión de compra en BNB: no reduce la cantidad vendible y suma al PnL', async () => {
    const h = await makeClient();
    h.rest.buyFeeAsset = 'BNB';
    await openDoge(h);
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.equal(p.netQuantity, 184);
    // 0.1 % de 14.996 USDT pagado en BNB a 600 (Binance lo da con 8 decimales: 0.00002499 BNB)
    close(p.entryFeeQuote, Number((184 * 0.0815 * 0.001 / 600).toFixed(8)) * 600);
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
    assert.equal(h.rest.sells[0]!.qty, '184');
    const quote = 184 * 0.0825;
    close(h.brain.of('ledger_close')[0]!.payload.pnl, quote - quote * 0.001 - p.entryQuote - p.entryFeeQuote);
});

test('conexión muerta sin close: sin mensajes ni pings durante 2 min se corta y se reconecta', async () => {
    mock.timers.enable({ apis: ['setTimeout', 'setInterval'] });
    try {
        const h = await makeClient();
        // con los pings de Binance (cada 20 s) la conexión sigue aunque no lleguen velas
        for (let i = 0; i < 10; i++) {
            now += 20_000;
            h.sockets[0]!.emit('ping');
            mock.timers.tick(STALE_CHECK_MS);
        }
        await h.send('DOGEUSDT', T0, 0.08, false);
        assert.equal(h.sockets[0]!.terminated, false);
        // silencio total: al llegar a STALE_SOCKET_MS se corta y el 'close' reconecta
        now += STALE_SOCKET_MS - 1;
        mock.timers.tick(STALE_CHECK_MS);
        assert.equal(h.sockets[0]!.terminated, false);
        now += 1;
        mock.timers.tick(STALE_CHECK_MS);
        assert.equal(h.sockets[0]!.terminated, true);
        h.sockets[0]!.emit('close');
        mock.timers.tick(1000);
        assert.equal(h.sockets.length, 2);
        // close() detiene la vigilancia
        h.client.close();
        now += 10 * STALE_SOCKET_MS;
        mock.timers.tick(STALE_CHECK_MS);
        assert.equal(h.sockets[1]!.terminated, false);
    } finally {
        mock.timers.reset();
    }
});

test('reconexión con espera creciente; open la reinicia; close() la detiene', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    try {
        const h = await makeClient();
        h.sockets[0]!.emit('close');
        mock.timers.tick(999);
        assert.equal(h.sockets.length, 1);
        mock.timers.tick(1);
        assert.equal(h.sockets.length, 2);
        h.sockets[1]!.emit('close');
        mock.timers.tick(1999);
        assert.equal(h.sockets.length, 2);
        mock.timers.tick(1);
        assert.equal(h.sockets.length, 3);
        h.sockets[2]!.emit('open');
        h.sockets[2]!.emit('close');
        mock.timers.tick(1000);
        assert.equal(h.sockets.length, 4);
        // las velas llegan por el socket nuevo
        await h.send('DOGEUSDT', T0, 0.08, true);
        assert.equal(h.brain.of('evaluate').length, 1);
        h.client.close();
        assert.equal(h.sockets[3]!.closed, true);
        h.sockets[3]!.emit('close');
        mock.timers.tick(120_000);
        assert.equal(h.sockets.length, 4);
    } finally {
        mock.timers.reset();
    }
});

test('arranque: posición OPEN con saldo se gestiona; sin saldo se cierra en el ledger y se avisa', async () => {
    const h = await makeClient(['DOGEUSDT', 'BTCUSDT'], ({ brain, rest }) => {
        brain.openTrades = [
            { order_id: 10, symbol: 'DOGEUSDT', entry_price: 0.0815, take_profit: 0.0825, stop_loss: 0.0805, quantity: 184,
              net_quantity: 183.816, entry_quote: 15, entry_fee_usdt: 0.015, timestamp: 5 },
            { order_id: 11, symbol: 'BTCUSDT', entry_price: 65000, take_profit: 66000, stop_loss: 64000, quantity: 0.00023,
              net_quantity: 0.00022977, entry_quote: 14.95, entry_fee_usdt: 0.01495, timestamp: 6 }
        ];
        rest.balances.set('DOGE', 200);
        rest.balances.set('BTC', 0);
    });
    const doge = h.client.getPosition('DOGEUSDT')!;
    assert.equal(doge.orderId, 10);
    close(doge.netQuantity, 183.816);
    close(doge.entryFeeBaseQty, 0.184);
    assert.equal(h.client.getPosition('BTCUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.order_id, 11);
    assert.equal(closed!.payload.pnl, null);
    assert.match(closed!.payload.reason, /^SIN SALDO al arrancar: libre 0 BTC/);
    assert.ok(h.telegram.messages.some(m => m.includes('CIERRE SIN VENTA: BTCUSDT') && m.includes('SIN SALDO al arrancar')));
    // el socket se abrió después de leer el ledger y de cerrar la posición sin saldo
    assert.equal(h.sockets.length, 1);
    assert.equal(h.sockets[0]!.asksAtCreation, h.brain.asks.length);
});

test('arranque: saldo algo menor (vendible) ajusta la cantidad; sin saldo legible se mantiene', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [{ order_id: 20, symbol: 'DOGEUSDT', entry_price: 0.0815, take_profit: 0.0825, stop_loss: 0.0805,
            quantity: 184, net_quantity: null, timestamp: 1 }];  // fila antigua: sin net_quantity
        rest.balances.set('DOGE', 183.816);
    });
    assert.equal(h.client.getPosition('DOGEUSDT')!.netQuantity, 183);
    assert.equal(h.brain.of('ledger_close').length, 0);

    const h2 = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [{ order_id: 21, symbol: 'DOGEUSDT', entry_price: 0.0815, take_profit: 0.0825, stop_loss: 0.0805,
            quantity: 184, timestamp: 1 }];
        rest.balanceError = new Error('VPN');
    });
    assert.equal(h2.client.getPosition('DOGEUSDT')!.netQuantity, 184);
});

test('arranque: varias OPEN del mismo símbolo -> se gestiona la más reciente', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain }) => {
        brain.openTrades = [
            { order_id: 30, symbol: 'DOGEUSDT', entry_price: 0.08, take_profit: 0.09, stop_loss: 0.07, quantity: 100, timestamp: 100 },
            { order_id: 31, symbol: 'DOGEUSDT', entry_price: 0.081, take_profit: 0.091, stop_loss: 0.071, quantity: 100, timestamp: 200 },
            { order_id: 29, symbol: 'DOGEUSDT', entry_price: 0.079, take_profit: 0.089, stop_loss: 0.069, quantity: 100, timestamp: 50 }
        ];
    });
    assert.equal(h.client.getPosition('DOGEUSDT')!.orderId, 31);
});

const OPEN_DOGE = { order_id: 40, symbol: 'DOGEUSDT', entry_price: 0.0815, take_profit: 0.0825, stop_loss: 0.0805, quantity: 184,
    net_quantity: 183.816, entry_quote: 14.996, entry_fee_usdt: 0.015, timestamp: 1 };

test('arranque: la compra no existe en Binance -> se cierra en el ledger (ORDEN INEXISTENTE)', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.orders[40] = null;
    });
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.order_id, 40);
    assert.equal(closed!.payload.symbol, 'DOGEUSDT');      // Binance numera las órdenes por símbolo
    assert.equal(closed!.payload.pnl, null);
    assert.match(closed!.payload.reason, /^ORDEN INEXISTENTE al arrancar/);
});

test('arranque: la compra existe pero no se ejecutó (LIMIT antigua sin llenar) -> COMPRA SIN EJECUTAR', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.orders[40] = { orderId: 40, status: 'NEW', executedQty: '0.00000000' };
    });
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.match(h.brain.of('ledger_close')[0]!.payload.reason, /^COMPRA SIN EJECUTAR al arrancar: la orden 40 está NEW/);
});

test('arranque: la posición ya se vendió (venta posterior en myTrades) -> se registra esa salida real', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.trades = [
            trade({ id: 500, orderId: 40, isBuyer: true, qty: 184, price: 0.0815, fee: 0.184, feeAsset: 'DOGE' }),
            trade({ id: 501, orderId: 41, isBuyer: false, qty: 100, price: 0.0826, fee: 0.00826 }),
            trade({ id: 502, orderId: 41, isBuyer: false, qty: 83, price: 0.0825, fee: 0.0068475 })
        ];
    });
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 183);
    close(closed!.payload.exit_quote, 100 * 0.0826 + 83 * 0.0825);
    close(closed!.payload.exit_fee_usdt, 0.00826 + 0.0068475);
    assert.equal(closed!.payload.exit_order_id, 41);
    assert.equal(closed!.payload.exit_trigger_price, null);
    // los 0.816 DOGE que quedan (bajo el paso) se valoran al precio medio de la venta
    const avgExit = (100 * 0.0826 + 83 * 0.0825) / 183;
    close(closed!.payload.residual_quantity, 0.816);
    close(closed!.payload.pnl, (100 * 0.0826 + 83 * 0.0825) + 0.816 * avgExit - 14.996 - (0.015 - 0.184 * 0.0815) -
        (0.00826 + 0.0068475));
    assert.equal(closed!.payload.reason, 'VENTA YA EJECUTADA (detectada al arrancar)');
});

test('arranque: una compra posterior de otra posición (o manual) corta la búsqueda de ventas de esta', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.trades = [
            trade({ id: 500, orderId: 40, isBuyer: true, qty: 184, price: 0.0815, fee: 0.184, feeAsset: 'DOGE' }),
            trade({ id: 501, orderId: 77, isBuyer: true, qty: 200, price: 0.0820 }),     // compra manual
            trade({ id: 502, orderId: 78, isBuyer: false, qty: 200, price: 0.0830 })     // y su venta
        ];
    });
    // la venta 78 no es de la posición 40: sigue abierta y sin tramos vendidos
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.equal(p.orderId, 40);
    assert.equal(p.exitParts, undefined);
    assert.equal(h.brain.of('ledger_close').length, 0);
});

test('arranque: venta posterior parcial -> la salida sigue en curso: se vende el resto con el primer precio y suma ambos tramos', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.trades = [
            trade({ id: 500, orderId: 40, isBuyer: true, qty: 184, price: 0.0815 }),
            trade({ id: 501, orderId: 41, isBuyer: false, qty: 100, price: 0.0812 })
        ];
    });
    assert.ok(h.client.getPosition('DOGEUSDT'));
    await h.send('DOGEUSDT', T0, 0.0812, false);             // dentro del rango TP/SL
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['83']);   // solo lo que falta
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 183);
    assert.equal(closed!.payload.reason, 'SALIDA EN CURSO (iniciada antes de arrancar)');
});

test('salida decidida que falla: se completa aunque el precio vuelva al rango, con el motivo y nivel originales', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw binanceHttpError(-1003, 'Too much request weight used', 429); };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);   // TP tocado, la venta falla
    now += 5001;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, false);   // el precio volvió al rango: la salida sigue
    assert.equal(h.rest.sells.length, 2);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.reason, 'TAKE PROFIT ✅');
    assert.equal(closed!.payload.exit_trigger_price, 0.0826);
});

test('arranque sin respuesta de Binance: la posición se conserva pero no se vende hasta verificarla', async () => {
    const getOrder = FakeRest.prototype.getOrder;
    let down = true;
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.getOrder = async (s: string, id: number) => {
            if (down) throw binanceHttpError(-1000, 'Internal error', 503);
            return getOrder.call(rest, s, id);
        };
        // Antes del reinicio ya se habían vendido 100 de los 183 DOGE vendibles
        rest.trades = [
            trade({ id: 500, orderId: 40, isBuyer: true, qty: 184, price: 0.0815, fee: 0.184, feeAsset: 'DOGE' }),
            trade({ id: 501, orderId: 41, isBuyer: false, qty: 100, price: 0.0803, fee: 0.00803 })
        ];
        rest.balances.set('DOGE', 83.816);
    });
    assert.ok(h.client.getPosition('DOGEUSDT')!.startupCheckPending);
    assert.equal(h.brain.of('ledger_close').length, 0);
    assert.ok(h.telegram.messages.some(m => m.includes('POSICIÓN SIN VERIFICAR: DOGEUSDT')));

    // SL tocado sin poder verificar: no se vende (vender 183 perdería la venta de 100 y fallaría por saldo)
    await h.send('DOGEUSDT', T0, 0.0800, false);
    assert.equal(h.rest.sells.length, 0);
    now += 1000;
    await h.send('DOGEUSDT', T0, 0.0799, false);              // dentro de la pausa de 5 s: ni siquiera se consulta
    assert.equal(h.rest.sells.length, 0);

    // Binance vuelve: se detecta la venta previa y solo se vende el resto; el cierre suma ambos tramos
    down = false;
    now += 5000;
    h.rest.fillPrice.DOGEUSDT = 0.0799;
    await h.send('DOGEUSDT', T0, 0.0799, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['83']);
    const [closed] = h.brain.of('ledger_close');
    assert.equal(closed!.payload.exit_quantity, 183);
    close(closed!.payload.exit_quote, 100 * 0.0803 + 83 * 0.0799);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

const PENDING_DOGE = { symbol: 'DOGEUSDT', status: 'PENDING', client_order_id: 'bot_b_crash_1', signal_price: 0.0815,
    take_profit: 0.0825, stop_loss: 0.0805, order_id: null, timestamp: 7 };

test('arranque: compra PENDING que se ejecutó antes de morir el proceso -> se adopta (fila a OPEN) y se verifica', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.pendingTrades = [PENDING_DOGE];
        rest.lookupQueue = [rest.buyExecution('DOGEUSDT', 184, 0.08152)];
    });
    assert.deepEqual(h.rest.lookups, [{ symbol: 'DOGEUSDT', clientOrderId: 'bot_b_crash_1' }]);
    const [open] = h.brain.of('ledger_open');
    assert.equal(open!.payload.client_order_id, 'bot_b_crash_1');   // misma fila PENDING -> OPEN
    assert.equal(open!.payload.quantity, 184);
    close(open!.payload.entry_price, 0.08152);
    assert.equal(open!.payload.signal_price, 0.0815);
    const p = h.client.getPosition('DOGEUSDT')!;
    assert.ok(p && !p.startupCheckPending);
    assert.equal(p.takeProfit, 0.0825);
    assert.equal(p.stopLoss, 0.0805);
    // ...y pasó por la verificación normal del arranque (orden en Binance, ventas posteriores y saldo)
    assert.ok(h.telegram.messages.some(m => m.includes('COMPRA RECUPERADA: DOGEUSDT')));
    await h.send('DOGEUSDT', T0, 0.0826, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183']);
});

test('arranque: compra PENDING que Binance no muestra: el WebSocket conecta sin esperas y se cancela tras ~2 min de consultas', async () => {
    const sleeps: number[] = [];
    const rest = new FakeRest();
    const brain = new FakeBrain();
    brain.pendingTrades = [PENDING_DOGE];
    rest.lookupQueue = [null];
    const sockets: FakeSocket[] = [];
    const client = new BinanceWSClient(['DOGEUSDT'], 15, {
        rest, brain, telegram: new FakeTelegram(), sleep: async (ms: number) => { sleeps.push(ms); },
        createSocket: url => { const s = new FakeSocket(url); sockets.push(s); return s; }
    });
    await client.start();
    assert.equal(rest.lookups.length, 1);                         // una sola consulta al arrancar...
    assert.deepEqual(sleeps, []);                                 // ...sin esperas antes de conectar
    assert.equal(sockets.length, 1);
    assert.equal(brain.of('ledger_cancel').length, 0);            // sigue PENDING: se resuelve con los precios
    const send = (price: number) => sockets[0]!.emit('message', klineMessage('DOGEUSDT', T0, price, false));
    for (const wait of LATE_ORDER_RECHECKS_MS) {
        now += wait - 1;
        await send(0.0815);
        assert.equal(brain.of('ledger_cancel').length, 0);
        rest.lookupQueue = [null];
        now += 1;
        await send(0.0815);
    }
    assert.equal(rest.lookups.length, 1 + LATE_ORDER_RECHECKS_MS.length);
    assert.deepEqual(brain.of('ledger_cancel')[0]!.payload,
        { client_order_id: 'bot_b_crash_1', symbol: 'DOGEUSDT', reason: LATE_BUY_CANCEL_REASON });
    assert.equal(client.getPosition('DOGEUSDT'), undefined);
    client.close();
});

test('arranque: compra PENDING que aparece a los 10 s -> se adopta en segundo plano y revisa los precios vistos', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.pendingTrades = [PENDING_DOGE];
        rest.lookupQueue = [null];
    });
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.ok(h.telegram.messages.some(m => m.includes('COMPRA PENDIENTE SIN VERIFICAR: DOGEUSDT') && m.includes('aún no la muestra')));
    now += 3000;
    await h.send('DOGEUSDT', T0, 0.0826, false);                  // por encima del TP (0.0825) mientras es dudosa
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    now += LATE_ORDER_RECHECKS_MS[0]!;
    await h.send('DOGEUSDT', T0, 0.0820, false);
    assert.equal(h.brain.of('ledger_cancel').length, 0);
    assert.equal(h.brain.of('ledger_open')[0]!.payload.client_order_id, 'bot_b_crash_1');
    assert.equal(h.rest.sells.length, 1);                         // el TP visto durante la duda se aplica al adoptarla
    assert.equal(h.brain.of('ledger_close')[0]!.payload.reason, 'TAKE PROFIT ✅');
});

test('arranque: varias filas PENDING se consultan a la vez (no se suman sus esperas)', async () => {
    const gate = deferred();
    let started = 0;
    const h0 = makeClient(['DOGEUSDT', 'BTCUSDT'], ({ brain, rest }) => {
        brain.pendingTrades = [PENDING_DOGE, { ...PENDING_DOGE, symbol: 'BTCUSDT', client_order_id: 'bot_b_crash_2' }];
        const lookup = rest.lookupOrder.bind(rest);
        rest.lookupOrder = async (s: string, id: string) => { started++; await gate.promise; return lookup(s, id); };
        rest.lookupQueue = [null, null];
    });
    await flush();
    assert.equal(started, 2);                                     // las dos consultas en marcha antes de resolverse
    gate.resolve();
    const h = await h0;
    assert.equal(h.sockets.length, 1);
    assert.equal(h.brain.of('ledger_cancel').length, 0);
});

test('arranque: compra PENDING sin respuesta -> sigue PENDING, bloquea compras y se resuelve con los precios', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.pendingTrades = [PENDING_DOGE];
        rest.lookupQueue = [new OrderStatusUnknownError('DOGEUSDT', 'bot_b_crash_1', new Error('timeout'))];
    });
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_cancel').length, 0);
    assert.ok(h.telegram.messages.some(m => m.includes('COMPRA PENDIENTE SIN VERIFICAR: DOGEUSDT')));
    h.brain.signals.push(BUY(0.0815, 0.0825, 0.0805));
    await h.send('DOGEUSDT', T0, 0.0815, true);                // dentro de los 5 s: ni consulta ni compra nueva
    assert.equal(h.rest.buys.length, 0);
    assert.equal(h.rest.lookups.length, 1);
    now += 5001;
    h.rest.lookupQueue = [h.rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0815, false);
    assert.ok(h.client.getPosition('DOGEUSDT'));
    assert.equal(h.brain.of('ledger_open')[0]!.payload.client_order_id, 'bot_b_crash_1');
});

test('arranque: compra PENDING adoptada cuya fila no se pudo pasar a OPEN -> se gestiona igual', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.pendingTrades = [PENDING_DOGE];
        brain.ledgerOpenResult = { error: 'Permission denied' };
        rest.lookupQueue = [rest.buyExecution('DOGEUSDT', 184, 0.0815)];
    });
    assert.ok(h.client.getPosition('DOGEUSDT'));
    assert.ok(h.telegram.messages.some(m => m.includes('LEDGER') && m.includes('compra')));
});

test('venta sin respuesta que Binance dice que no existe: no se reenvía en el acto; se reconsulta pasados 10 s', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw unknownSell('bot_s_late'); };
    h.rest.lookupQueue = [null];                              // "no existe" (por ahora)
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    assert.equal(h.rest.sells.length, 1);
    assert.ok(h.client.getPosition('DOGEUSDT'));
    now += 9999;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);     // ni siquiera un SL más bajo adelanta la reconsulta
    assert.equal(h.rest.lookups.length, 1);
    // aparece tarde (-1007): la venta sí se ejecutó; no se vende otra vez
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 183)];
    now += 2;
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);
    assert.equal(h.rest.lookups.length, 2);
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.exit_quantity, 183);
});

test('venta "no existe" (OrderNotFoundError): se reconsulta a los 10, 30 y 90 s y solo entonces se vende otra vez', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw new OrderNotFoundError('DOGEUSDT', 'bot_s_gone', new Error('timeout')); };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.rest.lookups.length, 0);
    assert.ok(h.telegram.messages.some(m => m.includes('VENTA SIN CONFIRMAR: DOGEUSDT') && m.includes('~2 min')));
    for (const [i, wait] of LATE_ORDER_RECHECKS_MS.entries()) {
        now += wait - 1;
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0790, false);   // ni un SL más bajo adelanta la consulta ni reenvía
        assert.equal(h.rest.lookups.length, i);
        assert.equal(h.rest.sells.length, 1);
        now += 1;
        h.rest.lookupQueue = [null];
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
        assert.equal(h.rest.lookups.length, i + 1);
    }
    // tras ~2 min sin aparecer, la venta se da por no enviada y se vende otra vez
    assert.equal(h.rest.sells.length, 2);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
});

test('venta "no existe" que aparece a los ~40 s: no se vende dos veces y se registra esa venta', async () => {
    const h = await makeClient();
    await openDoge(h);
    h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw new OrderNotFoundError('DOGEUSDT', 'bot_s_late', new Error('timeout')); };
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);
    now += LATE_ORDER_RECHECKS_MS[0]!;
    h.rest.lookupQueue = [null];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);         // 10 s: sigue sin aparecer (antes se reenviaba aquí)
    assert.equal(h.rest.sells.length, 1);
    now += LATE_ORDER_RECHECKS_MS[1]!;
    h.rest.lookupQueue = [h.rest.sellExecution('DOGEUSDT', 183)];
    await h.send('DOGEUSDT', T0 + CANDLE, 0.0805, false);         // +30 s: aparece
    assert.equal(h.rest.sells.length, 1);
    assert.equal(h.client.getPosition('DOGEUSDT'), undefined);
    assert.equal(h.brain.of('ledger_close')[0]!.payload.exit_quantity, 183);
});

test('arranque: si no se puede leer el saldo, la posición también queda pendiente de verificar', async () => {
    const h = await makeClient(['DOGEUSDT'], ({ brain, rest }) => {
        brain.openTrades = [OPEN_DOGE];
        rest.balanceError = binanceHttpError(-1000, 'Internal error', 503);
    });
    assert.ok(h.client.getPosition('DOGEUSDT')!.startupCheckPending);
    await h.send('DOGEUSDT', T0, 0.0826, false);              // TP: sin saldo legible no se vende
    assert.equal(h.rest.sells.length, 0);
    h.rest.balanceError = null;
    now += 5001;
    await h.send('DOGEUSDT', T0, 0.0826, false);
    assert.deepEqual(h.rest.sells.map(s => s.qty), ['183']);
});

test('sin promesas sin capturar: Telegram que rechaza o lanza, errores de REST y de ledger', async () => {
    const seen: unknown[] = [];
    const onRejection = (reason: unknown) => seen.push(reason);
    process.on('unhandledRejection', onRejection);
    try {
        const h = await makeClient();
        let calls = 0;
        h.telegram.sendMessage = (() => {
            calls++;
            if (calls % 2) return Promise.reject(new Error('telegram caído'));
            throw new Error('telegram lanza');
        }) as any;
        h.brain.ledgerOpenResult = { error: 'Permission denied' };
        h.brain.ledgerCloseResult = { error: 'Permission denied' };
        await openDoge(h);
        h.rest.sellHook = (_s, _q, n) => { if (n === 1) throw binanceHttpError(-1003, 'Too much request weight used', 429); };
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
        now += 5001;
        await h.send('DOGEUSDT', T0 + CANDLE, 0.0826, false);
        h.rest.buyHook = () => { throw binanceHttpError(-2010, 'Account has insufficient balance for requested action.'); };
        h.brain.signals.push(BUY(65000, 66000, 64000));
        await h.send('BTCUSDT', T0 + CANDLE, 65000, true);
        await h.sockets[0]!.emit('message', Buffer.from('no es json'));
        await flush(10);
        assert.ok(calls >= 4);
        assert.deepEqual(seen, []);
    } finally {
        process.off('unhandledRejection', onRejection);
    }
});

test('reconexión: si crear el socket falla, no escapa del temporizador y se reintenta', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    try {
        let fail = true;
        const sockets: FakeSocket[] = [];
        const client = new BinanceWSClient(['DOGEUSDT'], 15, {
            rest: new FakeRest(), brain: new FakeBrain(), telegram: new FakeTelegram(), sleep: async () => {},
            createSocket: url => {
                if (sockets.length === 1 && fail) { fail = false; throw new Error('ENOTFOUND'); }
                const s = new FakeSocket(url);
                sockets.push(s);
                return s;
            }
        });
        await client.start();
        sockets[0]!.emit('close');
        assert.doesNotThrow(() => mock.timers.tick(1000));   // primer intento: createSocket lanza
        assert.equal(sockets.length, 1);
        mock.timers.tick(2000);                               // segundo intento, con espera duplicada
        assert.equal(sockets.length, 2);
        client.close();
    } finally {
        mock.timers.reset();
    }
});

test('positionFromLedger: filas antiguas sin datos de ejecución', () => {
    const p = positionFromLedger({ order_id: 375301, symbol: 'DOGEUSDT', entry_price: 0.08133, take_profit: 0.08, stop_loss: 0.08,
        quantity: 184, net_quantity: null, entry_quote: null, entry_fee_usdt: null });
    assert.equal(p.netQuantity, 184);
    close(p.entryQuote, 0.08133 * 184);
    assert.equal(p.entryFeeQuote, 0);
    assert.equal(p.entryFeeBaseQty, 0);
});
