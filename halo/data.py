"""Loading, cleaning and the control index. Everything here is causal: a value at time t
depends only on data at or before t, so truncating at an origin can never leak the future."""
import os
import numpy as np, pandas as pd, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET, SIBLING = "GTAV", "1174180"

def cfg():
    with open(os.path.join(ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)

def _read(name, post_name=None):
    df = pd.read_csv(os.path.join(ROOT, "data", name), dtype={"app_id": str})
    post = os.path.join(ROOT, "data", "post", post_name or "")
    if post_name and os.path.exists(post):
        df = pd.concat([df, pd.read_csv(post, dtype={"app_id": str})], ignore_index=True)
    return df

def roles_names():
    df = _read("panel_monthly_avg.csv")
    g = df.drop_duplicates("app_id")
    return dict(zip(g.app_id, g.role)), dict(zip(g.app_id, g.name))

def load_monthly(c, with_post=False):
    """Wide table of log monthly average players. Index: month Period. Columns: unit ids."""
    df = _read("panel_monthly_avg.csv", "panel_monthly_avg_post.csv" if with_post else None)
    df = df.drop_duplicates(["app_id", "month"], keep="first")          # frozen data wins over later pulls
    w = df.pivot(index="month", columns="app_id", values="avg_players").astype(float)
    w.index = pd.PeriodIndex(w.index, freq="M"); w = w.sort_index()
    for col in w:                                                      # drop leading launch artefacts
        ok = np.where(w[col].values >= c["monthly"]["min_avg"])[0]
        w.iloc[: ok[0] if len(ok) else len(w), w.columns.get_loc(col)] = np.nan
    return np.log(w)

def load_daily(c, with_post=False):
    """Wide table of log daily peak players, full UTC days only. Index: date."""
    df = _read("panel_daily_peak.csv", "panel_daily_peak_post.csv" if with_post else None)
    df = df[df.partial_day == 0].drop_duplicates(["app_id", "date"], keep="first")
    w = df.pivot(index="date", columns="app_id", values="peak_players").astype(float)
    w.index = pd.to_datetime(w.index); w = w.sort_index()
    return np.log(w)

def chained_index(w, controls, c):
    """Chained index of the mean of the controls' period-over-period log changes (an equal-weight geometric
    index). `trim` > 0 would drop that many highest and lowest changes each period; it is 0 because chained
    trimming drifts when changes are skewed (see pre-registration, amendment 3)."""
    d = w[controls].diff().values
    step = np.zeros(len(w))
    for i in range(1, len(w)):
        v = np.sort(d[i][~np.isnan(d[i])])
        if len(v) == 0:
            continue
        k = c["index"]["trim"] if len(v) >= c["index"]["min_n_for_trim"] else len(v) // 6
        step[i] = v[k: len(v) - k].mean()
    return pd.Series(np.cumsum(step), index=w.index)

def build_targets(w, c):
    """{'raw': {unit: series}, 'adjusted': {unit: series}}. A unit is never in its own index."""
    roles, _ = roles_names()
    controls = [u for u in w.columns if roles[u] == "control"]
    out = {"raw": {}, "adjusted": {}}
    for u in w.columns:
        s = w[u].dropna()
        assert s.index.equals(w.loc[s.index[0]: s.index[-1]].index), f"gap in {u}"
        idx = chained_index(w, [k for k in controls if k != u], c)
        out["raw"][u] = s
        out["adjusted"][u] = (s - idx.loc[s.index])
    return out

def panel_units(w):
    """Units used to train the pooled neural model and as placebos: target + controls (no sibling)."""
    roles, _ = roles_names()
    return [u for u in w.columns if roles[u] in ("target", "control")]

def trends_daily():
    t = pd.read_csv(os.path.join(ROOT, "data", "trends_daily_2026-03_to_2026-11.csv"), parse_dates=["date"])
    return t.set_index("date")
