export interface SymbolFilters {
    baseAsset: string;
    quoteAsset: string;
    stepSize: string;
    minQty: number;
    maxQty: number;
    tickSize: string;
    minNotional: number;
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
    quoteQty: number;
    avgPrice: number;
    fills: Fill[];
    fees: FeeSummary;
}
export interface FeeSummary {
    baseQty: number;
    totalQuote: number;
    detail: string;
    unpriced: string[];
}
/** Decimales de un paso de Binance ("0.00100000" -> 3, "1.00000000" -> 0). */
export declare function decimalsOf(step: string): number;
/**
 * Redondea hacia abajo al múltiplo de step y lo devuelve como texto con los decimales justos,
 * sin notación científica. El 1e-9 absorbe errores de coma flotante (los saldos tienen 8 decimales).
 */
export declare function floorToStep(value: number, step: string): string;
/** Precio con los decimales del tickSize del par (DOGE 0.08133, no 0.08). */
export declare function formatPrice(price: number, tickSize?: string): string;
/**
 * Cantidad tal cual (hasta 8 decimales, sin ceros sobrantes): 183.816, no 184. Nunca en notación
 * científica: String(0.00000016) da "1.6e-7" (una comisión en BTC), aquí "0.00000016".
 */
export declare function formatQty(qty: number): string;
/** USDT con signo y 4 decimales: con 15 USDT por operación, 2 decimales esconden las comisiones. */
export declare function formatUsdt(value: number): string;
/**
 * ¿Se puede enviar una orden MARKET con esta cantidad? Comprueba minQty/maxQty y el mínimo nocional.
 * Binance valora las MARKET con el precio medio de los últimos avgPriceMins minutos, no con el último:
 * notionalMargin exige ese margen extra sobre minNotional (0.01 = 1 %).
 */
export declare function isTradable(qty: number, price: number, f: SymbolFilters, notionalMargin?: number): boolean;
/**
 * Cantidad vendible de una posición: lo comprado menos la comisión cobrada en la moneda base,
 * limitado al saldo libre si se conoce, y redondeado hacia abajo al stepSize.
 */
export declare function sellableQuantity(netQuantity: number, f: SymbolFilters, freeBalance?: number): string;
/**
 * Comisiones de los fills valoradas en la moneda cotizada: en USDT tal cual, en la moneda base al precio
 * medio de la orden y en otro activo (BNB) con el precio que se pase en assetPrices (activo -> USDT).
 */
export declare function summarizeFees(fills: Fill[], baseAsset: string, quoteAsset: string, avgPrice: number, assetPrices?: Record<string, number>): FeeSummary;
/** Activos de comisión que no son ni la base ni la cotizada (p. ej. BNB) y hay que valorar aparte. */
export declare function foreignFeeAssets(resp: any, baseAsset: string, quoteAsset: string): string[];
/**
 * Interpreta la respuesta FULL de POST /api/v3/order (o una reconstruida con /myTrades).
 * Precio medio real = cummulativeQuoteQty / executedQty.
 */
export declare function parseExecution(resp: any, baseAsset: string, quoteAsset: string, assetPrices?: Record<string, number>): Execution;
/**
 * Operaciones de GET /api/v3/myTrades -> respuesta con la forma FULL (para parseExecution).
 * Sirve para reconstruir una orden cuyo resultado no llegó o una venta hecha sin que el ledger se enterara.
 */
export declare function tradesToResponse(trades: any[], order?: any): any;
/** Cantidad ya vendida en los tramos de una salida. */
export declare function soldQuantity(parts: Execution[] | undefined): number;
/**
 * Suma varias ejecuciones de la misma venta (si la primera MARKET se llenó solo en parte). Las comisiones
 * se suman ya valoradas en cada parte (la de base a su propio precio medio, BNB a su precio).
 */
export declare function mergeExecutions(parts: Execution[]): Execution;
/** Lo que el PnL necesita de la entrada (en memoria o recuperado del ledger). */
export interface EntryCost {
    entryQuote: number;
    entryFeeQuote: number;
    entryFeeBaseQty: number;
    entryPrice: number;
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
export declare function netPnl(entry: EntryCost, exit: {
    quoteQty: number;
    fees: FeeSummary;
    avgPrice?: number;
}, residualQty?: number): number;
/**
 * Calcula la cantidad a vender en un cierre parcial (ratio entre 0 y 1 sobre lo que queda por vender)
 * y comprueba que tanto el tramo a vender como el remanente posterior sean operables en Binance (isTradable).
 * Si alguno queda bajo minQty o minNotional, devuelve canSplit = false para evitar dejar polvo bloqueado.
 */
export declare function splitPartialQuantity(remainingNetQty: number, ratio: number, price: number, f: SymbolFilters, notionalMargin?: number): {
    canSplit: boolean;
    sellQty: string;
    sellQtyNum: number;
    remainingAfterNum: number;
};
/**
 * PnL neto realizado en un tramo parcial, asignando proporcionalmente el costo y la comisión de entrada
 * según la fracción que representa `part.executedQty` sobre la cantidad neta total de la posición.
 */
export declare function partialNetPnl(entry: EntryCost, netQuantity: number, part: Execution): number;
//# sourceMappingURL=execution.d.ts.map