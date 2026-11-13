"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const rest_client_1 = require("./api/rest-client");
const ws_client_1 = require("./api/ws-client");
const zmq_client_1 = require("./api/zmq-client");
const telegram_client_1 = require("./api/telegram-client");
const env_1 = require("./config/env");
const brain_handshake_1 = require("./brain-handshake");
const process_guards_1 = require("./process-guards");
const telegram = new telegram_client_1.TelegramClient();
// Ningún error asíncrono se pierde en silencio: se registra y se avisa, y el bot sigue vigilando sus posiciones
(0, process_guards_1.installProcessGuards)(message => telegram.sendMessage(message));
async function main() {
    console.log("Starting Binance Bot Initialization...");
    console.log(`🌐 Mercado: ${env_1.config.MARKET} (REST ${env_1.config.REST_URL} | WS ${env_1.config.WS_URL})\n`);
    const restClient = new rest_client_1.BinanceRestClient();
    // Desfase con la hora del servidor: evita rechazos -1021 (timestamp fuera de recvWindow)
    try {
        const offset = await restClient.syncServerTime();
        console.log(`🕒 Desfase con la hora de Binance: ${offset} ms`);
    }
    catch (error) {
        console.warn("⚠️ No se pudo leer la hora del servidor de Binance:", error.response?.data || error.message);
    }
    try {
        const accountInfo = await restClient.getAccountBalance();
        // omitZeroBalances: sin USDT el activo no aparece y cuenta como 0
        const usdtBalance = accountInfo.balances.find((b) => b.asset === 'USDT');
        const usdtFree = parseFloat(usdtBalance?.free || '0');
        console.log("✅ REST API Authentication successful.");
        console.log(`💵 Available Balance: ${usdtFree.toFixed(2)} USDT`);
        if (usdtFree < 20) {
            await telegram.sendMessage(`⚠️ <b>ALERTA DE MARGEN:</b> Tu balance de USDT libre es muy bajo en Binance (${env_1.config.MARKET}).`);
        }
    }
    catch (error) {
        console.error("❌ REST API Authentication failed. Check your .env keys.");
        console.error("   Detalle:", error.response?.status, error.response?.data || error.message);
        await telegram.sendMessage("❌ <b>ERROR CRÍTICO:</b> Autenticación REST fallida. Verifica las API Keys.");
        process.exit(1);
    }
    console.log("\n📡 Fetching active trading roster from Python Brain over ZMQ...");
    let roster = [];
    try {
        roster = await zmq_client_1.brain.ask('roster');
        console.log(`✅ Roster loaded: ${roster.join(', ')}`);
    }
    catch (error) {
        console.error("❌ Failed to connect to Python Brain via ZMQ.");
        await telegram.sendMessage("❌ <b>ERROR CRÍTICO:</b> No se pudo conectar con el cerebro Python vía ZMQ.");
        process.exit(1);
    }
    // Handshake: Python precarga velas por REST (tiene que leer el mismo mercado que las órdenes y el WebSocket)
    // y es la única fuente del tamaño por operación (optimize.NOTIONAL_USDT, el que simula el backtest) y de la
    // temporalidad de las velas (config.KLINE_INTERVAL).
    let tradeQuoteUsdt;
    let klineInterval;
    try {
        ({ notionalUsdt: tradeQuoteUsdt, klineInterval } = (0, brain_handshake_1.parseBrainHandshake)(await zmq_client_1.brain.ask('market'), env_1.config.MARKET));
    }
    catch (error) {
        console.error(`❌ ${error.message}`);
        await telegram.sendMessage(`❌ <b>ERROR CRÍTICO:</b> ${(0, telegram_client_1.escapeHtml)(error.message)}`);
        process.exit(1);
    }
    console.log(`💰 Tamaño por operación (backtest): ${tradeQuoteUsdt} USDT | Velas: ${klineInterval}`);
    console.log(`\nConnecting to live order book for all rostered coins...`);
    // El cliente WebSocket usa el mismo cliente REST (y el mismo desfase horario); start() recupera las
    // posiciones del ledger antes de conectarse a los precios.
    const wsClient = new ws_client_1.BinanceWSClient(roster, tradeQuoteUsdt, { rest: restClient, telegram, klineInterval });
    await wsClient.start();
    // Notificación de encendido exitoso
    await telegram.sendMessage(`🟢 <b>BOT INICIADO</b>\nConectado al mercado con ${roster.length} activos (velas de ${klineInterval}).\n<i>Esperando señales del algoritmo...</i>`);
    process.on('SIGINT', async () => {
        console.log("\nShutting down bot...");
        await telegram.sendMessage("🔴 <b>BOT APAGADO</b>\nDesconexión manual o caída del servidor.");
        wsClient.close();
        process.exit(0);
    });
}
main().catch(async (error) => {
    console.error("❌ Error fatal al arrancar:", error);
    await telegram.sendMessage(`❌ <b>ERROR CRÍTICO:</b> el bot no pudo arrancar (${(0, telegram_client_1.escapeHtml)(String(error?.message ?? error))}).`);
    process.exit(1);
});
//# sourceMappingURL=index.js.map