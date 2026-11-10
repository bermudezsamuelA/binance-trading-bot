import './setup-env';
import { BinanceWSClient, SocketLike } from '../src/api/ws-client';
import { Execution, SymbolFilters } from '../src/api/execution';
export declare const DOGE: SymbolFilters;
export declare const BTC: SymbolFilters;
export declare const T0: number;
export declare const CANDLE = 900000;
export declare function deferred<T = void>(): {
    promise: Promise<T>;
    resolve: (value: T) => void;
    reject: (error: any) => void;
};
export declare const flush: (times?: number) => Promise<void>;
/** Error con la forma de axios y el cuerpo {code, msg} de Binance. */
export declare function binanceHttpError(code: number, msg: string, status?: number): any;
/** Respuesta FULL de POST /api/v3/order con un fill. */
export declare function fullResponse(o: {
    symbol: string;
    orderId: number;
    side: 'BUY' | 'SELL';
    qty: number;
    price: number;
    fee: number;
    feeAsset: string;
    status?: string;
    clientOrderId?: string;
}): {
    symbol: string;
    orderId: number;
    orderListId: number;
    clientOrderId: string;
    transactTime: number;
    price: string;
    origQty: string;
    executedQty: string;
    origQuoteOrderQty: string;
    cummulativeQuoteQty: string;
    status: string;
    timeInForce: string;
    type: string;
    side: "BUY" | "SELL";
    workingTime: number;
    selfTradePreventionMode: string;
    fills: {
        price: string;
        qty: string;
        commission: string;
        commissionAsset: string;
        tradeId: number;
    }[];
};
export declare class FakeSocket implements SocketLike {
    url: string;
    handlers: Map<string, (...args: any[]) => any>;
    closed: boolean;
    terminated: boolean;
    asksAtCreation: number;
    constructor(url: string);
    on(event: string, listener: (...args: any[]) => any): this;
    close(): void;
    terminate(): void;
    emit(event: string, ...args: any[]): any;
}
export declare class FakeBrain {
    asks: {
        type: string;
        payload: any;
    }[];
    signals: any[];
    openTrades: any[];
    pendingTrades: any[];
    ledgerOpenResult: any;
    ledgerCloseResult: any;
    ledgerPendingResult: any;
    ledgerCancelResult: any;
    ask(type: string, payload?: any): Promise<any>;
    of(type: string): {
        type: string;
        payload: any;
    }[];
}
export declare class FakeTelegram {
    messages: string[];
    sendMessage(message: string): Promise<void>;
}
type SellHook = (symbol: string, qty: string, n: number) => Promise<Execution | void> | Execution | void;
export declare class FakeRest {
    filters: Record<string, SymbolFilters>;
    buys: {
        symbol: string;
        quote: number;
        ref: number;
        clientOrderId?: string;
    }[];
    invalidations: string[];
    sells: {
        symbol: string;
        qty: string;
    }[];
    lookups: {
        symbol: string;
        clientOrderId: string;
    }[];
    fillPrice: Record<string, number>;
    buyFeeAsset: 'base' | 'quote' | 'BNB';
    feeRate: number;
    bnbPrice: number;
    buyHook: ((symbol: string, clientOrderId?: string) => Promise<Execution | void> | Execution | void) | null;
    sellHook: SellHook | null;
    lookupQueue: (Execution | null | Error)[];
    lookupResult: Execution | null;
    avgPrice: Record<string, number>;
    avgPriceCalls: number;
    orders: Record<number, any>;
    trades: any[];
    balances: Map<string, number>;
    balanceError: any;
    private nextId;
    getSymbolFilters(symbol: string): Promise<SymbolFilters>;
    invalidateSymbolFilters(symbol: string): void;
    marketBuy(symbol: string, quoteAmount: number, refPrice: number, clientOrderId?: string): Promise<Execution>;
    marketSell(symbol: string, quantity: string): Promise<Execution>;
    sellExecution(symbol: string, qty: number, status?: string): Execution;
    getFreeBalances(): Promise<Map<string, number>>;
    getPrice(symbol: string): Promise<number>;
    getAvgPrice(symbol: string): Promise<number>;
    lookupOrder(symbol: string, clientOrderId: string): Promise<Execution | null>;
    getOrder(_symbol: string, orderId: number): Promise<any | null>;
    getMyTrades(_symbol: string, params: {
        orderId?: number;
        fromId?: number;
    }): Promise<any[]>;
    tradesToExecution(symbol: string, trades: any[], order?: any): Promise<Execution>;
    /** Ejecución de compra como la daría Binance (para adoptar una compra sin confirmar). */
    buyExecution(symbol: string, qty: number, price: number): Execution;
}
/** Operación de /myTrades. */
export declare function trade(o: {
    id: number;
    orderId: number;
    isBuyer: boolean;
    qty: number;
    price: number;
    fee?: number;
    feeAsset?: string;
}): {
    symbol: string;
    id: number;
    orderId: number;
    orderListId: number;
    price: string;
    qty: string;
    quoteQty: string;
    commission: string;
    commissionAsset: string;
    time: number;
    isBuyer: boolean;
    isMaker: boolean;
    isBestMatch: boolean;
};
export declare function klineMessage(symbol: string, openTime: number, close: number, closed: boolean): Buffer<ArrayBuffer>;
/** Cliente con dobles; send() emite una vela en el último socket y devuelve la promesa del handler. */
export declare function makeClient(roster?: string[], setup?: (h: {
    rest: FakeRest;
    brain: FakeBrain;
}) => void): Promise<{
    client: BinanceWSClient;
    rest: FakeRest;
    brain: FakeBrain;
    telegram: FakeTelegram;
    sockets: FakeSocket[];
    send: (symbol: string, openTime: number, close: number, closed: boolean) => Promise<void>;
}>;
export declare const BUY: (entry: number, tp: number, sl: number) => {
    action: string;
    entry_price: number;
    take_profit: number;
    stop_loss: number;
};
export {};
//# sourceMappingURL=helpers.d.ts.map