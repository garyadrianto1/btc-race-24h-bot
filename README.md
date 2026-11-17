# btc-race-24h-bot

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/garyadrianto1/btc-race-24h-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/garyadrianto1/btc-race-24h-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A dip-buying cbBTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty: it buys all-in after a sharp 30-minute dip (-0.9% or more) and sells everything at +1.2% take-profit or -1.2% stop-loss, with a late trend-entry fallback so it always trades at least once. Local dev grade on the published 24h dev window: net PnL +$20.09, 4 trades, max drawdown 1.22% (buy-and-hold makes +$1.07 on the same window).

## Run it

```sh
python3 main.py
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout (one JSON line per minute bar, one reply per batch) through the vendored SDK shim in `vendor/`. Standard library only, integer arithmetic, deterministic.

---

<sub>Entered on [make.fun](https://make.fun/?ref=m1ceh0z1&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
