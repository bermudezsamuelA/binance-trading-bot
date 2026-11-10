import { EventEmitter } from 'events';
export declare const GUARD_ALERT_INTERVAL_MS = 60000;
export interface GuardOptions {
    target?: EventEmitter;
    log?: (...args: any[]) => void;
    now?: () => number;
}
/** Instala los manejadores y devuelve la función que los quita. */
export declare function installProcessGuards(notify: (message: string) => unknown, options?: GuardOptions): () => void;
//# sourceMappingURL=process-guards.d.ts.map