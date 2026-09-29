import { BinanceRestClient } from './api/rest-client';
import { BinanceWSClient } from './api/ws-client';

async function main() {
    console.log("Starting Binance Bot Initialization...\n");

    // 1. Verify REST Connection and Credentials
    const restClient = new BinanceRestClient();
    try {
        await restClient.getAccountBalance();
        console.log("✅ REST API Authentication successful.");
    } catch (error) {
        console.error("❌ REST API Authentication failed. Check your .env keys.");
        process.exit(1);
    }

    // 2. Start the Sensor (WebSocket)
    // We listen to the BTCUSDT order book best bid/ask
    const symbol = 'btcusdt';
    const streamType = 'bookTicker';
    
    console.log(`\nConnecting to live order book for ${symbol.toUpperCase()}...`);
    const wsClient = new BinanceWSClient(`${symbol}@${streamType}`);

    // Graceful shutdown on Ctrl+C
    process.on('SIGINT', () => {
        console.log("\nShutting down bot...");
        wsClient.close();
        process.exit(0);
    });
}

main();