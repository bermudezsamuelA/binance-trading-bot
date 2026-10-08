import { BinanceRestClient } from './api/rest-client';
import { BinanceWSClient } from './api/ws-client';
import { brain } from './api/zmq-client'; 
import { TelegramClient } from './api/telegram-client';

async function main() {
    console.log("Starting Binance Bot Initialization...\n");
    
    const telegram = new TelegramClient();
    const restClient = new BinanceRestClient();
    
    try {
        const accountInfo = await restClient.getAccountBalance();
        const usdtBalance = accountInfo.balances.find((b: any) => b.asset === 'USDT');
        
        console.log("✅ REST API Authentication successful.");
        console.log(`💵 Available Balance: ${parseFloat(usdtBalance?.free || '0').toFixed(2)} USDT`);
        
        if (parseFloat(usdtBalance?.free) < 20) {
            await telegram.sendMessage("⚠️ <b>ALERTA DE MARGEN:</b> Tu balance de USDT libre es muy bajo en Binance Testnet.");
        }
    } catch (error) {
        console.error("❌ REST API Authentication failed. Check your .env keys.");
        await telegram.sendMessage("❌ <b>ERROR CRÍTICO:</b> Autenticación REST fallida. Verifica las API Keys.");
        process.exit(1);
    }

    console.log("\n📡 Fetching active trading roster from Python Brain over ZMQ...");
    let roster: string[] = [];
    try {
        roster = await brain.ask('roster'); 
        console.log(`✅ Roster loaded: ${roster.join(', ')}`);
    } catch (error: any) {
        console.error("❌ Failed to connect to Python Brain via ZMQ.");
        await telegram.sendMessage("❌ <b>ERROR CRÍTICO:</b> No se pudo conectar con el cerebro Python vía ZMQ.");
        process.exit(1);
    }

    console.log(`\nConnecting to live order book for all rostered coins...`);
    const wsClient = new BinanceWSClient(roster);
    await wsClient.syncStateFromLedger();
    
    // Notificación de encendido exitoso
    await telegram.sendMessage(`🟢 <b>BOT INICIADO</b>\nConectado al mercado con ${roster.length} activos.\n<i>Esperando señales del algoritmo...</i>`);
    
    process.on('SIGINT', async () => {
        console.log("\nShutting down bot...");
        await telegram.sendMessage("🔴 <b>BOT APAGADO</b>\nDesconexión manual o caída del servidor.");
        wsClient.close();
        process.exit(0);
    });
}

main();