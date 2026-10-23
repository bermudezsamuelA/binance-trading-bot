// Handshake con Python (mercado y tamaño por operación) y manejadores de errores no capturados.
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'events';
import { parseBrainHandshake } from '../src/brain-handshake';
import { GUARD_ALERT_INTERVAL_MS, installProcessGuards } from '../src/process-guards';

test('handshake: mismo mercado, nocional (optimize.NOTIONAL_USDT) y velas (config.KLINE_INTERVAL) de Python', () => {
    assert.deepEqual(parseBrainHandshake({ market: 'testnet', notional_usdt: 15, kline_interval: '1h' }, 'testnet'),
        { market: 'testnet', notionalUsdt: 15, klineInterval: '1h' });
    assert.equal(parseBrainHandshake({ market: 'mainnet', notional_usdt: 25.5, kline_interval: '15m' }, 'mainnet').notionalUsdt, 25.5);
});

test('handshake: mercado distinto, nocional o velas ausentes/no válidos -> error (Node aborta)', () => {
    assert.throws(() => parseBrainHandshake({ market: 'mainnet', notional_usdt: 15, kline_interval: '1h' }, 'testnet'), /Mercado distinto/);
    assert.throws(() => parseBrainHandshake({ market: 'testnet' }, 'testnet'), /tamaño por operación/);   // server.py antiguo
    assert.throws(() => parseBrainHandshake({ market: 'testnet', notional_usdt: null }, 'testnet'), /tamaño por operación/);
    assert.throws(() => parseBrainHandshake({ market: 'testnet', notional_usdt: 0 }, 'testnet'), /tamaño por operación/);
    assert.throws(() => parseBrainHandshake({ market: 'testnet', notional_usdt: 'abc' }, 'testnet'), /tamaño por operación/);
    assert.throws(() => parseBrainHandshake({ market: 'testnet', notional_usdt: 15 }, 'testnet'), /temporalidad/);   // sin velas
    assert.throws(() => parseBrainHandshake({ market: 'testnet', notional_usdt: 15, kline_interval: '17m' }, 'testnet'), /temporalidad/);
    assert.throws(() => parseBrainHandshake({ error: 'Tipo de solicitud desconocida' }, 'testnet'), /Mercado distinto/);
    assert.throws(() => parseBrainHandshake(undefined, 'testnet'), /Mercado distinto/);
});

test('process guards: registran y avisan sin relanzar; un aviso por minuto; se pueden quitar', () => {
    const target = new EventEmitter();
    const logs: any[][] = [];
    const alerts: string[] = [];
    let now = 1000;
    const uninstall = installProcessGuards(msg => { alerts.push(msg); return Promise.reject(new Error('telegram caído')); },
        { target, log: (...args) => logs.push(args), now: () => now });

    assert.doesNotThrow(() => target.emit('unhandledRejection', new Error('<fallo> asíncrono'), Promise.resolve()));
    assert.equal(logs.length, 1);
    assert.equal(alerts.length, 1);
    assert.match(alerts[0]!, /unhandledRejection/);
    assert.match(alerts[0]!, /&lt;fallo&gt; asíncrono/);       // escapado para el HTML de Telegram

    now += 1000;
    target.emit('uncaughtException', new Error('síncrono'));
    assert.equal(logs.length, 2);                              // siempre se registra
    assert.equal(alerts.length, 1);                            // pero no se inunda Telegram

    now += GUARD_ALERT_INTERVAL_MS;
    target.emit('uncaughtException', 'texto');
    assert.equal(alerts.length, 2);

    uninstall();
    assert.equal(target.listenerCount('unhandledRejection'), 0);
    assert.equal(target.listenerCount('uncaughtException'), 0);
});

test('process guards: un notify que lanza no provoca otro error', () => {
    const target = new EventEmitter();
    installProcessGuards(() => { throw new Error('sin red'); }, { target, log: () => {} });
    assert.doesNotThrow(() => target.emit('unhandledRejection', 'x'));
});
