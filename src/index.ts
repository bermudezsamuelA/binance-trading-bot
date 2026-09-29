import { BinanceRestClient } from './api/rest-client';
import { BinanceWSClient } from './api/ws-client';
import { brain } from './api/zmq-client'; 

async function main() {
    console.log("Starting Binance Bot Initialization...\n");

    const restClient = new BinanceRestClient();
    try {
        const accountInfo = await restClient.getAccountBalance();
        const usdtBalance = accountInfo.balances.find((b: any) => b.asset === 'USDT');
        
        console.log("✅ REST API Authentication successful.");
        console.log(`💵 Available Balance: ${parseFloat(usdtBalance?.free || '0').toFixed(2)} USDT`);
        console.log(`🔒 Locked in Orders: ${parseFloat(usdtBalance?.locked || '0').toFixed(2)} USDT`);
        
        if (parseFloat(usdtBalance?.free) < 20) {
            console.log("\n⚠️ WARNING: Your free USDT is very low. Please cancel open orders on the Testnet UI to free up margin.");
        }
    } catch (error) {
        console.error("❌ REST API Authentication failed. Check your .env keys.");
        process.exit(1);
    }

    console.log("\n📡 Fetching active trading roster from Python Brain over ZMQ...");
    let roster: string[] = [];
    try {
        roster = await brain.ask('roster'); 
        console.log(`✅ Roster loaded: ${roster.join(', ')}`);
    } catch (error: any) {
        console.error("❌ Failed to connect to Python Brain via ZMQ. Is the server running?");
        process.exit(1);
    }

    console.log(`\nConnecting to live order book for all rostered coins...`);
    const wsClient = new BinanceWSClient(roster);
    await wsClient.syncStateFromLedger();
    
    process.on('SIGINT', () => {
        console.log("\nShutting down bot...");
        wsClient.close();
        process.exit(0);
    });
}

main();