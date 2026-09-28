import * as dotenv from 'dotenv';
dotenv.config();

export const config = {
    API_KEY: process.env.BINANCE_API_KEY || '',
    API_SECRET: process.env.BINANCE_API_SECRET || '',
    REST_URL: process.env.BINANCE_REST_URL || 'https://testnet.binance.vision/api',
    WS_URL: process.env.BINANCE_WS_URL || 'wss://stream.testnet.binance.vision/ws'
};

// Validación inicial
if (!config.API_KEY || !config.API_SECRET) {
    throw new Error("Faltan las credenciales de Binance en el archivo .env");
}