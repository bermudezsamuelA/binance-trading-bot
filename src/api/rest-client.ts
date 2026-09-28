import axios from 'axios';
import * as crypto from 'crypto';
import { config } from '../config/env';

export class BinanceRestClient {
    private apiKey = config.API_KEY;
    private apiSecret = config.API_SECRET;
    private baseUrl = config.REST_URL;

    /**
     * Genera la firma HMAC-SHA256 requerida por los endpoints privados de Binance.
     */
    private sign(queryString: string): string {
        return crypto
            .createHmac('sha256', this.apiSecret)
            .update(queryString)
            .digest('hex');
    }

    /**
     * Consulta el estado de la cuenta y los balances.
     */
    public async getAccountBalance() {
        const endpoint = '/v3/account'; // Nota: La URL base ya incluye '/api' en el archivo .env
        const timestamp = Date.now();
        
        // Todos los parámetros deben ir en el query string antes de firmar
        const queryString = `timestamp=${timestamp}`;
        const signature = this.sign(queryString);
        
        const url = `${this.baseUrl}${endpoint}?${queryString}&signature=${signature}`;

        try {
            const response = await axios.get(url, {
                headers: {
                    'X-MBX-APIKEY': this.apiKey
                }
            });
            return response.data;
        } catch (error: any) {
            console.error("Error al consultar la cuenta de Binance:", error.response?.data || error.message);
            throw error;
        }
    }
}