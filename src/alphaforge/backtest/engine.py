"""A-share constrained daily backtester.

Rules enforced (all configurable):
  * T+1: a position bought today cannot be sold today
  * limit-up: no buy when the open is at the up-limit
  * limit-down: no sell when the open is at the down-limit
  * suspension: no trade when volume == 0 / no valid price
  * lot size 100, participation cap, commission, stamp duty, slippage
  * signal at close t -> execution at t+1 open (no look-ahead)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from alphaforge.config import Config, load_config
from alphaforge.data.panel import Panel
from alphaforge.utils import connect


@dataclass
class Trade:
    date: str
    code: str
    side: str
    shares: int
    price: float
    value: float
    fee: float
    reason: str = ""


@dataclass
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    benchmark: pd.Series | None
    positions: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "start": str(self.equity.index[0]) if len(self.equity) else None,
            "end": str(self.equity.index[-1]) if len(self.equity) else None,
            "equity": [float(x) for x in self.equity.to_numpy()],
            "dates": [str(d.date()) for d in self.equity.index],
            "benchmark": ([float(x) for x in self.benchmark.to_numpy()]
                          if self.benchmark is not None else []),
            "trades": int(len(self.trades)),
            "config": self.config,
        }


def load_benchmark(panel: Panel, code: str, cfg: Config | None = None) -> pd.Series | None:
    cfg = cfg or load_config()
    try:
        conn = connect(cfg.paths.market_db, readonly=True)
        df = pd.read_sql_query("SELECT date,close FROM index_daily WHERE code=? ORDER BY date",
                               conn, params=[code.split(".")[0]])
        conn.close()
    except Exception:
        return None
    if df.empty:
        return None
    s = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["date"]))
    s = s.reindex(pd.DatetimeIndex(panel.dates)).ffill()
    return s


class Broker:
    def __init__(self, panel: Panel, cfg: Config):
        self.panel = panel
        self.cfg = cfg
        self.initial_cash = float(cfg.get("backtest.initial_cash", 10_000_000))
        self.cash = self.initial_cash
        self.shares: dict[int, int] = {}
        self.buy_idx: dict[int, int] = {}
        self.avg_cost: dict[int, float] = {}
        self.trades: list[Trade] = []
        self.commission = float(cfg.get("backtest.commission_bps", 3)) / 1e4
        self.stamp = float(cfg.get("backtest.stamp_duty_bps", 5)) / 1e4
        self.slippage = float(cfg.get("backtest.slippage_bps", 5)) / 1e4
        self.lot = int(cfg.get("backtest.lot_size", 100))
        self.participation = float(cfg.get("backtest.max_participation", 0.1))
        self.t_plus_one = bool(cfg.get("backtest.t_plus_one", True))
        self.exec_mode = str(cfg.get("backtest.execution", "next_open"))
        self.last_price = np.full(panel.shape[1], np.nan)
        self.total_traded = 0.0
        self.target: dict[int, float] = {}
        self.deferred_buy: set[int] = set()
        self.deferred_sell: set[int] = set()

    # -- prices / masks ----------------------------------------------------
    def exec_price(self, d: int, j: int) -> float:
        if self.exec_mode == "next_vwap":
            p = self.panel.field("vwap")[d, j]
        else:
            p = self.panel.field("open")[d, j]
        if not np.isfinite(p) or p <= 0:
            p = self.last_price[j]
        return float(p)

    def can_buy(self, d: int, j: int) -> bool:
        if not np.isfinite(self.panel.field("close")[d, j]):
            return False
        if self.panel.field("volume")[d, j] <= 0:
            return False
        op = self.panel.field("open")[d, j]
        up = self.panel.field("up_limit")[d, j]
        if np.isfinite(up) and np.isfinite(op) and op >= up - 0.005:
            return False
        return True

    def can_sell(self, d: int, j: int) -> bool:
        if not np.isfinite(self.panel.field("close")[d, j]):
            return False
        if self.panel.field("volume")[d, j] <= 0:
            return False
        op = self.panel.field("open")[d, j]
        down = self.panel.field("down_limit")[d, j]
        if np.isfinite(down) and np.isfinite(op) and op <= down + 0.005:
            return False
        return True

    # -- accounting --------------------------------------------------------
    def mark(self, d: int, price_field: str = "close") -> None:
        p = self.panel.field(price_field)[d]
        valid = np.isfinite(p)
        self.last_price[valid] = p[valid]

    def equity(self, price_field: str = "close", d: int | None = None) -> float:
        total = self.cash
        for j, sh in self.shares.items():
            price = self.panel.field(price_field)[d, j] if d is not None else self.last_price[j]
            if not np.isfinite(price):
                price = self.last_price[j]
            total += sh * float(price)
        return total

    def positions_frame(self, d: int) -> pd.DataFrame:
        rows = []
        for j, sh in self.shares.items():
            if sh <= 0:
                continue
            price = self.panel.field("close")[d, j]
            rows.append({
                "date": self.panel.date_strs[d],
                "code": self.panel.symbols[j],
                "shares": int(sh),
                "price": float(price) if np.isfinite(price) else np.nan,
                "value": float(sh * price) if np.isfinite(price) else np.nan,
            })
        return pd.DataFrame(rows)

    # -- execution ---------------------------------------------------------
    def _sell(self, d: int, j: int, desired_value: float) -> bool:
        """Try to sell down to ``desired_value``; return True when settled."""
        sh = self.shares.get(j, 0)
        if sh <= 0:
            return True
        price = self.exec_price(d, j)
        if not np.isfinite(price) or price <= 0:
            return False
        current = sh * price
        if current <= desired_value * 1.01:
            return True
        if self.t_plus_one and self.buy_idx.get(j, -10**9) >= d:
            return False
        if not self.can_sell(d, j):
            return False
        sell_shares = int((current - desired_value) / price // self.lot) * self.lot
        max_shares = int(self.panel.field("volume")[d, j] * self.participation // self.lot) * self.lot
        sell_shares = min(sell_shares, sh, max_shares)
        if sell_shares < self.lot:
            return True
        px = price * (1 - self.slippage)
        value = sell_shares * px
        fee = value * (self.commission + self.stamp)
        self.cash += value - fee
        self.shares[j] = sh - sell_shares
        self.total_traded += value
        self.trades.append(Trade(self.panel.date_strs[d], self.panel.symbols[j], "SELL",
                                 sell_shares, px, value, fee, "rebalance"))
        if self.shares[j] <= 0:
            self.shares.pop(j)
            self.buy_idx.pop(j, None)
        return True

    def _buy(self, d: int, j: int, target_weight: float, equity: float) -> bool:
        """Try to buy up to ``target_weight``; return True when settled."""
        price = self.exec_price(d, j)
        if not np.isfinite(price) or price <= 0 or not self.can_buy(d, j):
            return False
        desired = target_weight * equity
        current = self.shares.get(j, 0) * price
        if current >= desired * 0.99:
            return True
        buy_value = desired - current
        max_shares = int(self.panel.field("volume")[d, j] * self.participation // self.lot) * self.lot
        px = price * (1 + self.slippage)
        afford = int(max(self.cash, 0.0) / (px * (1 + self.commission)) // self.lot) * self.lot
        buy_shares = int(buy_value / px // self.lot) * self.lot
        buy_shares = min(buy_shares, max_shares, afford)
        if buy_shares < self.lot:
            return True
        value = buy_shares * px
        fee = max(value * self.commission, 5.0)
        if value + fee > self.cash:
            return False
        self.cash -= value + fee
        self.shares[j] = self.shares.get(j, 0) + buy_shares
        self.buy_idx[j] = d
        self.total_traded += value
        self.trades.append(Trade(self.panel.date_strs[d], self.panel.symbols[j], "BUY",
                                 buy_shares, px, value, fee, "rebalance"))
        return True

    def rebalance(self, d: int, target: dict[str, float]) -> None:
        idx = {c: i for i, c in enumerate(self.panel.symbols)}
        self.target = {idx[c]: w for c, w in target.items() if c in idx}
        self.deferred_buy.clear()
        self.deferred_sell.clear()
        equity = self.equity("open", d)
        if not np.isfinite(equity) or equity <= 0:
            return
        for j in list(self.shares):
            if not self._sell(d, j, self.target.get(j, 0.0) * equity):
                self.deferred_sell.add(j)
        equity = self.equity("open", d)
        if equity <= 0:
            return
        for j, w in sorted(self.target.items(), key=lambda kv: -kv[1]):
            if not self._buy(d, j, w, equity):
                self.deferred_buy.add(j)

    def retry(self, d: int) -> None:
        """Retry only the orders that were blocked (limit-up/down, suspension)."""
        if not self.target:
            return
        equity = self.equity("open", d)
        if equity <= 0:
            return
        for j in list(self.deferred_sell):
            if j not in self.shares:
                self.deferred_sell.discard(j)
                continue
            if self._sell(d, j, self.target.get(j, 0.0) * equity):
                self.deferred_sell.discard(j)
        equity = self.equity("open", d)
        for j in list(self.deferred_buy):
            if j not in self.target:
                self.deferred_buy.discard(j)
                continue
            if self._buy(d, j, self.target[j], equity):
                self.deferred_buy.discard(j)


def run_backtest(panel: Panel, targets: dict[int, dict[str, float]],
                 cfg: Config | None = None, start: str | None = None, end: str | None = None,
                 benchmark_code: str | None = None) -> BacktestResult:
    cfg = cfg or load_config()
    start_idx = panel.date_index(start, strict=False) if start else 0
    end_idx = panel.date_index(end, strict=False) if end else panel.shape[0] - 1
    if start_idx >= end_idx:
        raise ValueError("回测区间为空")
    broker = Broker(panel, cfg)
    equity = []
    dates = []
    position_rows = []
    pending: dict[str, float] | None = None
    benchmark_code = benchmark_code or cfg.get("backtest.benchmark", cfg.benchmark)

    for d in range(start_idx, end_idx + 1):
        # use yesterday's close as the fallback mark for illiquid names: today's
        # close is not known at the open when orders are executed
        if d > 0:
            broker.mark(d - 1)
        # signal at d-1 -> execute at today's open
        if (d - 1) in targets:
            pending = targets[d - 1]
            broker.rebalance(d, pending)
        elif pending is not None:
            broker.retry(d)
        broker.mark(d)
        eq = broker.equity("close", d)
        equity.append(eq)
        dates.append(pd.Timestamp(panel.dates[d]))
        position_rows.append(broker.positions_frame(d))

    eq = pd.Series(equity, index=pd.DatetimeIndex(dates), name="equity")
    rets = eq.pct_change().fillna(0.0)
    bench = load_benchmark(panel, benchmark_code, cfg)
    if bench is not None:
        bench = bench.reindex(eq.index).ffill().bfill()
        if len(bench) and bench.iloc[0] and np.isfinite(bench.iloc[0]):
            bench = bench / bench.iloc[0] * broker.initial_cash
    positions = pd.concat([p for p in position_rows if not p.empty], ignore_index=True) \
        if any(not p.empty for p in position_rows) else pd.DataFrame()
    trades = pd.DataFrame([t.__dict__ for t in broker.trades])
    metrics = compute_metrics(eq, rets, bench, broker, trades, cfg)
    return BacktestResult(equity=eq, returns=rets, benchmark=bench, positions=positions,
                          trades=trades, metrics=metrics,
                          config={"targets": len(targets), "start": str(eq.index[0].date()),
                                  "end": str(eq.index[-1].date())})


def compute_metrics(equity: pd.Series, returns: pd.Series, benchmark: pd.Series | None,
                    broker: Broker, trades: pd.DataFrame, cfg: Config) -> dict[str, Any]:
    n = len(equity)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1) if n else float("nan")
    years = max(n / 252.0, 1e-9)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if n else float("nan")
    vol = float(returns.std() * math.sqrt(252)) if n > 1 else float("nan")
    sharpe = float(returns.mean() / returns.std() * math.sqrt(252)) if n > 1 and returns.std() > 0 else float("nan")
    cum = (1 + returns).cumprod()
    dd = float((cum / cum.cummax() - 1).min()) if n else float("nan")
    calmar = cagr / abs(dd) if dd and abs(dd) > 1e-9 else float("nan")
    avg_equity = float(equity.mean()) if n else float("nan")
    turnover = float(broker.total_traded / avg_equity / years) if avg_equity else float("nan")
    out: dict[str, Any] = {
        "total_return": total, "cagr": cagr, "volatility": vol, "sharpe": sharpe,
        "max_drawdown": dd, "calmar": calmar, "turnover_annual": turnover,
        "initial_cash": broker.initial_cash, "final_equity": float(equity.iloc[-1]),
        "n_days": n, "n_trades": int(len(trades)),
        "avg_positions": float(trades[trades["side"] == "BUY"].groupby("date").size().mean())
        if not trades.empty and "side" in trades.columns else 0.0,
    }
    if benchmark is not None and len(benchmark) == len(equity):
        b = benchmark.pct_change().fillna(0.0)
        b_total = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1)
        out["benchmark_total_return"] = b_total
        out["excess_return"] = total - b_total
        excess = returns - b
        out["information_ratio"] = float(excess.mean() / excess.std() * math.sqrt(252)) \
            if excess.std() > 0 else float("nan")
        var_b = float(b.var())
        out["beta"] = float(returns.cov(b) / var_b) if var_b > 0 else float("nan")
    monthly = (1 + returns).resample("ME").prod() - 1
    out["monthly_returns"] = {str(k.date()): float(v) for k, v in monthly.items()}
    out["best_month"] = float(monthly.max()) if len(monthly) else float("nan")
    out["worst_month"] = float(monthly.min()) if len(monthly) else float("nan")
    out["win_rate_monthly"] = float((monthly > 0).mean()) if len(monthly) else float("nan")
    return out
