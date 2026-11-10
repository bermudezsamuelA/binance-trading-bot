"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const axios_1 = __importDefault(require("axios"));
const env_1 = require("./src/config/env");
const crypto = __importStar(require("crypto"));
async function cancelAllForSymbol(symbol) {
    const timestamp = Date.now();
    const queryString = `symbol=${symbol}&timestamp=${timestamp}`;
    const signature = crypto.createHmac('sha256', env_1.config.API_SECRET).update(queryString).digest('hex');
    const url = `${env_1.config.REST_URL}/v3/openOrders?${queryString}&signature=${signature}`;
    try {
        await axios_1.default.delete(url, { headers: { 'X-MBX-APIKEY': env_1.config.API_KEY } });
        console.log(`✅ All open orders for ${symbol} successfully canceled.`);
    }
    catch (error) {
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
//# sourceMappingURL=rescue.js.map