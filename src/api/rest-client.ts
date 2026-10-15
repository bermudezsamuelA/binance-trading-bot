import axios from 'axios';
import * as crypto from 'crypto';
import { config } from '../config/env';

export class BinanceRestClient {
    private apiKey = config.API_KEY;
    private apiSecret = config.API_SECRET;
    private baseUrl = config.REST_URL;

    private filtersCache = new Map<string, { stepSize: string; tickSize: string; minNotional: number }>();

    /**
     * Lee de /exchangeInfo los filtros LOT_SIZE, PRICE_FILTER y NOTIONAL del par (con caché).
     */
    public async getSymbolFilters(symbol: string) {
        const key = symbol.toUpperCase();
        const cached = this.filtersCache.get(key);
        if (cached) return cached;

        const response = await axios.get(`${this.baseUrl}/v3/exchangeInfo?symbol=${key}`);
        const filters: any[] = response.data.symbols[0].filters;
        const lot = filters.find(f => f.filterType === 'LOT_SIZE');
        const price = filters.find(f => f.filterType === 'PRICE_FILTER');
        const notional = filters.find(f => f.filterType === 'NOTIONAL' || f.filterType === 'MIN_NOTIONAL');

        const result = {
            stepSize: lot.stepSize,
            tickSize: price.tickSize,
            minNotional: parseFloat(notional?.minNotional ?? '0')
        };
        this.filtersCache.set(key, result);
        return result;
    }

    /**
     * Redondea hacia abajo al múltiplo de step ("0.00100000", "1.00000000") y lo
     * devuelve como texto con los decimales justos, sin notación científica.
     */
    private roundToStep(value: number, step: string): string {
        const decimals = step.replace(/0+$/, '').split('.')[1]?.length ?? 0;
        const stepNum = parseFloat(step);
        const rounded = Math.floor(value / stepNum + 1e-9) * stepNum;
        return rounded.toFixed(decimals);
    }

    /**
     * Ajusta cantidad y precio a los filtros del par. Devuelve null si la orden
     * queda por debajo del mínimo nocional o con cantidad cero.
     */
    public async normalizeOrder(symbol: string, quantity: number, price: number) {
        const f = await this.getSymbolFilters(symbol);
        const qty = this.roundToStep(quantity, f.stepSize);
        const px = this.roundToStep(price, f.tickSize);
        if (parseFloat(qty) <= 0 || parseFloat(qty) * parseFloat(px) < f.minNotional) {
            return null;
        }
        return { quantity: qty, price: px };
    }

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
        const normalized = await this.normalizeOrder(symbol, quantity, price);
        if (!normalized) {
            throw new Error(`Orden ${side} ${symbol} por debajo del mínimo (cantidad ${quantity} @ ${price})`);
        }
        const timestamp = Date.now();

        // Parámetros obligatorios según la documentación oficial de Binance Spot
        const params = [
            `symbol=${symbol.toUpperCase()}`,
            `side=${side}`,
            `type=LIMIT`,
            `timeInForce=GTC`, // Good Till Cancelled
            `quantity=${normalized.quantity}`,
            `price=${normalized.price}`,
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