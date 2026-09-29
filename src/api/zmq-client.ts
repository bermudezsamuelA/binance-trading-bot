import { Request } from 'zeromq';

class BrainConnection {
    private sock: Request;
    private isLocked = false;
    private queue: (() => void)[] = [];

    constructor() {
        this.sock = new Request();
        this.sock.connect('tcp://127.0.0.1:5555');
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
            await this.sock.send(JSON.stringify({ type, payload }));
            const [result] = await this.sock.receive();
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