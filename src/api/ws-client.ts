import WebSocket from 'ws';
import { BinanceRestClient } from './rest-client';
import { brain } from './zmq-client';

interface Position {
    symbol: string;
    orderId: number;
    entryPrice: number;
    takeProfit: number;
    stopLoss: number;
    quantity: number;
}

export class BinanceWSClient {
    private ws: WebSocket;
    private baseUrl = 'wss://stream.testnet.binance.vision/stream?streams=';
    private restClient = new BinanceRestClient();
    
    // Tracks active trades by symbol
    private activePositions: Map<string, Position> = new Map();
    // Throttle / cooldown tracker per symbol
    private lastEvaluationTime: Map<string, number> = new Map();

    constructor(roster: string[]) {
        const streams = roster.map(symbol => `${symbol.toLowerCase()}@bookTicker`).join('/');
        const url = `${this.baseUrl}${streams}`;
        
        this.ws = new WebSocket(url);
        this.initializeEvents();
    }

    private initializeEvents() {
        this.ws.on('open', () => {
            console.log(`🟢 WebSocket connected to combined stream.`);
        });

        this.ws.on('message', async (data: WebSocket.RawData) => {
            try {
                const parsedData = JSON.parse(data.toString());
                if (parsedData.data && parsedData.data.u) {
                    await this.handleMarketData(parsedData.data);
                }
            } catch (err) {
                // Ignore parse hiccups on heartbeat frames
            }
        });

        this.ws.on('error', (error) => console.error('🔴 Error de WebSocket:', error));
        this.ws.on('close', () => console.log('⚫ Conexión WebSocket cerrada.'));
    }

    private async handleMarketData(data: any) {
        const symbol = data.s;
        const currentPrice = (parseFloat(data.b) + parseFloat(data.a)) / 2;

        // 1. POSITION MANAGEMENT: If active, monitor TP/SL
        if (this.activePositions.has(symbol)) {
            await this.manageExistingPosition(symbol, currentPrice);
            return; 
        }

        // 2. SIGNAL DISCOVERY: Check if cooled down (minimum 5s)
        const now = Date.now();
        const lastEval = this.lastEvaluationTime.get(symbol) || 0;
        
        if (now - lastEval > 5000) {
            this.lastEvaluationTime.set(symbol, now);
            await this.evaluateNewTrade(symbol, currentPrice, data.E);
        }
    }

    private async manageExistingPosition(symbol: string, currentPrice: number) {
        const position = this.activePositions.get(symbol)!;

        if (currentPrice >= position.takeProfit) {
            console.log(`\n💰 [TAKE PROFIT HIT] ${symbol} @ ${currentPrice}. Exiting trade.`);
            await this.closePosition(symbol, position, currentPrice);
        } else if (currentPrice <= position.stopLoss) {
            console.log(`\n🛡️ [STOP LOSS HIT] ${symbol} @ ${currentPrice}. Cutting losses.`);
            await this.closePosition(symbol, position, currentPrice);
        }
    }

    private async evaluateNewTrade(symbol: string, currentPrice: number, timestamp: number) {
        try {
            // ZeroMQ Request to Python Brain
            const signal = await brain.ask('evaluate', {
                symbol: symbol,
                current_price: currentPrice,
                timestamp: timestamp
            });

            if (signal && signal.action === 'BUY') {
                console.log(`\n=========================================`);
                console.log(`🚀 [NUEVO TRADE] Python recomienda comprar ${symbol}`);
                console.log(`   Entrada: ${signal.entry_price} | TP: ${signal.take_profit} | SL: ${signal.stop_loss}`);
                
                const targetUsdtAllocation = 15.0; 
                const rawQuantity = targetUsdtAllocation / signal.entry_price;
                
                const decimals = symbol === 'BTCUSDT' ? 5 : 3;
                const factor = Math.pow(10, decimals);
                const safeQuantity = Math.floor(rawQuantity * factor) / factor;

                const orderResult = await this.restClient.placeLimitOrder(
                    symbol,
                    'BUY',
                    safeQuantity,
                    signal.entry_price
                );

                const positionData: Position = {
                    symbol: symbol,
                    orderId: orderResult.orderId,
                    entryPrice: signal.entry_price,
                    takeProfit: signal.take_profit,
                    stopLoss: signal.stop_loss,
                    quantity: safeQuantity
                };
                
                this.activePositions.set(symbol, positionData);

                // Log OPEN trade via ZeroMQ
                try {
                    await brain.ask('ledger_open', {
                        order_id: positionData.orderId,
                        symbol: positionData.symbol,
                        action: "BUY",
                        entry_price: positionData.entryPrice,
                        take_profit: positionData.takeProfit,
                        stop_loss: positionData.stopLoss,
                        quantity: positionData.quantity
                    });
                    console.log(`✅ Trade logged securely in Python CSV Ledger via ZMQ.`);
                } catch (ledgerError) {
                    console.error(`⚠️ Failed to log trade to Python ledger.`);
                }
                
                console.log(`=========================================\n`);
            }
        } catch (error: any) {
            if (error.response?.data) {
                console.log(`❌ Order failed for ${symbol}:`, error.response.data.msg);
                console.log(`⏳ Applying 60-second cooldown to ${symbol}...`);
                this.lastEvaluationTime.set(symbol, Date.now() + 60000);
            }
        }
    }

    private async closePosition(symbol: string, position: Position, exitPrice: number) {
        try {
            const orderResult = await this.restClient.placeLimitOrder(
                symbol,
                'SELL',
                position.quantity,
                exitPrice 
            );
            console.log(`✅ [EXIT CONFIRMED] ${symbol} closed. Order ID: ${orderResult.orderId}`);
            
            this.activePositions.delete(symbol);

            // Log CLOSED trade via ZeroMQ
            try {
                await brain.ask('ledger_close', { order_id: position.orderId });
                console.log(`🔒 Ledger updated: Trade ${position.orderId} marked as CLOSED.`);
            } catch (ledgerError) {
                console.error(`⚠️ Failed to update Python ledger closure.`);
            }

        } catch (error: any) {
            console.error(`🔴 Error closing position for ${symbol}:`, error.message);
        }
    }

    public async syncStateFromLedger() {
        try {
            const openTrades = await brain.ask('sync_positions');
            
            for (const trade of openTrades) {
                this.activePositions.set(trade.symbol, {
                    symbol: trade.symbol,
                    orderId: trade.order_id,
                    entryPrice: trade.entry_price,
                    takeProfit: trade.take_profit,
                    stopLoss: trade.stop_loss,
                    quantity: trade.quantity
                });
            }
            if (this.activePositions.size > 0) {
                console.log(`🔄 Synced ${this.activePositions.size} active position(s) from Python Ledger.`);
            }
        } catch (error) {
            console.error(`⚠️ Failed to sync state from ledger.`, error);
        }
    }

    public close() {
        this.ws.close();
    }
}