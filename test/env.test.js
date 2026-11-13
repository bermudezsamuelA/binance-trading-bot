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
// src/config/env.ts en un proceso aparte (sin el .env real): valores entre comillas como los deja `docker run
// --env-file`, que, a diferencia de dotenv y de binance-research/config.py, no quita las comillas.
require("./setup-env");
const node_test_1 = require("node:test");
const strict_1 = __importDefault(require("node:assert/strict"));
const child_process_1 = require("child_process");
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const path = __importStar(require("path"));
const ENV_TS = path.join(__dirname, '..', 'src', 'config', 'env.ts');
function loadConfig(env) {
    const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'env-test-')); // sin .env: dotenv no carga nada
    try {
        const code = `const { config } = require(${JSON.stringify(ENV_TS)}); process.stdout.write(JSON.stringify(config));`;
        return (0, child_process_1.spawnSync)(process.execPath, ['--require', require.resolve('tsx/cjs'), '-e', code], {
            cwd, encoding: 'utf8',
            env: { PATH: process.env.PATH ?? '', SystemRoot: process.env.SystemRoot ?? '', DOTENV_CONFIG_QUIET: 'true', ...env }
        });
    }
    finally {
        fs.rmSync(cwd, { recursive: true, force: true });
    }
}
(0, node_test_1.test)('docker run --env-file deja las comillas del .env: env.ts las quita (como dotenv y config.py)', () => {
    const r = loadConfig({
        BINANCE_MARKET: '"testnet"', BINANCE_API_KEY: '"clave"', BINANCE_API_SECRET: "'secreto'",
        TELEGRAM_BOT_TOKEN: '"123:abc"', TELEGRAM_CHAT_ID: '"42"'
    });
    strict_1.default.equal(r.status, 0, r.stderr);
    const config = JSON.parse(r.stdout);
    strict_1.default.equal(config.MARKET, 'testnet');
    strict_1.default.equal(config.REST_URL, 'https://testnet.binance.vision/api');
    strict_1.default.equal(config.API_KEY, 'clave');
    strict_1.default.equal(config.API_SECRET, 'secreto');
    strict_1.default.equal(config.TELEGRAM_BOT_TOKEN, '123:abc');
    strict_1.default.equal(config.TELEGRAM_CHAT_ID, '42');
});
(0, node_test_1.test)('env.ts: sin comillas no cambia nada; un mercado inválido o sin credenciales aborta', () => {
    const ok = loadConfig({ BINANCE_MARKET: 'mainnet', BINANCE_API_KEY: 'a"b', BINANCE_API_SECRET: 's',
        TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    strict_1.default.equal(ok.status, 0, ok.stderr);
    strict_1.default.equal(JSON.parse(ok.stdout).API_KEY, 'a"b'); // solo se quita un par envolvente
    strict_1.default.equal(JSON.parse(ok.stdout).MARKET, 'mainnet');
    const bad = loadConfig({ BINANCE_MARKET: '"prod"', BINANCE_API_KEY: 'k', BINANCE_API_SECRET: 's',
        TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    strict_1.default.notEqual(bad.status, 0);
    strict_1.default.match(bad.stderr, /BINANCE_MARKET="prod" no es válido/);
    const missing = loadConfig({ BINANCE_API_KEY: '""', BINANCE_API_SECRET: 's', TELEGRAM_BOT_TOKEN: 't', TELEGRAM_CHAT_ID: '1' });
    strict_1.default.notEqual(missing.status, 0);
    strict_1.default.match(missing.stderr, /Faltan las credenciales de Binance/);
});
//# sourceMappingURL=env.test.js.map