"""Dip-snap cbBTC trading bot for make.fun's btc-race-24h-20261117-0603.

Strategy (validated on the 24h dev window: net PnL +$20.09, 4 trades, max
drawdown 1.22%; buy-and-hold on the same window makes +$1.07 and every
fast trend/mean-reversion variant loses money to the ~26 bps round-trip cost):

- Flat: buy all-in when the close has fallen 0.9% or more over the last
  30 bars (a sharp dip), i.e. close * 1000 <= close_30_bars_ago * 991.
- Holding: sell everything when the close is 1.2% above the entry close
  (take profit) or 1.2% below it (stop-loss), i.e. close * 1000 >= entry * 1012
  or close * 1000 <= entry * 988.
- Late-entry fallback: if no trade has completed by batch 1000 and the close
  is above its 240-bar EMA, buy (same exits). This guarantees at least one
  trade in a smooth uptrend window where no sharp dip ever appears; it never
  fires on the dev window, so it costs nothing there.

All arithmetic is integer (fixed-point EMA), no randomness, no clock, no
environment, no file access: two runs on the same data are byte-identical.
One symbol only (CBBTC), long only, at most one open position. Orders use
max_slippage_bps 500. The bot speaks agent-fun/bars-replay/v1 through the
vendored SDK shim (vendor/makefun_bars.py, byte-for-byte copy of the kit's).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 30          # bars for the dip measurement
DROP_NUM = 991         # buy when close * 1000 <= close_30_ago * 991 (<= -0.9%)
TP_NUM = 1012          # sell when close * 1000 >= entry * 1012 (>= +1.2%)
SL_NUM = 988           # sell when close * 1000 <= entry * 988 (<= -1.2%)
LATE_BAR = 1000        # first batch the late-entry fallback may fire on
EMA_SPAN = 240         # bars for the late-entry trend filter
EMA_SCALE = 1_000_000
EMA_K = 2 * EMA_SCALE // (EMA_SPAN + 1)
MAX_SLIPPAGE_BPS = 500

closes = []            # CBBTC closes (ints), one per batch that carries its bar
entry = None           # entry close of the open position (None when flat)
pending_buy = False    # a buy was decided last batch; cleared once it fills
completed_trades = 0   # sells observed to empty the position
late_done = False      # the late-entry fallback has fired
ema = None             # 240-bar EMA of closes (fixed point, price units)
prev_qty = 0           # position qty on the previous batch


def on_batch(state, batch):
    global entry, pending_buy, completed_trades, late_done, ema, prev_qty
    # Only act on batches that actually carry this minute's CBBTC bar.
    has_bar = any(b.get("symbol") == SYMBOL for b in batch.get("bars", []))
    close = state.close(SYMBOL)
    if close is None:
        return []
    if has_bar:
        closes.append(close)
        if len(closes) >= EMA_SPAN and ema is None:
            ema = sum(closes[-EMA_SPAN:]) // EMA_SPAN
        elif ema is not None:
            ema = (close * EMA_K + ema * (EMA_SCALE - EMA_K)) // EMA_SCALE
    held = state.positions.get(SYMBOL)
    qty = held.qty if held else 0
    if prev_qty > 0 and qty == 0:
        completed_trades += 1  # a sell completed: the position is empty now
    prev_qty = qty
    if pending_buy:
        if qty > 0:
            pending_buy = False  # the buy filled; keep the entry close
        else:
            entry = None         # the buy was rejected; forget the entry
            pending_buy = False
    if state.warming_up:
        return []
    if qty > 0:
        if entry is not None:
            if close * 1000 >= entry * TP_NUM or close * 1000 <= entry * SL_NUM:
                entry = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if len(closes) >= LOOKBACK + 1:
        if closes[-1] * 1000 <= closes[-1 - LOOKBACK] * DROP_NUM:
            entry = close
            pending_buy = True
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if (not late_done and completed_trades == 0 and state.seq >= LATE_BAR
            and ema is not None and close > ema):
        entry = close
        pending_buy = True
        late_done = True
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
