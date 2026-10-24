// USDT ocioso en Binance Simple Earn (flexible): el saldo que el bot no necesita para comprar gana el interés del
// producto flexible de USDT, y antes de cada compra se rescata lo que falte (el rescate flexible es inmediato).
// Ganancia mecánica: no depende de ninguna señal. Solo en mainnet (la testnet no tiene /sapi) y solo con
// EARN_IDLE_USDT=1 en el .env (mueve dinero de la cuenta, así que está apagado por defecto).
//
// Reserva: siempre quedan libres en spot EARN_RESERVE_TRADES compras (por defecto 2), para que una compra no espere al
// rescate. Lo que pasa de esa reserva se suscribe al arrancar, tras cada venta y cada hora.

export interface FlexibleProduct {
    productId: string;
    apr: number;              // latestAnnualPercentageRate (fracción: 0.05 = 5 % anual)
    minPurchase: number;
    canPurchase: boolean;
    canRedeem: boolean;
}

export interface EarnRest {
    getFreeBalances(): Promise<Map<string, number>>;
    getFlexibleProduct(asset: string): Promise<FlexibleProduct | null>;
    getFlexiblePosition(asset: string): Promise<number>;
    subscribeFlexible(productId: string, amount: string): Promise<void>;
    redeemFlexible(productId: string, amount: string): Promise<void>;
}

export const EARN_RESERVE_TRADES = 2;
export const EARN_SWEEP_MS = 60 * 60 * 1000;
const MARGIN = 1.02;          // 2 % de margen sobre el importe de la compra (comisión y redondeos)
const REDEEM_WAIT_MS = 10_000;
const REDEEM_POLL_MS = 1_000;

/** Importe en USDT con 2 decimales hacia abajo (Binance acepta hasta 8; 2 evita restos por redondeo). */
export function floorUsdt(x: number): string {
    return (Math.floor(Math.max(0, x) * 100 + 1e-9) / 100).toFixed(2);
}

export class EarnManager {
    private product: FlexibleProduct | null = null;
    private busy = false;
    private timer: ReturnType<typeof setInterval> | null = null;

    constructor(private rest: EarnRest, private notify: (message: string) => void,
                private options: { enabled: boolean; market: string; tradeQuoteUsdt: number; reserveTrades?: number;
                                   sleep?: (ms: number) => Promise<void> }) {}

    get active(): boolean {
        return this.product !== null;
    }

    private get reserve(): number {
        return this.options.tradeQuoteUsdt * (this.options.reserveTrades ?? EARN_RESERVE_TRADES) * MARGIN;
    }

    private sleep(ms: number): Promise<void> {
        return this.options.sleep ? this.options.sleep(ms) : new Promise(resolve => setTimeout(resolve, ms));
    }

    /** Busca el producto flexible de USDT. Devuelve un texto para la consola (o null si queda apagado). */
    public async start(): Promise<string | null> {
        if (!this.options.enabled) return null;
        if (this.options.market !== 'mainnet') {
            return `EARN_IDLE_USDT se ignora en ${this.options.market}: Simple Earn solo existe en mainnet.`;
        }
        try {
            const product = await this.rest.getFlexibleProduct('USDT');
            if (!product || !product.canPurchase || !product.canRedeem) {
                return 'Simple Earn: no hay un producto flexible de USDT disponible para esta cuenta; queda apagado.';
            }
            this.product = product;
        } catch (error: any) {
            return `Simple Earn: no se pudo consultar el producto flexible de USDT (${error?.message ?? error}); queda apagado.`;
        }
        await this.sweep();
        return `Simple Earn activo: USDT ocioso al ${(100 * this.product.apr).toFixed(2)} % anual (tasa variable de ` +
            `Binance); se dejan libres ${this.reserve.toFixed(2)} USDT para comprar.`;
    }

    /** Barrido periódico (cada hora). Se puede parar con stop(). */
    public schedule(intervalMs = EARN_SWEEP_MS) {
        if (!this.active || this.timer) return;
        this.timer = setInterval(() => { this.sweep().catch(() => {}); }, intervalMs);
        this.timer.unref?.();
    }

    public stop() {
        if (this.timer) clearInterval(this.timer);
        this.timer = null;
    }

    /** Suscribe el USDT libre que pasa de la reserva. Devuelve lo suscrito (0 si nada). Nunca lanza. */
    public async sweep(): Promise<number> {
        if (!this.product || this.busy) return 0;
        this.busy = true;
        try {
            const free = (await this.rest.getFreeBalances()).get('USDT') ?? 0;
            const excess = parseFloat(floorUsdt(free - this.reserve));
            if (excess < Math.max(this.product.minPurchase, 1)) return 0;
            await this.rest.subscribeFlexible(this.product.productId, excess.toFixed(2));
            console.log(`[EARN] ${excess.toFixed(2)} USDT a Simple Earn flexible (quedan ${(free - excess).toFixed(2)} libres).`);
            return excess;
        } catch (error: any) {
            console.warn(`[EARN] No se pudo suscribir el USDT ocioso: ${error?.message ?? error}`);
            return 0;
        } finally {
            this.busy = false;
        }
    }

    /**
     * Antes de una compra de `quote` USDT: si el saldo libre no alcanza, rescata lo que falta de Simple Earn y espera
     * (hasta 10 s) a que llegue. Devuelve true si hay saldo para comprar. Nunca lanza: si algo falla, la compra sigue y,
     * si de verdad no hay saldo, Binance la rechaza como siempre.
     */
    public async ensureFunds(quote: number): Promise<boolean> {
        if (!this.product) return true;
        const need = quote * MARGIN;
        try {
            let free = (await this.rest.getFreeBalances()).get('USDT') ?? 0;
            if (free >= need) return true;
            const inEarn = await this.rest.getFlexiblePosition('USDT');
            // Se rescata lo que falta más la reserva, para que la siguiente compra tampoco espere
            const amount = Math.min(inEarn, need - free + this.reserve);
            if (!(amount > 0)) return false;
            await this.rest.redeemFlexible(this.product.productId, (Math.ceil(amount * 100 - 1e-9) / 100).toFixed(2));
            console.log(`[EARN] Rescate de ${amount.toFixed(2)} USDT de Simple Earn para comprar.`);
            for (let waited = 0; waited < REDEEM_WAIT_MS; waited += REDEEM_POLL_MS) {
                await this.sleep(REDEEM_POLL_MS);
                free = (await this.rest.getFreeBalances()).get('USDT') ?? 0;
                if (free >= need) return true;
            }
            console.warn(`[EARN] El rescate no llegó en ${REDEEM_WAIT_MS / 1000} s (libres ${free.toFixed(2)} USDT).`);
            return false;
        } catch (error: any) {
            console.warn(`[EARN] No se pudo rescatar USDT de Simple Earn: ${error?.message ?? error}`);
            this.notify(`⚠️ <b>SIMPLE EARN:</b> no se pudo rescatar USDT antes de comprar (${String(error?.message ?? error)}).`);
            return false;
        }
    }
}
