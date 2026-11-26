"""Exploratory, post-hoc: the frozen daily O1 method applied separately to GTA V Legacy and Enhanced.
Run:  python exploratory/per_app/forecast_per_app.py

Made after launch. Uses only pre-launch data (full UTC days up to the freeze origin, 2026-11-15) from
outputs/dashboard/players_daily.csv, the per-app split of the series the freeze used. Never reads data/post/.
Model, backtest harness and window errors are imported from halo; the interval arithmetic mirrors
halo/freeze.py (which has it inline, not as a function). Raw scale (log daily peak) only: the adjusted
series is an index and does not add across apps. Not part of the pre-registered test.
"""
import os, sys
import numpy as np, pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from halo import data as D, models as M                                      # noqa: E402
from halo.backtest import daily_backtest, window_errors, select               # noqa: E402

APPS = {"legacy": ("271590", "legacy_peak"), "enhanced": ("3240220", "enhanced_peak")}
Q = {80: 0.90, 95: 0.975}


def load_apps(c):
    """Log daily peak per app, full days only, ending exactly at the freeze origin."""
    df = pd.read_csv(os.path.join(ROOT, "outputs", "dashboard", "players_daily.csv"), parse_dates=["date"])
    df = df[(df.partial_day == 0) & (df.date <= c["freeze"]["daily_origin"])].set_index("date").sort_index()
    out = {}
    for app, (_, col) in {**APPS, "combined": (None, "combined_peak")}.items():
        s = np.log(df[col].astype(float))
        assert s.index.equals(pd.date_range(s.index[0], s.index[-1], freq="D")), f"gap in {app}"
        assert s.index[-1] == pd.Timestamp(c["freeze"]["daily_origin"])
        out[app] = s
    return out


def main():
    c = D.cfg(); H = c["daily"]["horizon"]; fo = pd.Timestamp(c["freeze"]["daily_origin"])
    sel = __import__("json").load(open(os.path.join(ROOT, "outputs", "backtest", "selection.json")))
    model = sel["daily"]["raw"]; assert model in M.DAILY, model                 # frozen raw daily model (naive)
    tg = load_apps(c)
    bt = daily_backtest(tg, list(tg), [model], c)                               # same 30 origins as the freeze (config)
    assert bt.origin.nunique() == 30 and bt.origin.min() == c["daily"]["bt_first"] and bt.origin.max() == c["daily"]["bt_last"]
    hr = bt.dropna().groupby(["unit", "h"]).err.agg(lambda e: np.sqrt((e ** 2).mean()))
    we = window_errors(bt, c)
    days = pd.date_range(fo + pd.Timedelta(days=1), periods=H, freq="D")
    z = {lv: stats.norm.ppf(p) for lv, p in Q.items()}
    rows, summ, logs = [], [], {}
    for app in tg:
        s = tg[app]; f = M.DAILY[model](s.values, H); logs[app] = f
        e = we[we.unit == app].err.values; rmse_o1 = float(np.sqrt((e ** 2).mean()))
        p1 = f[c["daily"]["win_from"] - 1: c["daily"]["win_to"]].mean(); k = stats.t.ppf(0.975, 2) * rmse_o1
        eh = hr.loc[app]
        summ.append(dict(app=app, model=model, n_origins=int(bt[bt.unit == app].origin.nunique()), n_windows=len(e),
                         o1_window_mae=float(np.abs(e).mean()), o1_window_rmse=rmse_o1, o1_window_bias=float(e.mean()),
                         rmse_h1=float(eh.loc[1]), rmse_h7=float(eh.loc[7]), rmse_h14=float(eh.loc[14]), rmse_h17=float(eh.loc[17]),
                         o1_point_players=round(float(np.exp(p1))), o1_lo95_players=round(float(np.exp(p1 - k))), o1_hi95_players=round(float(np.exp(p1 + k)))))
        if app == "combined": continue
        for i, d in enumerate(days):
            sd = float(eh.loc[i + 1])
            rows.append(dict(date=d.date().isoformat(), app=app, forecast=round(float(np.exp(f[i]))),
                             **{f"{b}{lv}": round(float(np.exp(f[i] + sg * z[lv] * sd))) for lv in Q for b, sg in (("lo", -1), ("hi", 1))}))
    out = pd.DataFrame(rows)[["date", "app", "forecast", "lo80", "hi80", "lo95", "hi95"]]
    out.to_csv(os.path.join(ROOT, "outputs", "dashboard", "per_app_forecast.csv"), index=False)
    pd.DataFrame(summ).to_csv(os.path.join(HERE, "backtest_summary.csv"), index=False, float_format="%.6f")

    # sanity check against the frozen combined forecast (raw, GTA V)
    fr = pd.read_csv(os.path.join(ROOT, "outputs", "frozen", "v1", "frozen_daily.csv"), dtype={"unit": str})
    fr = fr[(fr.unit == D.TARGET) & (fr.type == "raw")].set_index("date").forecast_log
    chk = pd.DataFrame({"date": [d.date().isoformat() for d in days],
                        "legacy": np.exp(logs["legacy"]), "enhanced": np.exp(logs["enhanced"]),
                        "frozen_combined": np.exp(fr.loc[[d.date().isoformat() for d in days]].values),
                        "recomputed_combined": np.exp(logs["combined"])})
    chk["sum"] = chk.legacy + chk.enhanced; chk["diff"] = chk["sum"] - chk.frozen_combined; chk["diff_pct"] = 100 * chk["diff"] / chk.frozen_combined
    pd.set_option("display.width", 200)
    print(chk.round(1).to_string(index=False))
    print(f"max |sum - frozen| = {chk['diff'].abs().max():.1f} players ({chk.diff_pct.abs().max():.4f}%)")
    print("recomputed combined matches frozen:", bool(np.allclose(logs["combined"], fr.loc[[d.date().isoformat() for d in days]].values, atol=1e-5)))
    frz = pd.read_csv(os.path.join(ROOT, "outputs", "frozen", "v1", "frozen_daily.csv"), dtype={"unit": str})
    frz = frz[(frz.unit == D.TARGET) & (frz.type == "raw")].band_sd.values[:H]
    print("recomputed combined band_sd matches frozen:", bool(np.allclose(hr.loc["combined"].values, frz, atol=1e-5)))


if __name__ == "__main__":
    main()
