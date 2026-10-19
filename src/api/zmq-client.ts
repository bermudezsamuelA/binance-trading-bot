import { Request } from 'zeromq';
import { envValue } from '../config/env';

class BrainConnection {
    private sock: Request | null = null;
    private isLocked = false;
    private queue: (() => void)[] = [];

    // El socket se crea con la primera pregunta: importar este modulo (p. ej. en las pruebas) no abre conexiones
    private socket(): Request {
        if (!this.sock) {
            this.sock = new Request();
            // BRAIN_ZMQ_URL (opcional, .env): p. ej. tcp://host.docker.internal:5555 desde un contenedor Docker
            this.sock.connect(envValue('BRAIN_ZMQ_URL') || 'tcp://127.0.0.1:5555');
        }
        return this.sock;
    }

    private async acquireLock(): Promise<void> {
        if (!this.isLocked) {
            this.isLocked = true;
            return Promise.resolve();
        }
        return new Promise(resolve => this.queue.push(resolve));
    }

    private releaseLock(): void {
        if (this.queue.length > 0) {
            const next = this.queue.shift();
            if (next) next();
        } else {
            this.isLocked = false;
        }
    }

    public async ask(type: string, payload: any = {}): Promise<any> {
        await this.acquireLock();
        try {
            const sock = this.socket();
            await sock.send(JSON.stringify({ type, payload }));
            const [result] = await sock.receive();
            if (!result) {
                throw new Error("ZeroMQ received an empty frame from Python.");
            }
            
            return JSON.parse(result.toString());
        } finally {
            this.releaseLock();
        }
    }
}

// Export a singleton instance so all files share the exact same TCP socket
export const brain = new BrainConnection();