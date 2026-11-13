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
Object.defineProperty(exports, "__esModule", { value: true });
exports.config = void 0;
exports.envValue = envValue;
const dotenv = __importStar(require("dotenv"));
dotenv.config();
/**
 * Variable de entorno sin espacios y sin un par de comillas envolventes. dotenv y binance-research/config.py ya las
 * quitan del .env, pero `docker run --env-file .env` pasa el valor literal: BINANCE_MARKET="testnet" llegaría con
 * comillas y el bot no arrancaría (o firmaría con una clave entre comillas).
 */
function envValue(name) {
    const value = (process.env[name] ?? '').trim();
    const quoted = /^(["'])(.*)\1$/s.exec(value);
    return quoted ? quoted[2] : value;
}
// Mercado de Binance. Una sola variable (BINANCE_MARKET en .env) decide a la vez las órdenes (REST),
// los precios en vivo (WebSocket) y la precarga de Python (binance-research/config.py lee el mismo .env).
// Así es imposible operar en un mercado con los precios de otro.
const MARKETS = {
    testnet: { REST_URL: 'https://testnet.binance.vision/api', WS_URL: 'wss://stream.testnet.binance.vision' },
    mainnet: { REST_URL: 'https://api.binance.com/api', WS_URL: 'wss://stream.binance.com:9443' },
};
const marketName = (envValue('BINANCE_MARKET') || 'testnet').toLowerCase();
if (!(marketName in MARKETS)) {
    throw new Error(`🔴 BINANCE_MARKET="${marketName}" no es válido. Usa "testnet" o "mainnet" en el archivo .env`);
}
const market = MARKETS[marketName];
exports.config = {
    API_KEY: envValue('BINANCE_API_KEY'),
    API_SECRET: envValue('BINANCE_API_SECRET'),
    MARKET: marketName,
    REST_URL: market.REST_URL,
    WS_URL: market.WS_URL,
    TELEGRAM_BOT_TOKEN: envValue('TELEGRAM_BOT_TOKEN'),
    TELEGRAM_CHAT_ID: envValue('TELEGRAM_CHAT_ID')
};
// Validación inicial
if (!exports.config.API_KEY || !exports.config.API_SECRET) {
    throw new Error("🔴 Faltan las credenciales de Binance en el archivo .env");
}
if (!exports.config.TELEGRAM_BOT_TOKEN || !exports.config.TELEGRAM_CHAT_ID) {
    throw new Error("🔴 Faltan las credenciales de Telegram en el archivo .env");
}
if (process.env.BINANCE_REST_URL || process.env.BINANCE_WS_URL) {
    console.warn(`⚠️  BINANCE_REST_URL y BINANCE_WS_URL ya no se usan: el mercado lo decide BINANCE_MARKET (${exports.config.MARKET}).`);
}
//# sourceMappingURL=env.js.map