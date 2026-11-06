// Errores no capturados (unhandledRejection / uncaughtException): se registran y se avisa por Telegram, pero el
// proceso sigue vivo, porque con posiciones abiertas apagarse deja los TP/SL sin vigilar. Nunca en silencio.
import { EventEmitter } from 'events';
import { escapeHtml } from './api/telegram-client';

// Como mucho un aviso de Telegram por minuto (un error en bucle no debe inundar el chat)
export const GUARD_ALERT_INTERVAL_MS = 60000;

export interface GuardOptions {
    target?: EventEmitter;                    // process por defecto (las pruebas usan otro emisor)
    log?: (...args: any[]) => void;
    now?: () => number;
}

/** Instala los manejadores y devuelve la función que los quita. */
export function installProcessGuards(notify: (message: string) => unknown, options: GuardOptions = {}): () => void {
    const target = options.target ?? process;
    const log = options.log ?? console.error;
    const now = options.now ?? Date.now;
    let lastAlertAt = -Infinity;

    const report = (kind: string, error: unknown) => {
        log(`[${kind}] Error no capturado (el bot sigue en marcha):`, error);
        if (now() - lastAlertAt < GUARD_ALERT_INTERVAL_MS) return;
        lastAlertAt = now();
        const text = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
        try {
            Promise.resolve(notify(`⚠️ <b>ERROR NO CAPTURADO (${kind})</b>\n<i>${escapeHtml(text.slice(0, 500))}</i>\n` +
                `El bot sigue en marcha; revisa la consola.`)).catch(() => {});
        } catch {
            // el aviso nunca debe provocar otro error no capturado
        }
    };
    const onRejection = (reason: unknown) => report('unhandledRejection', reason);
    const onException = (error: unknown) => report('uncaughtException', error);
    target.on('unhandledRejection', onRejection);
    target.on('uncaughtException', onException);
    return () => {
        target.off('unhandledRejection', onRejection);
        target.off('uncaughtException', onException);
    };
}
