"""Dip-snap cbBTC trading bot for make.fun's btc-race-24h-20261117-0603.

Strategy (E7 — validated on the 24h dev window by the real harness:
net PnL +$16.73, 4 trades, max drawdown 0.66%; buy-and-hold on the same
window makes +$1.07 and every fast trend/mean-reversion variant loses
money to the ~26 bps round-trip cost):

- Flat: buy all-in when the close has fallen 0.9% or more over the last
  45 bars (a sharp dip), i.e. close * 1000 <= close_45_bars_ago * 991.
  A 45-bar lookback (not 30) is what survives regime shuffling: on 48
  fresh block-bootstrap 24h windows rebuilt from the dev window it keeps
  a median PnL of +$16.86 with 6 losing windows, vs +$16.72 / 7 for the
  30-bar version.
- Downtrend gate: dip buys (main and second-chance) are only taken when
  the 720-bar return is >= -1%, i.e. the 12-hour trend is not in a
  sustained decline. Before 721 closes exist the gate passes. This cuts
  the worst case in a steady -3%/day drift window from -$27.45 (E5) to
  -$15.49 without touching dev PnL or the bootstrap median.
- Time stop: a position held 300 bars without hitting TP/SL is sold at
  market. The dev trades last 141/118 bars, so it costs nothing there;
  it stops a dip-buy from riding a slow drift for 12 hours (down-drift
  loss falls further to -$7.53, flat-range loss to -$0.15).
- Holding: sell everything when the close is 1.2% above the entry close
  (take profit) or 1.2% below it (stop-loss), i.e. close * 1000 >=
  entry * 1012 or close * 1000 <= entry * 988.
- Second-chance dip: if no trade has completed by batch 1000, also accept
  a 0.9% dip measured over 60 bars. In calm windows the 45-bar dip never
  appears, but the slower 60-bar dip does; this keeps the bot trading
  (and profitable) in range-like windows instead of sitting out.
- Late-entry fallback: if still no trade has completed by batch 1000 and
  the close is above its 240-bar EMA *and* the 60-bar return is at least
  +0.5%, buy (same exits). The trend filter keeps it from buying the top
  of a range; it never fires on the dev window, so it costs nothing there.

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
LOOKBACK = 45          # bars for the dip measurement
DROP_NUM = 991         # buy when close * 1000 <= close_45_ago * 991 (<= -0.9%)
TP_NUM = 1012          # sell when close * 1000 >= entry * 1012 (>= +1.2%)
SL_NUM = 988           # sell when close * 1000 <= entry * 988 (<= -1.2%)
LATE_BAR = 1000        # first batch the late-entry fallback may fire on
EMA_SPAN = 240         # bars for the late-entry trend filter
EMA_SCALE = 1_000_000
EMA_K = 2 * EMA_SCALE // (EMA_SPAN + 1)
HEDGE_TREND_LOOKBACK = 60   # bars for the late-entry trend filter
HEDGE_TREND_BPS = 50        # late entry needs a 60-bar return >= +0.5%
SC_LOOKBACK = 60       # bars for the second-chance dip measurement
SC_DROP_NUM = 991      # second-chance dip: close * 1000 <= close_60_ago * 991
SC_BAR = 1000          # first batch the second-chance dip may fire on
MAX_SLIPPAGE_BPS = 500
DT_SPAN = 720          # bars for the downtrend gate (12-hour return)
DT_MIN_BPS = -100      # dip buys need a 720-bar return >= -1%
TIME_STOP = 300        # bars held without TP/SL before selling at market

closes = []            # CBBTC closes (ints), one per batch that carries its bar
entry = None           # entry close of the open position (None when flat)
pending_buy = False    # a buy was decided last batch; cleared once it fills
completed_trades = 0   # sells observed to empty the position
late_done = False      # the late-entry fallback has fired
ema = None             # 240-bar EMA of closes (fixed point, price units)
prev_qty = 0           # position qty on the previous batch
hold_start = -1        # batch seq when the open position's buy filled


def downtrend_ok():
    """True unless the 720-bar return is below -1% (sustained decline).
    Passes while fewer than 721 closes exist."""
    if len(closes) < DT_SPAN + 1:
        return True
    return ((closes[-1] - closes[-1 - DT_SPAN]) * 10000
            // closes[-1 - DT_SPAN] >= DT_MIN_BPS)


def on_batch(state, batch):
    global entry, pending_buy, completed_trades, late_done, ema, prev_qty, hold_start
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
            hold_start = state.seq
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
        if hold_start >= 0 and state.seq - hold_start >= TIME_STOP:
            entry = None
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []
    if len(closes) >= LOOKBACK + 1:
        if (closes[-1] * 1000 <= closes[-1 - LOOKBACK] * DROP_NUM
                and downtrend_ok()):
            entry = close
            pending_buy = True
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if (completed_trades == 0 and state.seq >= SC_BAR
            and len(closes) >= SC_LOOKBACK + 1
            and closes[-1] * 1000 <= closes[-1 - SC_LOOKBACK] * SC_DROP_NUM
            and downtrend_ok()):
        entry = close
        pending_buy = True
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if (not late_done and completed_trades == 0 and state.seq >= LATE_BAR
            and ema is not None and close > ema
            and len(closes) >= HEDGE_TREND_LOOKBACK + 1
            and (closes[-1] - closes[-1 - HEDGE_TREND_LOOKBACK]) * 10000
            // closes[-1 - HEDGE_TREND_LOOKBACK] >= HEDGE_TREND_BPS):
        entry = close
        pending_buy = True
        late_done = True
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
