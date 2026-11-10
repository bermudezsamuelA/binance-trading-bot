/**
 * Variable de entorno sin espacios y sin un par de comillas envolventes. dotenv y binance-research/config.py ya las
 * quitan del .env, pero `docker run --env-file .env` pasa el valor literal: BINANCE_MARKET="testnet" llegaría con
 * comillas y el bot no arrancaría (o firmaría con una clave entre comillas).
 */
export declare function envValue(name: string): string;
declare const MARKETS: {
    testnet: {
        REST_URL: string;
        WS_URL: string;
    };
    mainnet: {
        REST_URL: string;
        WS_URL: string;
    };
};
type MarketName = keyof typeof MARKETS;
export declare const config: {
    API_KEY: string;
    API_SECRET: string;
    MARKET: MarketName;
    REST_URL: string;
    WS_URL: string;
    TELEGRAM_BOT_TOKEN: string;
    TELEGRAM_CHAT_ID: string;
};
export {};
//# sourceMappingURL=env.d.ts.map