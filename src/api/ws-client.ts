import WebSocket from 'ws';
import { config } from '../config/env';

export class BinanceWSClient {
    private ws: WebSocket;
    private baseUrl = config.WS_URL;

    constructor(streamName: string) {
        // Construct the URL. Example streamName: 'btcusdt@bookTicker'
        const url = `${this.baseUrl}/${streamName}`;
        this.ws = new WebSocket(url);

        this.initializeEvents();
    }

    private initializeEvents() {
        this.ws.on('open', () => {
            console.log(`🟢 WebSocket connected to stream: ${this.ws.url}`);
        });

        this.ws.on('message', (data: WebSocket.RawData) => {
            const parsedData = JSON.parse(data.toString());
            this.handleMarketData(parsedData);
        });

        this.ws.on('error', (error) => {
            console.error('🔴 WebSocket Error:', error);
        });

        this.ws.on('close', () => {
            console.log('⚫ WebSocket connection closed.');
            // In a production environment, you would implement reconnection logic here
        });
    }

    private handleMarketData(data: any) {
        // Formatting the output so it doesn't flood your console into unreadability
        if (data.u) {
            console.log(`[${data.s}] Bid: ${data.b} (Qty: ${data.B}) | Ask: ${data.a} (Qty: ${data.A})`);
        } else {
            console.log('Raw WS Data:', data);
        }
    }

    public close() {
        this.ws.close();
    }
}