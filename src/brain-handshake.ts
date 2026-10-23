// Handshake de arranque con el cerebro Python ('market'): mismo mercado, tamaño por operación y temporalidad de
// las velas que el backtest. Python es la única fuente del tamaño (optimize.NOTIONAL_USDT) y de la temporalidad
// (config.KLINE_INTERVAL): Node compra exactamente ese importe y se suscribe a esas velas.

export interface BrainHandshake {
    market: string;
    notionalUsdt: number;   // USDT por operación (quoteOrderQty de cada compra)
    klineInterval: string;  // velas del WebSocket (@kline_<intervalo>), las mismas que evalúa la estrategia
}

// Intervalos de velas de Binance spot
const KLINE_INTERVALS = new Set(['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M']);

/** Valida la respuesta de Python a 'market'. Lanza un error con el motivo si no se puede operar. */
export function parseBrainHandshake(response: any, expectedMarket: string): BrainHandshake {
    if (response?.market !== expectedMarket) {
        throw new Error(`Mercado distinto: Node usa "${expectedMarket}" y Python "${response?.market}". Revisa BINANCE_MARKET en .env.`);
    }
    const notional = Number(response?.notional_usdt);
    if (response?.notional_usdt === null || response?.notional_usdt === undefined || !Number.isFinite(notional) || notional <= 0) {
        throw new Error(`Python no informa un tamaño por operación válido (notional_usdt=${response?.notional_usdt}). ` +
            `¿server.py desactualizado?`);
    }
    if (!KLINE_INTERVALS.has(response?.kline_interval)) {
        throw new Error(`Python no informa una temporalidad de velas válida (kline_interval=${response?.kline_interval}). ` +
            `¿server.py desactualizado?`);
    }
    return { market: response.market, notionalUsdt: notional, klineInterval: response.kline_interval };
}
