"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.TelegramClient = void 0;
exports.escapeHtml = escapeHtml;
const axios_1 = __importDefault(require("axios"));
const env_1 = require("../config/env");
class TelegramClient {
    token = env_1.config.TELEGRAM_BOT_TOKEN;
    chatId = env_1.config.TELEGRAM_CHAT_ID;
    baseUrl = `https://api.telegram.org/bot${this.token}`;
    async sendMessage(message) {
        try {
            const url = `${this.baseUrl}/sendMessage`;
            await axios_1.default.post(url, {
                chat_id: this.chatId,
                text: message,
                parse_mode: 'HTML' // Permite usar negritas (<b>) y cursivas (<i>) en los mensajes
            });
        }
        catch (error) {
            console.error("⚠️ Error enviando alerta a Telegram:", error.message);
        }
    }
}
exports.TelegramClient = TelegramClient;
/** Texto seguro para parse_mode HTML de Telegram (mensajes de error de Binance, motivos de cierre). */
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
//# sourceMappingURL=telegram-client.js.map