import axios from 'axios';
import { config } from '../config/env';

export class TelegramClient {
    private token = config.TELEGRAM_BOT_TOKEN;
    private chatId = config.TELEGRAM_CHAT_ID;
    private baseUrl = `https://api.telegram.org/bot${this.token}`;

    public async sendMessage(message: string) {
        try {
            const url = `${this.baseUrl}/sendMessage`;
            await axios.post(url, {
                chat_id: this.chatId,
                text: message,
                parse_mode: 'HTML' // Permite usar negritas (<b>) y cursivas (<i>) en los mensajes
            });
        } catch (error: any) {
            console.error("⚠️ Error enviando alerta a Telegram:", error.message);
        }
    }
}