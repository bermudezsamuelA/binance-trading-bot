from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import time

app = FastAPI(
    title="Quantitative Strategy Engine",
    description="Python backend providing signals and spread parameters to the Node.js execution bot.",
    version="1.0.0"
)

# Request schema: What Node.js sends from its WebSocket stream
class MarketState(BaseModel):
    symbol: str
    bid_price: float
    ask_price: float
    bid_qty: float
    ask_qty: float
    timestamp: Optional[int] = None

# Response schema: What Node.js receives to place orders
class StrategySignal(BaseModel):
    symbol: str
    action: str              # "HOLD", "BUY", "SELL", "PROVIDE_LIQUIDITY"
    target_bid_price: float  # Limit buy order placement
    target_ask_price: float  # Limit sell order placement
    spread_pct: float        # Calculated spread percentage
    confidence: float        # Signal strength (0.0 to 1.0)

@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "strategy-engine",
        "timestamp": int(time.time() * 1000)
    }

@app.post("/strategy/evaluate", response_model=StrategySignal)
def evaluate_market_state(state: MarketState):
    """
    Receives live ticker data from Node.js, computes analytical metrics,
    and returns precise order placement guidelines.
    """
    mid_price = (state.bid_price + state.ask_price) / 2.0
    current_spread = ((state.ask_price - state.bid_price) / mid_price) * 100.0

    # Baseline placeholder calculation (to be replaced with statistical model)
    target_spread_offset = mid_price * 0.001  # 0.10% distance from mid price

    return StrategySignal(
        symbol=state.symbol.upper(),
        action="PROVIDE_LIQUIDITY",
        target_bid_price=round(mid_price - target_spread_offset, 2),
        target_ask_price=round(mid_price + target_spread_offset, 2),
        spread_pct=round(current_spread, 4),
        confidence=0.85
    )