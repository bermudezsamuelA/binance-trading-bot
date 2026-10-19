// Cálculos puros sobre órdenes de Binance Spot: redondeos, mínimos, respuesta FULL, comisiones y PnL neto.
// Sin red ni estado: los usan rest-client y ws-client, y se prueban aparte (test/execution.test.ts).

export interface SymbolFilters {
    baseAsset: string;
    quoteAsset: string;
    stepSize: string;     // múltiplo de cantidad para órdenes MARKET (LOT_SIZE, o MARKET_LOT_SIZE si es más grueso)
    minQty: number;
    maxQty: number;       // 0 = sin máximo
    tickSize: string;
    minNotional: number;  // 0 si NOTIONAL/MIN_NOTIONAL no se aplica a órdenes MARKET
    quoteOrderQtyMarketAllowed: boolean;
}

export interface Fill {
    price: number;
    qty: number;
    commission: number;
    commissionAsset: string;
}

export interface Execution {
    orderId: number;
    clientOrderId: string;
    status: string;
    executedQty: number;
    quoteQty: number;     // cummulativeQuoteQty: lo pagado (BUY) o recibido (SELL), sin comisiones
    avgPrice: number;     // quoteQty / executedQty
    fills: Fill[];
    fees: FeeSummary;
}

export interface FeeSummary {
    baseQty: number;      // comisión cobrada en la moneda base (en una compra, reduce lo recibido)
    totalQuote: number;   // todas las comisiones valoradas en la moneda cotizada (USDT)
    detail: string;       // texto con cada activo, p. ej. "0.184 DOGE + 0.00002 BNB"
    unpriced: string[];   // activos que no se pudieron valorar (cuentan 0 en totalQuote)
}

/** Decimales de un paso de Binance ("0.00100000" -> 3, "1.00000000" -> 0). */
export function decimalsOf(step: string): number {
    return step.replace(/0+$/, '').split('.')[1]?.length ?? 0;
}

/**
 * Redondea hacia abajo al múltiplo de step y lo devuelve como texto con los decimales justos,
 * sin notación científica. El 1e-9 absorbe errores de coma flotante (los saldos tienen 8 decimales).
 */
export function floorToStep(value: number, step: string): string {
    const decimals = decimalsOf(step);
    const stepNum = parseFloat(step);
    if (!(value > 0) || !(stepNum > 0)) return (0).toFixed(decimals);
    const rounded = Math.floor(value / stepNum + 1e-9) * stepNum;
    return rounded.toFixed(decimals);
}

/** Precio con los decimales del tickSize del par (DOGE 0.08133, no 0.08). */
export function formatPrice(price: number, tickSize?: string): string {
    if (!Number.isFinite(price)) return String(price);
    if (tickSize && parseFloat(tickSize) > 0) return price.toFixed(decimalsOf(tickSize));
    return String(Number(price.toPrecision(8)));
}

/**
 * Cantidad tal cual (hasta 8 decimales, sin ceros sobrantes): 183.816, no 184. Nunca en notación
 * científica: String(0.00000016) da "1.6e-7" (una comisión en BTC), aquí "0.00000016".
 */
export function formatQty(qty: number): string {
    if (!Number.isFinite(qty)) return String(qty);
    const text = qty.toFixed(8).replace(/\.?0+$/, '');
    return text === '-0' ? '0' : text;
}

/** USDT con signo y 4 decimales: con 15 USDT por operación, 2 decimales esconden las comisiones. */
export function formatUsdt(value: number): string {
    const sign = value >= 0 ? '+' : '-';
    return `${sign}${Math.abs(value).toFixed(4)} USDT`;
}

/**
 * ¿Se puede enviar una orden MARKET con esta cantidad? Comprueba minQty/maxQty y el mínimo nocional.
 * Binance valora las MARKET con el precio medio de los últimos avgPriceMins minutos, no con el último:
 * notionalMargin exige ese margen extra sobre minNotional (0.01 = 1 %).
 */
export function isTradable(qty: number, price: number, f: SymbolFilters, notionalMargin = 0): boolean {
    if (!(qty > 0)) return false;
    if (qty < f.minQty) return false;
    if (f.maxQty > 0 && qty > f.maxQty) return false;
    if (f.minNotional > 0 && qty * price < f.minNotional * (1 + notionalMargin)) return false;
    return true;
}

/**
 * Cantidad vendible de una posición: lo comprado menos la comisión cobrada en la moneda base,
 * limitado al saldo libre si se conoce, y redondeado hacia abajo al stepSize.
 */
export function sellableQuantity(netQuantity: number, f: SymbolFilters, freeBalance?: number): string {
    const available = freeBalance === undefined ? netQuantity : Math.min(netQuantity, freeBalance);
    return floorToStep(available, f.stepSize);
}

/**
 * Comisiones de los fills valoradas en la moneda cotizada: en USDT tal cual, en la moneda base al precio
 * medio de la orden y en otro activo (BNB) con el precio que se pase en assetPrices (activo -> USDT).
 */
export function summarizeFees(fills: Fill[], baseAsset: string, quoteAsset: string, avgPrice: number,
                              assetPrices: Record<string, number> = {}): FeeSummary {
    const byAsset = new Map<string, number>();
    for (const fill of fills) {
        if (!(fill.commission > 0)) continue;
        byAsset.set(fill.commissionAsset, (byAsset.get(fill.commissionAsset) ?? 0) + fill.commission);
    }
    let baseQty = 0;
    let totalQuote = 0;
    const unpriced: string[] = [];
    for (const [asset, amount] of byAsset) {
        if (asset === quoteAsset) {
            totalQuote += amount;
        } else if (asset === baseAsset) {
            baseQty += amount;
            totalQuote += amount * avgPrice;
        } else if (assetPrices[asset] !== undefined && Number.isFinite(assetPrices[asset])) {
            totalQuote += amount * assetPrices[asset]!;
        } else {
            unpriced.push(asset);
        }
    }
    const detail = [...byAsset].map(([asset, amount]) => `${formatQty(amount)} ${asset}`).join(' + ');
    return { baseQty, totalQuote, detail, unpriced };
}

/** Activos de comisión que no son ni la base ni la cotizada (p. ej. BNB) y hay que valorar aparte. */
export function foreignFeeAssets(resp: any, baseAsset: string, quoteAsset: string): string[] {
    const assets = new Set<string>();
    for (const fill of resp?.fills ?? []) {
        const asset = String(fill.commissionAsset ?? '');
        if (asset && asset !== baseAsset && asset !== quoteAsset && parseFloat(fill.commission) > 0) assets.add(asset);
    }
    return [...assets];
}

/**
 * Interpreta la respuesta FULL de POST /api/v3/order (o una reconstruida con /myTrades).
 * Precio medio real = cummulativeQuoteQty / executedQty.
 */
export function parseExecution(resp: any, baseAsset: string, quoteAsset: string,
                               assetPrices: Record<string, number> = {}): Execution {
    const fills: Fill[] = (resp.fills ?? []).map((f: any) => ({
        price: parseFloat(f.price),
        qty: parseFloat(f.qty),
        commission: parseFloat(f.commission ?? '0'),
        commissionAsset: String(f.commissionAsset ?? '')
    }));
    const executedQty = parseFloat(resp.executedQty ?? '0') || 0;
    let quoteQty = parseFloat(resp.cummulativeQuoteQty ?? '0');
    if (!(quoteQty >= 0)) {
        // cummulativeQuoteQty < 0 = dato no disponible: se reconstruye con los fills
        quoteQty = fills.reduce((sum, f) => sum + f.price * f.qty, 0);
    }
    const avgPrice = executedQty > 0 ? quoteQty / executedQty : 0;
    return {
        orderId: Number(resp.orderId),
        clientOrderId: String(resp.clientOrderId ?? ''),
        status: String(resp.status ?? ''),
        executedQty,
        quoteQty,
        avgPrice,
        fills,
        fees: summarizeFees(fills, baseAsset, quoteAsset, avgPrice, assetPrices)
    };
}

/**
 * Operaciones de GET /api/v3/myTrades -> respuesta con la forma FULL (para parseExecution).
 * Sirve para reconstruir una orden cuyo resultado no llegó o una venta hecha sin que el ledger se enterara.
 */
export function tradesToResponse(trades: any[], order: any = {}): any {
    const executedQty = trades.reduce((sum, t) => sum + parseFloat(t.qty), 0);
    const quoteQty = trades.reduce((sum, t) =>
        sum + (t.quoteQty !== undefined ? parseFloat(t.quoteQty) : parseFloat(t.price) * parseFloat(t.qty)), 0);
    return {
        orderId: trades[0]?.orderId,
        clientOrderId: '',
        status: 'FILLED',
        ...order,
        executedQty: String(executedQty),
        cummulativeQuoteQty: String(quoteQty),
        fills: trades.map(t => ({
            price: t.price, qty: t.qty, commission: t.commission, commissionAsset: t.commissionAsset, tradeId: t.id
        }))
    };
}

/** Cantidad ya vendida en los tramos de una salida. */
export function soldQuantity(parts: Execution[] | undefined): number {
    return (parts ?? []).reduce((sum, p) => sum + p.executedQty, 0);
}

/**
 * Suma varias ejecuciones de la misma venta (si la primera MARKET se llenó solo en parte). Las comisiones
 * se suman ya valoradas en cada parte (la de base a su propio precio medio, BNB a su precio).
 */
export function mergeExecutions(parts: Execution[]): Execution {
    const first = parts[0];
    if (!first) throw new Error('mergeExecutions sin ejecuciones');
    if (parts.length === 1) return first;
    const executedQty = parts.reduce((s, p) => s + p.executedQty, 0);
    const quoteQty = parts.reduce((s, p) => s + p.quoteQty, 0);
    return {
        orderId: first.orderId,
        clientOrderId: parts.map(p => p.clientOrderId).join('+'),
        status: parts[parts.length - 1]!.status,
        executedQty,
        quoteQty,
        avgPrice: executedQty > 0 ? quoteQty / executedQty : 0,
        fills: parts.flatMap(p => p.fills),
        fees: {
            baseQty: parts.reduce((s, p) => s + p.fees.baseQty, 0),
            totalQuote: parts.reduce((s, p) => s + p.fees.totalQuote, 0),
            detail: parts.map(p => p.fees.detail).filter(Boolean).join(' + '),
            unpriced: [...new Set(parts.flatMap(p => p.fees.unpriced))]
        }
    };
}

/** Lo que el PnL necesita de la entrada (en memoria o recuperado del ledger). */
export interface EntryCost {
    entryQuote: number;       // USDT pagados (cummulativeQuoteQty de la compra)
    entryFeeQuote: number;    // comisiones de la compra en USDT (todas)
    entryFeeBaseQty: number;  // parte de esa comisión cobrada en la moneda base
    entryPrice: number;       // precio medio de compra (valoración de la comisión en base)
}

/**
 * PnL neto en USDT = USDT recibidos + residuo − USDT pagados − comisiones.
 * La comisión de compra cobrada en la moneda base ya está descontada (se vende menos cantidad),
 * así que no se resta otra vez; el resto de comisiones (USDT, BNB, las de la venta) sí.
 *
 * residualQty: cantidad de la posición que sigue en cartera sin poder venderse (por debajo del stepSize o del
 * mínimo). Con la comisión cobrada en la moneda base, lo neto nunca es múltiplo del paso y siempre queda casi un
 * paso entero: en BTC (paso 0.00001 ≈ 0.9 USDT) es ~6 % de una posición de 15 USDT. Sigue siendo del usuario, así
 * que se valora al precio medio de la venta en vez de contarlo como pérdida.
 */
export function netPnl(entry: EntryCost, exit: { quoteQty: number; fees: FeeSummary; avgPrice?: number },
                       residualQty = 0): number {
    const entryFeeNotEmbedded = entry.entryFeeQuote - entry.entryFeeBaseQty * entry.entryPrice;
    const residualValue = residualQty > 0 ? residualQty * (exit.avgPrice ?? 0) : 0;
    return exit.quoteQty + residualValue - entry.entryQuote - entryFeeNotEmbedded - exit.fees.totalQuote;
}
