export interface BrainHandshake {
    market: string;
    notionalUsdt: number;
    klineInterval: string;
}
/** Valida la respuesta de Python a 'market'. Lanza un error con el motivo si no se puede operar. */
export declare function parseBrainHandshake(response: any, expectedMarket: string): BrainHandshake;
//# sourceMappingURL=brain-handshake.d.ts.map