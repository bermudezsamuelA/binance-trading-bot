// Handshake de arranque con el cerebro Python ('market'): mismo mercado y tamaño por operación del backtest.
// Python es la única fuente del tamaño (optimize.NOTIONAL_USDT); Node compra exactamente ese importe.

export interface BrainHandshake {
    market: string;
    notionalUsdt: number;   // USDT por operación (quoteOrderQty de cada compra)
}

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
    return { market: response.market, notionalUsdt: notional };
}
