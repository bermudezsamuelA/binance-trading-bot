// Comisiones pagadas con BNB (descuento del 25 %: 0.075 % por lado). Python decide si se usan (config.PAY_FEES_WITH_BNB,
// en el .env) y con esa comisión calcula el backtest; aquí se vigila que Binance de verdad las cobre en BNB:
//   * saldo de BNB libre valorado en USDT: aviso si baja del mínimo (sin BNB, Binance cobra el 0.10 % normal);
//   * cada compra o venta: aviso si la comisión no salió en BNB (opción desactivada en la cuenta o BNB agotado);
//   * en mainnet, al arrancar, la opción "Usar BNB para pagar comisiones" de la cuenta (GET /sapi/v1/bnbBurn).
import type { Execution } from './execution';

// Con 15 USDT por operación, la comisión de ida y vuelta con BNB es ~0.0225 USDT: 2 USDT alcanzan para ~90 operaciones
export const BNB_MIN_USDT = 2;

/** Activos en los que se cobró la comisión de una orden (solo fills con comisión > 0). */
export function feeAssets(exec: Pick<Execution, 'fills'>): string[] {
    return [...new Set(exec.fills.filter(f => f.commission > 0).map(f => f.commissionAsset))];
}

interface BnbRest {
    getFreeBalances(): Promise<Map<string, number>>;
    getPrice(symbol: string): Promise<number>;
    getBnbBurnStatus?(): Promise<{ spotBNBBurn: boolean }>;
}

export class BnbFeeMonitor {
    private lowBalanceAlerted = false;
    private wrongAssetAlerted = false;

    constructor(private rest: BnbRest, private notify: (message: string) => void,
                private options: { enabled: boolean; market: string; minUsdt?: number }) {}

    get enabled(): boolean {
        return this.options.enabled;
    }

    /** Saldo de BNB libre en USDT (null si no se pudo leer). Avisa una vez al bajar del mínimo y de nuevo tras reponerlo. */
    public async checkBalance(): Promise<number | null> {
        if (!this.enabled) return null;
        let bnbUsdt: number;
        try {
            const free = (await this.rest.getFreeBalances()).get('BNB') ?? 0;
            bnbUsdt = free > 0 ? free * await this.rest.getPrice('BNBUSDT') : 0;
        } catch (error: any) {
            console.warn(`[BNB] No se pudo leer el saldo de BNB: ${error?.message ?? error}`);
            return null;
        }
        const min = this.options.minUsdt ?? BNB_MIN_USDT;
        if (bnbUsdt < min && !this.lowBalanceAlerted) {
            this.lowBalanceAlerted = true;
            console.warn(`[BNB] Saldo de BNB bajo: ${bnbUsdt.toFixed(2)} USDT (mínimo ${min} USDT).`);
            this.notify(`⚠️ <b>BNB BAJO:</b> quedan ${bnbUsdt.toFixed(2)} USDT en BNB (${this.options.market}). ` +
                `Sin BNB, Binance cobra la comisión normal (0.10 % en vez de 0.075 %) y el bot rinde menos que el backtest. ` +
                `Compra unos 5-10 USDT de BNB en la cuenta spot.`);
        } else if (bnbUsdt >= min) {
            this.lowBalanceAlerted = false;
        }
        return bnbUsdt;
    }

    /** En mainnet: avisa si la opción de pagar comisiones con BNB está apagada en la cuenta (la testnet no la tiene). */
    public async checkAccountSetting(): Promise<boolean | null> {
        if (!this.enabled || this.options.market !== 'mainnet' || !this.rest.getBnbBurnStatus) return null;
        try {
            const on = Boolean((await this.rest.getBnbBurnStatus()).spotBNBBurn);
            if (!on) {
                this.notify(`⚠️ <b>BNB DESACTIVADO:</b> la cuenta no paga las comisiones con BNB. Actívalo en Binance ` +
                    `(perfil → "Usar BNB para pagar comisiones"); si no, cada operación cuesta 0.10 % por lado y no 0.075 %.`);
            }
            return on;
        } catch (error: any) {
            console.warn(`[BNB] No se pudo consultar la opción de comisiones con BNB: ${error?.message ?? error}`);
            return null;
        }
    }

    /** Tras cada compra o venta ejecutada: avisa (una vez, hasta que vuelva a cobrar en BNB) y revisa el saldo. */
    public async afterTrade(symbol: string, exec: Pick<Execution, 'fills'>): Promise<void> {
        if (!this.enabled) return;
        const assets = feeAssets(exec);
        const other = assets.filter(a => a !== 'BNB');
        if (other.length && !this.wrongAssetAlerted) {
            this.wrongAssetAlerted = true;
            console.warn(`[BNB] ${symbol}: la comisión se cobró en ${other.join(', ')}, no en BNB.`);
            this.notify(`⚠️ <b>COMISIÓN SIN BNB: ${symbol}</b>\nBinance cobró la comisión en ${other.join(', ')}. ` +
                `Revisa que haya BNB libre y que la opción de pagar comisiones con BNB esté activa` +
                (this.options.market === 'testnet' ? ' (la testnet puede no aplicar el descuento).' : '.'));
        } else if (assets.includes('BNB') && !other.length) {
            this.wrongAssetAlerted = false;
        }
        await this.checkBalance();
    }
}
