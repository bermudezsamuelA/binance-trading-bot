import * as dotenv from 'dotenv';
dotenv.config();

/**
 * Variable de entorno sin espacios y sin un par de comillas envolventes. dotenv y binance-research/config.py ya las
 * quitan del .env, pero `docker run --env-file .env` pasa el valor literal: BINANCE_MARKET="testnet" llegaría con
 * comillas y el bot no arrancaría (o firmaría con una clave entre comillas).
 */
export function envValue(name: string): string {
    const value = (process.env[name] ?? '').trim();
    const quoted = /^(["'])(.*)\1$/s.exec(value);
    return quoted ? quoted[2]! : value;
}

// Mercado de Binance. Una sola variable (BINANCE_MARKET en .env) decide a la vez las órdenes (REST),
// los precios en vivo (WebSocket) y la precarga de Python (binance-research/config.py lee el mismo .env).
// Así es imposible operar en un mercado con los precios de otro.
const MARKETS = {
    testnet: { REST_URL: 'https://testnet.binance.vision/api', WS_URL: 'wss://stream.testnet.binance.vision' },
    mainnet: { REST_URL: 'https://api.binance.com/api', WS_URL: 'wss://stream.binance.com:9443' },
};
type MarketName = keyof typeof MARKETS;

const marketName = (envValue('BINANCE_MARKET') || 'testnet').toLowerCase();
if (!(marketName in MARKETS)) {
    throw new Error(`🔴 BINANCE_MARKET="${marketName}" no es válido. Usa "testnet" o "mainnet" en el archivo .env`);
}
const market = MARKETS[marketName as MarketName];

export const config = {
    API_KEY: envValue('BINANCE_API_KEY'),
    API_SECRET: envValue('BINANCE_API_SECRET'),
    MARKET: marketName as MarketName,
    REST_URL: market.REST_URL,
    WS_URL: market.WS_URL,
    TELEGRAM_BOT_TOKEN: envValue('TELEGRAM_BOT_TOKEN'),
    TELEGRAM_CHAT_ID: envValue('TELEGRAM_CHAT_ID')
};

// Validación inicial
if (!config.API_KEY || !config.API_SECRET) {
    throw new Error("🔴 Faltan las credenciales de Binance en el archivo .env");
}
if (!config.TELEGRAM_BOT_TOKEN || !config.TELEGRAM_CHAT_ID) {
    throw new Error("🔴 Faltan las credenciales de Telegram en el archivo .env");
}
if (process.env.BINANCE_REST_URL || process.env.BINANCE_WS_URL) {
    console.warn(`⚠️  BINANCE_REST_URL y BINANCE_WS_URL ya no se usan: el mercado lo decide BINANCE_MARKET (${config.MARKET}).`);
}
