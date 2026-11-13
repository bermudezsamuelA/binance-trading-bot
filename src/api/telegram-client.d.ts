export declare class TelegramClient {
    private token;
    private chatId;
    private baseUrl;
    sendMessage(message: string): Promise<void>;
}
/** Texto seguro para parse_mode HTML de Telegram (mensajes de error de Binance, motivos de cierre). */
export declare function escapeHtml(text: string): string;
//# sourceMappingURL=telegram-client.d.ts.map