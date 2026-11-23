"""Thin wrapper around neuralforecast: long-format panels, calendar features, fit and forecast.
Nothing here reads files; it only sees the series it is handed (already cut at an origin)."""
import logging, os, warnings
import numpy as np, pandas as pd

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
warnings.filterwarnings("ignore")

from neuralforecast import NeuralForecast                                  # noqa: E402
from neuralforecast import models as NFM                                   # noqa: E402
from neuralforecast.losses.pytorch import MAE                               # noqa: E402

from . import specs as S                                                    # noqa: E402

# Lightning sets its own log levels on import, so quieten it afterwards.
for _name in list(logging.root.manager.loggerDict):
    if _name.split(".")[0] in ("pytorch_lightning", "lightning", "lightning_fabric", "neuralforecast"):
        logging.getLogger(_name).setLevel(logging.ERROR)

CLASSES = {"lstm": NFM.LSTM, "gru": NFM.GRU, "nbeats": NFM.NBEATS, "nhits": NFM.NHITS, "tft": NFM.TFT, "patchtst": NFM.PatchTST}
FREQ = {"monthly": "MS", "daily": "D"}


def calendar(ds, resolution):
    """Calendar features known in advance. Monthly: month-of-year sin/cos (as the frozen MLP). Daily: day-of-week one-hot."""
    ds = pd.DatetimeIndex(ds)
    if resolution == "monthly":
        a = 2 * np.pi * ds.month.values / 12
        return {"m_sin": np.sin(a), "m_cos": np.cos(a)}
    return {f"dow{k}": (ds.dayofweek.values == k).astype(float) for k in range(7)}


def calendar_cols(resolution):
    return ["m_sin", "m_cos"] if resolution == "monthly" else [f"dow{k}" for k in range(7)]


def to_long(series, resolution):
    """{unit: pd.Series of log values} -> long DataFrame unique_id, ds, y (+ calendar columns)."""
    parts = []
    for u, s in series.items():
        if len(s) == 0:
            continue
        ds = s.index.to_timestamp(how="start") if isinstance(s.index, pd.PeriodIndex) else pd.DatetimeIndex(s.index)
        df = pd.DataFrame({"unique_id": u, "ds": ds, "y": s.values.astype(np.float64)})
        for k, v in calendar(ds, resolution).items():
            df[k] = v
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def future_frame(long_df, h, resolution):
    last = long_df.groupby("unique_id").ds.max()
    off = pd.offsets.MonthBegin(1) if resolution == "monthly" else pd.Timedelta(days=1)
    rows = []
    for u, t in last.items():
        ds = pd.DatetimeIndex([t + off * k for k in range(1, h + 1)]) if resolution == "monthly" else pd.date_range(t + off, periods=h, freq="D")
        df = pd.DataFrame({"unique_id": u, "ds": ds})
        for k, v in calendar(ds, resolution).items():
            df[k] = v
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def build(model, cfg, resolution, h, seed, device, max_steps=None):
    cls = CLASSES[model]
    kw = dict(S.COMMON); kw.update(cfg)
    kw["loss"] = MAE(); kw["valid_loss"] = MAE()
    kw["max_steps"] = max_steps if max_steps is not None else S.STEPS[resolution]
    kw["random_seed"] = int(seed)
    if getattr(cls, "EXOGENOUS_FUTR", False):
        kw["futr_exog_list"] = calendar_cols(resolution)
    trainer = dict(accelerator="gpu" if device == "cuda" else "cpu", devices=1, enable_progress_bar=False,
                   enable_model_summary=False, logger=False, enable_checkpointing=False, deterministic="warn")
    return cls(h=h, alias=model, **kw, **trainer)


class Fitted:
    """One model fitted on a panel cut at a refit origin; forecasts from that origin or any later one."""
    def __init__(self, model, cfg, resolution, h, seed, device, train_series, max_steps=None):
        self.model, self.res, self.h = model, resolution, h
        self.input_size = cfg["input_size"]
        train = {u: s for u, s in train_series.items() if len(s) >= self.input_size + h}
        self.nf = NeuralForecast(models=[build(model, cfg, resolution, h, seed, device, max_steps)], freq=FREQ[resolution])
        self.nf.fit(df=to_long(train, resolution), val_size=0)

    def forecast(self, series):
        """{unit: history cut at the forecast origin} -> {unit: array of h forecasts} (NaN if too short)."""
        ok = {u: s for u, s in series.items() if len(s) >= self.input_size}
        out = {u: np.full(self.h, np.nan) for u in series}
        if not ok:
            return out
        df = to_long(ok, self.res)
        fut = future_frame(df, self.h, self.res)
        p = self.nf.predict(df=df, futr_df=fut if getattr(CLASSES[self.model], "EXOGENOUS_FUTR", False) else None)
        p = p.reset_index() if "unique_id" not in p.columns else p
        for u, g in p.groupby("unique_id"):
            out[u] = g.sort_values("ds")[self.model].values.astype(float)
        return out
