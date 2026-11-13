"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.GUARD_ALERT_INTERVAL_MS = void 0;
exports.installProcessGuards = installProcessGuards;
const telegram_client_1 = require("./api/telegram-client");
// Como mucho un aviso de Telegram por minuto (un error en bucle no debe inundar el chat)
exports.GUARD_ALERT_INTERVAL_MS = 60000;
/** Instala los manejadores y devuelve la función que los quita. */
function installProcessGuards(notify, options = {}) {
    const target = options.target ?? process;
    const log = options.log ?? console.error;
    const now = options.now ?? Date.now;
    let lastAlertAt = -Infinity;
    const report = (kind, error) => {
        log(`[${kind}] Error no capturado (el bot sigue en marcha):`, error);
        if (now() - lastAlertAt < exports.GUARD_ALERT_INTERVAL_MS)
            return;
        lastAlertAt = now();
        const text = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
        try {
            Promise.resolve(notify(`⚠️ <b>ERROR NO CAPTURADO (${kind})</b>\n<i>${(0, telegram_client_1.escapeHtml)(text.slice(0, 500))}</i>\n` +
                `El bot sigue en marcha; revisa la consola.`)).catch(() => { });
        }
        catch {
            // el aviso nunca debe provocar otro error no capturado
        }
    };
    const onRejection = (reason) => report('unhandledRejection', reason);
    const onException = (error) => report('uncaughtException', error);
    target.on('unhandledRejection', onRejection);
    target.on('uncaughtException', onException);
    return () => {
        target.off('unhandledRejection', onRejection);
        target.off('uncaughtException', onException);
    };
}
//# sourceMappingURL=process-guards.js.map