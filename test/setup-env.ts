// Se importa primero en cada prueba: credenciales ficticias para src/config/env (que lanza sin ellas).
// Ninguna prueba hace peticiones reales: REST, WebSocket, ZMQ y Telegram se sustituyen por dobles.
process.env.BINANCE_API_KEY = 'test-key';
process.env.BINANCE_API_SECRET = 'test-secret';
process.env.TELEGRAM_BOT_TOKEN = 'test-token';
process.env.TELEGRAM_CHAT_ID = '1';
process.env.BINANCE_MARKET = 'testnet';
process.env.DOTENV_CONFIG_QUIET = 'true';
