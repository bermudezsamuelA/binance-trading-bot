// src/config/env.ts en un proceso aparte (sin el .env real): valores entre comillas como los deja `docker run
// --env-file`, que, a diferencia de dotenv y de binance-research/config.py, no quita las comillas.
import './setup-env';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const ENV_TS = path.join(__dirname, '..', 'src', 'config', 'env.ts');

function loadConfig(env: Record<string, string>) {
    const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'env-test-'));   // sin .env: dotenv no carga nada
    try {
        const code = `const { config } = require(${JSON.stringify(ENV_TS)}); process.stdout.write(JSON.stringify(config));`;
        return spawnSync(process.execPath, ['--require', require.resolve('tsx/cjs'), '-e', code], {
            cwd, encoding: 'utf8',
            env: { PATH: process.env.PATH ?? '', SystemRoot: process.env.SystemRoot ?? '', DOTENV_CONFIG_QUIET: 'true', ...env }
        });
    } finally {
        fs.rmSync(cwd, { recursive: true, force: true });
    }
}

test('docker run --env-file deja las comillas del .env: env.ts las quita (como dotenv y config.py)', () => {
    const r = loadConfig({
        BINANCE_MARKET: '"testnet"', BINANCE_API_KEY: '"clave"', BINANCE_API_SECRET: "'secreto'",
        TELEGRAM_BOT_TOKEN: '"123:abc"', TELEGRAM_CHAT_ID: '"42"'
    });
    assert.equal(r.status, 0, r.stderr);
    const config = JSON.parse(r.stdout);
    assert.equal(config.MARKET, 'testnet');
    assert.equal(config.REST_URL, 'https://testnet.binance.vision/api');
    assert.equal(config.API_KEY, 'clave');
    assert.equal(config.API_SECRET, 'secreto');
    assert.equal(config.TELEGRAM_BOT_TOKEN, '123:abc');
    assert.equal(config.TELEGRAM_CHAT_ID, '42');
});

test('env.ts: sin comillas no cambia nada; un mercado inválido o sin credenciales aborta', () => {
    const ok = loadConfig({ BINANCE_MARKET: 'mainnet', BINANCE_API_KEY: 'a"b', BINANCE_API_SECRET: 's',
                            TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    assert.equal(ok.status, 0, ok.stderr);
    assert.equal(JSON.parse(ok.stdout).API_KEY, 'a"b');                 // solo se quita un par envolvente
    assert.equal(JSON.parse(ok.stdout).MARKET, 'mainnet');
    const bad = loadConfig({ BINANCE_MARKET: '"prod"', BINANCE_API_KEY: 'k', BINANCE_API_SECRET: 's',
                             TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    assert.notEqual(bad.status, 0);
    assert.match(bad.stderr, /BINANCE_MARKET="prod" no es válido/);
    const missing = loadConfig({ BINANCE_API_KEY: '""', BINANCE_API_SECRET: 's', TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    assert.notEqual(missing.status, 0);
    assert.match(missing.stderr, /Faltan las credenciales de Binance/);
});
