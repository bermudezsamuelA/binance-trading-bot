declare class BrainConnection {
    private sock;
    private isLocked;
    private queue;
    private socket;
    private acquireLock;
    private releaseLock;
    ask(type: string, payload?: any): Promise<any>;
}
export declare const brain: BrainConnection;
export {};
//# sourceMappingURL=zmq-client.d.ts.map