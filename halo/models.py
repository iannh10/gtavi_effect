"""Forecasters. Every function sees only the history it is handed (already cut at the origin)."""
import warnings
import numpy as np, pandas as pd, torch
from torch import nn

warnings.filterwarnings("ignore")
torch.set_num_threads(2)

# ---------------------------------------------------------------- monthly (log avg players)
def m_naive(y, H=2):
    t = len(y) - 1
    return np.array([y[t] + y[t + h - 12] - y[t - 12] if t >= 12 else np.nan for h in range(1, H + 1)])

def m_clim(y, H=2):
    t = len(y) - 1; out = []
    for h in range(1, H + 1):
        ch = [y[t - 12 * k + h] - y[t - 12 * k] for k in range(1, 40) if t - 12 * k >= 0]
        out.append(y[t] + np.mean(ch) if len(ch) >= 2 else np.nan)
    return np.array(out)

def m_sarima(y, H=2):
    if len(y) < 30:
        return np.full(H, np.nan)
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    try:
        r = SARIMAX(y, order=(0, 1, 1), seasonal_order=(0, 1, 1, 12)).fit(disp=False, maxiter=100)
        f = np.asarray(r.forecast(H))
        return f if np.all(np.isfinite(f)) and np.all(np.abs(f - y[-1]) < 3) else np.full(H, np.nan)
    except Exception:
        return np.full(H, np.nan)

# ---------------------------------------------------------------- daily (log daily peak)
def d_naive(y, H):
    t = len(y) - 1
    return np.array([y[t + h - 7 * int(np.ceil(h / 7))] for h in range(1, H + 1)])

def _ets(y, H, damped):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    try:
        m = ExponentialSmoothing(y, trend="add" if damped else None, damped_trend=damped,
                                 seasonal="add", seasonal_periods=7, initialization_method="estimated").fit()
        return np.asarray(m.forecast(H))
    except Exception:
        return np.full(H, np.nan)

def d_ets(y, H): return _ets(y, H, False)
def d_ets_damped(y, H): return _ets(y, H, True)

def d_sarimax_trends(y, H, x):
    """x: log1p('GTA 5' search interest) aligned with y. Future x is held at its last-7-day mean.
    Information only: never eligible for the frozen forecast (see pre-registration)."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    try:
        r = SARIMAX(y, exog=x, order=(1, 0, 0), seasonal_order=(0, 1, 1, 7)).fit(disp=False, maxiter=100)
        return np.asarray(r.forecast(H, exog=np.full((H, 1), x[-7:].mean())))
    except Exception:
        return np.full(H, np.nan)

def dow_effects(s, weeks=8):
    """Mean deviation from the overall mean by day of week, last `weeks` weeks of a daily series."""
    s = s.iloc[-7 * weeks:]
    return (s.groupby(s.index.dayofweek).mean() - s.mean()).to_dict()

# ---------------------------------------------------------------- pooled neural forecaster
def _device(c):
    d = c["nn"]["device"]
    return torch.device("cuda" if (d == "auto" and torch.cuda.is_available()) or d == "cuda" else "cpu")

class PanelMLP:
    """Small MLP trained across all panel series; an ensemble over fixed seeds."""
    def __init__(self, c, seed):
        self.c, self.seed, self.nets = c, seed, []
    def fit(self, X, Y):
        n, dev = self.c["nn"], _device(self.c)
        X = torch.tensor(X, dtype=torch.float32, device=dev); Y = torch.tensor(Y, dtype=torch.float32, device=dev)
        for k in range(n["seeds"]):
            torch.manual_seed(self.seed + k)
            net = nn.Sequential(nn.Linear(X.shape[1], n["hidden"]), nn.ReLU(), nn.Dropout(n["dropout"]),
                                nn.Linear(n["hidden"], n["hidden"]), nn.ReLU(), nn.Linear(n["hidden"], Y.shape[1])).to(dev)
            opt = torch.optim.Adam(net.parameters(), lr=n["lr"], weight_decay=n["weight_decay"])
            loss = nn.HuberLoss(delta=n["huber_delta"])
            net.train()
            for _ in range(n["epochs"]):
                opt.zero_grad(); loss(net(X), Y).backward(); opt.step()
            net.eval(); self.nets.append(net)
        return self
    def predict(self, x):
        dev = _device(self.c)
        with torch.no_grad():
            x = torch.tensor(np.atleast_2d(x), dtype=torch.float32, device=dev)
            return np.mean([net(x).cpu().numpy() for net in self.nets], axis=0)

def monthly_feat(y, month, lags):
    a = 2 * np.pi * month / 12
    return np.concatenate([y[-lags:] - y[-1], [np.sin(a), np.cos(a)]])

def monthly_xy(s, lags, H):
    """Training pairs from one series (already cut at the origin). Targets never pass its end."""
    y, mo = s.values, s.index.month.values; X, Y = [], []
    for i in range(lags - 1, len(y) - H):
        X.append(monthly_feat(y[: i + 1], mo[i], lags)); Y.append(y[i + 1: i + 1 + H] - y[i])
    return X, Y

def daily_feat(y, dow, lags):
    return np.concatenate([y[-lags:] - y[-7:].mean(), np.eye(7)[dow]])

def daily_xy(s, lags, H):
    y, dw = s.values, s.index.dayofweek.values; X, Y = [], []
    for i in range(lags - 1, len(y) - H):
        X.append(daily_feat(y[: i + 1], dw[i], lags)); Y.append(y[i + 1: i + 1 + H] - y[i - 6: i + 1].mean())
    return X, Y

def fit_panel_nn(series_list, c, kind):
    """series_list: panel series already cut at the origin. Returns a fitted PanelMLP or None."""
    lags, H = (c["nn"]["monthly_lags"], c["monthly"]["horizon"]) if kind == "monthly" else (c["nn"]["daily_lags"], c["daily"]["horizon"])
    X, Y = [], []
    for s in series_list:
        x, y = (monthly_xy if kind == "monthly" else daily_xy)(s, lags, H); X += x; Y += y
    if len(X) < 100:
        return None
    return PanelMLP(c, c["seed"]).fit(np.array(X), np.array(Y))

def nn_predict(model, s, c, kind):
    if kind == "monthly":
        lags, H = c["nn"]["monthly_lags"], c["monthly"]["horizon"]
        if model is None or len(s) < lags: return np.full(H, np.nan)
        return s.values[-1] + model.predict(monthly_feat(s.values, s.index.month[-1], lags))[0]
    lags, H = c["nn"]["daily_lags"], c["daily"]["horizon"]
    if model is None or len(s) < lags: return np.full(H, np.nan)
    return s.values[-7:].mean() + model.predict(daily_feat(s.values, s.index.dayofweek[-1], lags))[0]

MONTHLY = {"naive": m_naive, "clim": m_clim, "sarima": m_sarima}
DAILY = {"naive": d_naive, "ets": d_ets, "ets_damped": d_ets_damped}
