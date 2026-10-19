import { BinanceRestClient } from './api/rest-client';
import { BinanceWSClient } from './api/ws-client';
import { brain } from './api/zmq-client'; 
import { TelegramClient, escapeHtml } from './api/telegram-client';
import { config } from './config/env';
import { parseBrainHandshake } from './brain-handshake';
import { installProcessGuards } from './process-guards';

const telegram = new TelegramClient();
// Ningún error asíncrono se pierde en silencio: se registra y se avisa, y el bot sigue vigilando sus posiciones
installProcessGuards(message => telegram.sendMessage(message));

async function main() {
    console.log("Starting Binance Bot Initialization...");
    console.log(`🌐 Mercado: ${config.MARKET} (REST ${config.REST_URL} | WS ${config.WS_URL})\n`);

    const restClient = new BinanceRestClient();

    // Desfase con la hora del servidor: evita rechazos -1021 (timestamp fuera de recvWindow)
    try {
        const offset = await restClient.syncServerTime();
        console.log(`🕒 Desfase con la hora de Binance: ${offset} ms`);
    } catch (error: any) {
        console.warn("⚠️ No se pudo leer la hora del servidor de Binance:", error.response?.data || error.message);
    }
    
    try {
        const accountInfo = await restClient.getAccountBalance();
        // omitZeroBalances: sin USDT el activo no aparece y cuenta como 0
        const usdtBalance = accountInfo.balances.find((b: any) => b.asset === 'USDT');
        const usdtFree = parseFloat(usdtBalance?.free || '0');

        console.log("✅ REST API Authentication successful.");
        console.log(`💵 Available Balance: ${usdtFree.toFixed(2)} USDT`);

        if (usdtFree < 20) {
            await telegram.sendMessage(`⚠️ <b>ALERTA DE MARGEN:</b> Tu balance de USDT libre es muy bajo en Binance (${config.MARKET}).`);
        }
    } catch (error: any) {
        console.error("❌ REST API Authentication failed. Check your .env keys.");
        console.error("   Detalle:", error.response?.status, error.response?.data || error.message);
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

    // Handshake: Python precarga velas por REST (tiene que leer el mismo mercado que las órdenes y el WebSocket)
    // y es la única fuente del tamaño por operación (optimize.NOTIONAL_USDT, el que simula el backtest).
    let tradeQuoteUsdt: number;
    try {
        tradeQuoteUsdt = parseBrainHandshake(await brain.ask('market'), config.MARKET).notionalUsdt;
    } catch (error: any) {
        console.error(`❌ ${error.message}`);
        await telegram.sendMessage(`❌ <b>ERROR CRÍTICO:</b> ${escapeHtml(error.message)}`);
        process.exit(1);
    }
    console.log(`💰 Tamaño por operación (backtest): ${tradeQuoteUsdt} USDT`);

    console.log(`\nConnecting to live order book for all rostered coins...`);
    // El cliente WebSocket usa el mismo cliente REST (y el mismo desfase horario); start() recupera las
    // posiciones del ledger antes de conectarse a los precios.
    const wsClient = new BinanceWSClient(roster, tradeQuoteUsdt, { rest: restClient, telegram });
    await wsClient.start();
    
    // Notificación de encendido exitoso
    await telegram.sendMessage(`🟢 <b>BOT INICIADO</b>\nConectado al mercado con ${roster.length} activos.\n<i>Esperando señales del algoritmo...</i>`);
    
    process.on('SIGINT', async () => {
        console.log("\nShutting down bot...");
        await telegram.sendMessage("🔴 <b>BOT APAGADO</b>\nDesconexión manual o caída del servidor.");
        wsClient.close();
        process.exit(0);
    });
}

main().catch(async (error: any) => {
    console.error("❌ Error fatal al arrancar:", error);
    await telegram.sendMessage(`❌ <b>ERROR CRÍTICO:</b> el bot no pudo arrancar (${escapeHtml(String(error?.message ?? error))}).`);
    process.exit(1);
});