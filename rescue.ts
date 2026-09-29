import { BinanceRestClient } from './src/api/rest-client';
import axios from 'axios';
import { config } from './src/config/env';
import * as crypto from 'crypto';

async function cancelAllForSymbol(symbol: string) {
    const timestamp = Date.now();
    const queryString = `symbol=${symbol}&timestamp=${timestamp}`;
    const signature = crypto.createHmac('sha256', config.API_SECRET).update(queryString).digest('hex');
    const url = `${config.REST_URL}/v3/openOrders?${queryString}&signature=${signature}`;

    try {
        await axios.delete(url, { headers: { 'X-MBX-APIKEY': config.API_KEY } });
        console.log(`✅ All open orders for ${symbol} successfully canceled.`);
    } catch (error: any) {
        console.log(`⚠️ No active orders found for ${symbol} or error occurred.`);
    }
}

async function rescueFunds() {
    console.log("🧹 Running Rescue Script to unlock funds...");
    await cancelAllForSymbol('BTCUSDT');
    await cancelAllForSymbol('ETHUSDT');
    console.log("💵 Your Testnet USDT has been refunded. You can delete this script now.");
}

rescueFunds();