import axios from 'axios';
import * as crypto from 'crypto';
import { config } from '../config/env';

export class BinanceRestClient {
    private apiKey = config.API_KEY;
    private apiSecret = config.API_SECRET;
    private baseUrl = config.REST_URL;

    private sign(queryString: string): string {
        return crypto
            .createHmac('sha256', this.apiSecret)
            .update(queryString)
            .digest('hex');
    }

    public async getAccountBalance() {
        const endpoint = '/v3/account';
        const timestamp = Date.now();
        const queryString = `timestamp=${timestamp}`;
        const signature = this.sign(queryString);
        
        const url = `${this.baseUrl}${endpoint}?${queryString}&signature=${signature}`;

        const response = await axios.get(url, {
            headers: { 'X-MBX-APIKEY': this.apiKey }
        });
        return response.data;
    }

    /**
     * Envía una orden límite firmada a la Testnet de Binance.
     */
    public async placeLimitOrder(symbol: string, side: 'BUY' | 'SELL', quantity: number, price: number) {
        const endpoint = '/v3/order';
        const timestamp = Date.now();
        
        // Parámetros obligatorios según la documentación oficial de Binance Spot
        const params = [
            `symbol=${symbol.toUpperCase()}`,
            `side=${side}`,
            `type=LIMIT`,
            `timeInForce=GTC`, // Good Till Cancelled
            `quantity=${quantity}`,
            `price=${price.toFixed(2)}`,
            `timestamp=${timestamp}`
        ].join('&');

        const signature = this.sign(params);
        const url = `${this.baseUrl}${endpoint}?${params}&signature=${signature}`;

        try {
            const response = await axios.post(url, null, {
                headers: { 'X-MBX-APIKEY': this.apiKey }
            });
            return response.data;
        } catch (error: any) {
            console.error(`Error colocando orden ${side}:`, error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Cancela una orden activa en la Testnet de Binance.
     */
    public async cancelOrder(symbol: string, orderId: number) {
        const endpoint = '/v3/order';
        const timestamp = Date.now();
        
        const params = [
            `symbol=${symbol.toUpperCase()}`,
            `orderId=${orderId}`,
            `timestamp=${timestamp}`
        ].join('&');

        const signature = this.sign(params);
        const url = `${this.baseUrl}${endpoint}?${params}&signature=${signature}`;

        try {
            // Binance requires a DELETE HTTP request to cancel orders
            const response = await axios.delete(url, {
                headers: { 'X-MBX-APIKEY': this.apiKey }
            });
            return response.data;
        } catch (error: any) {
            // Error code -2011 means "Unknown order" (it was likely already filled or canceled)
            if (error.response?.data?.code === -2011) {
                console.log(`⚠️ Orden ${orderId} ya no está activa en el libro.`);
            } else {
                console.error(`🔴 Error cancelando orden ${orderId}:`, error.response?.data || error.message);
            }
            throw error;
        }
    }
}