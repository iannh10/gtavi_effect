"""Plug any forecaster into halo's own backtest harness without editing halo.

halo.backtest.monthly_backtest / daily_backtest call `halo.models.MONTHLY[name](history_values, H)` (or DAILY) for
every (origin, unit). A deep global model needs to know which unit and origin it is forecasting, so HistoryAdapter
recovers both from the history it is handed and asserts the history is exactly that unit's series cut at that origin.
The name is registered in halo's dict in memory only for the duration of one harness call.
"""
from contextlib import contextmanager
import numpy as np, pandas as pd
from halo import backtest as B, models as M


class HistoryAdapter:
    def __init__(self, tg, forecaster):
        """tg: {unit: pd.Series} (one target type). forecaster(unit, origin) -> array of H forecasts."""
        self.tg, self.forecaster = tg, forecaster
        self.vals = {u: s.values for u, s in tg.items()}
        self.calls = []

    def identify(self, y):
        n = len(y)
        hits = [u for u, v in self.vals.items() if len(v) >= n and np.array_equal(v[:n], y)]
        assert len(hits) == 1, f"adapter could not identify a unique unit for a history of length {n}: {hits}"
        u = hits[0]
        return u, self.tg[u].index[n - 1]

    def __call__(self, y, H):
        u, o = self.identify(np.asarray(y))
        assert np.array_equal(self.tg[u].loc[:o].values, y), "history is not the unit's series cut at the origin"
        self.calls.append((u, o))
        f = np.asarray(self.forecaster(u, o), dtype=float)
        assert f.shape == (H,), f"forecaster returned shape {f.shape}, expected ({H},)"
        return f


@contextmanager
def registered(resolution, name, fn):
    table = M.MONTHLY if resolution == "monthly" else M.DAILY
    assert name not in table, f"{name} would shadow a frozen model"
    table[name] = fn
    try:
        yield
    finally:
        del table[name]


def run_harness(resolution, tg, units_eval, name, forecaster, c, origins=None):
    """Run halo's harness for one model through the adapter. Returns halo's own error frame."""
    ad = HistoryAdapter(tg, forecaster)
    with registered(resolution, name, ad):
        if resolution == "monthly":
            return B.monthly_backtest(tg, units_eval, [name], c, origins=origins)
        return B.daily_backtest(tg, units_eval, [name], c, origins=origins)


def all_origins(resolution, c):
    """The harness's default origins, as halo computes them."""
    if resolution == "monthly":
        return list(pd.period_range(c["monthly"]["backtest_start"], c["monthly"]["backtest_end"], freq="M"))
    return list(pd.date_range(c["daily"]["bt_first"], c["daily"]["bt_last"], freq="D"))


def selection_metric(bt, resolution, c):
    """{model: selection-metric MAE}, computed exactly as halo.backtest.main does."""
    if resolution == "monthly":
        return bt[bt.h == 2].dropna().groupby("model").err.apply(lambda e: e.abs().mean()).to_dict()
    return B.window_errors(bt, c).groupby("model").err.apply(lambda e: e.abs().mean()).to_dict()


def selection_n(bt, resolution, c):
    if resolution == "monthly":
        return bt[bt.h == 2].dropna().groupby("model").size().to_dict()
    return B.window_errors(bt, c).groupby("model").size().to_dict()
