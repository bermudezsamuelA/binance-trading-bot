"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
// Handshake con Python (mercado y tamaño por operación) y manejadores de errores no capturados.
require("./setup-env");
const node_test_1 = require("node:test");
const strict_1 = __importDefault(require("node:assert/strict"));
const events_1 = require("events");
const brain_handshake_1 = require("../src/brain-handshake");
const process_guards_1 = require("../src/process-guards");
(0, node_test_1.test)('handshake: mismo mercado, nocional (optimize.NOTIONAL_USDT) y velas (config.KLINE_INTERVAL) de Python', () => {
    strict_1.default.deepEqual((0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: 15, kline_interval: '1h' }, 'testnet'), { market: 'testnet', notionalUsdt: 15, klineInterval: '1h' });
    strict_1.default.equal((0, brain_handshake_1.parseBrainHandshake)({ market: 'mainnet', notional_usdt: 25.5, kline_interval: '15m' }, 'mainnet').notionalUsdt, 25.5);
});
(0, node_test_1.test)('handshake: mercado distinto, nocional o velas ausentes/no válidos -> error (Node aborta)', () => {
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'mainnet', notional_usdt: 15, kline_interval: '1h' }, 'testnet'), /Mercado distinto/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet' }, 'testnet'), /tamaño por operación/); // server.py antiguo
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: null }, 'testnet'), /tamaño por operación/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: 0 }, 'testnet'), /tamaño por operación/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: 'abc' }, 'testnet'), /tamaño por operación/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: 15 }, 'testnet'), /temporalidad/); // sin velas
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ market: 'testnet', notional_usdt: 15, kline_interval: '17m' }, 'testnet'), /temporalidad/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)({ error: 'Tipo de solicitud desconocida' }, 'testnet'), /Mercado distinto/);
    strict_1.default.throws(() => (0, brain_handshake_1.parseBrainHandshake)(undefined, 'testnet'), /Mercado distinto/);
});
(0, node_test_1.test)('process guards: registran y avisan sin relanzar; un aviso por minuto; se pueden quitar', () => {
    const target = new events_1.EventEmitter();
    const logs = [];
    const alerts = [];
    let now = 1000;
    const uninstall = (0, process_guards_1.installProcessGuards)(msg => { alerts.push(msg); return Promise.reject(new Error('telegram caído')); }, { target, log: (...args) => logs.push(args), now: () => now });
    strict_1.default.doesNotThrow(() => target.emit('unhandledRejection', new Error('<fallo> asíncrono'), Promise.resolve()));
    strict_1.default.equal(logs.length, 1);
    strict_1.default.equal(alerts.length, 1);
    strict_1.default.match(alerts[0], /unhandledRejection/);
    strict_1.default.match(alerts[0], /&lt;fallo&gt; asíncrono/); // escapado para el HTML de Telegram
    now += 1000;
    target.emit('uncaughtException', new Error('síncrono'));
    strict_1.default.equal(logs.length, 2); // siempre se registra
    strict_1.default.equal(alerts.length, 1); // pero no se inunda Telegram
    now += process_guards_1.GUARD_ALERT_INTERVAL_MS;
    target.emit('uncaughtException', 'texto');
    strict_1.default.equal(alerts.length, 2);
    uninstall();
    strict_1.default.equal(target.listenerCount('unhandledRejection'), 0);
    strict_1.default.equal(target.listenerCount('uncaughtException'), 0);
});
(0, node_test_1.test)('process guards: un notify que lanza no provoca otro error', () => {
    const target = new events_1.EventEmitter();
    (0, process_guards_1.installProcessGuards)(() => { throw new Error('sin red'); }, { target, log: () => { } });
    strict_1.default.doesNotThrow(() => target.emit('unhandledRejection', 'x'));
});
//# sourceMappingURL=process.test.js.map