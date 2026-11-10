"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.brain = void 0;
const zeromq_1 = require("zeromq");
const env_1 = require("../config/env");
class BrainConnection {
    sock = null;
    isLocked = false;
    queue = [];
    // El socket se crea con la primera pregunta: importar este modulo (p. ej. en las pruebas) no abre conexiones
    socket() {
        if (!this.sock) {
            this.sock = new zeromq_1.Request();
            // BRAIN_ZMQ_URL (opcional, .env): p. ej. tcp://host.docker.internal:5555 desde un contenedor Docker
            this.sock.connect((0, env_1.envValue)('BRAIN_ZMQ_URL') || 'tcp://127.0.0.1:5555');
        }
        return this.sock;
    }
    async acquireLock() {
        if (!this.isLocked) {
            this.isLocked = true;
            return Promise.resolve();
        }
        return new Promise(resolve => this.queue.push(resolve));
    }
    releaseLock() {
        if (this.queue.length > 0) {
            const next = this.queue.shift();
            if (next)
                next();
        }
        else {
            this.isLocked = false;
        }
    }
    async ask(type, payload = {}) {
        await this.acquireLock();
        try {
            const sock = this.socket();
            await sock.send(JSON.stringify({ type, payload }));
            const [result] = await sock.receive();
            if (!result) {
                throw new Error("ZeroMQ received an empty frame from Python.");
            }
            return JSON.parse(result.toString());
        }
        finally {
            this.releaseLock();
        }
    }
}
// Export a singleton instance so all files share the exact same TCP socket
exports.brain = new BrainConnection();
//# sourceMappingURL=zmq-client.js.map