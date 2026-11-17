"""Rolling-origin backtests, model selection and leakage tests.
Run:  python -m halo.backtest
Pass 1 scores every candidate on GTA V. Pass 2 runs only the selected model on every unit
(needed for the placebo test). Selection never looks at anything after the freeze origin."""
import json, os, sys, time
import numpy as np, pandas as pd
from . import data as D, models as M

OUT = os.path.join(D.ROOT, "outputs", "backtest")

# ------------------------------------------------------------------ harnesses
def monthly_backtest(tg, units_eval, model_names, c, origins=None):
    H = c["monthly"]["horizon"]; train_units = [u for u in tg if u != D.SIBLING]
    origins = origins if origins is not None else pd.period_range(c["monthly"]["backtest_start"], c["monthly"]["backtest_end"], freq="M")
    rows = []
    for o in origins:
        cut = {u: tg[u].loc[:o] for u in tg}
        assert all(len(s) == 0 or s.index[-1] <= o for s in cut.values())          # leakage guard
        nn = M.fit_panel_nn([cut[u] for u in train_units if len(cut[u])], c, "monthly") if "nn" in model_names else None
        for u in units_eval:
            s = cut[u]
            if len(s) < 14 or s.index[-1] != o:
                continue
            for name in model_names:
                f = M.nn_predict(nn, s, c, "monthly") if name == "nn" else M.MONTHLY[name](s.values, H)
                for h in range(1, H + 1):
                    a = tg[u].get(o + h, np.nan)
                    rows.append((u, name, str(o), h, str(o + h), f[h - 1], a, f[h - 1] - a))
    return pd.DataFrame(rows, columns=["unit", "model", "origin", "h", "target", "fc", "actual", "err"])

def daily_backtest(tg, units_eval, model_names, c, origins=None, trends=None):
    H = c["daily"]["horizon"]; train_units = [u for u in tg if u != D.SIBLING]
    origins = origins if origins is not None else pd.date_range(c["daily"]["bt_first"], c["daily"]["bt_last"], freq="D")
    rows = []
    for o in origins:
        cut = {u: tg[u].loc[:o] for u in tg}
        assert all(s.index[-1] <= o for s in cut.values())                          # leakage guard
        nn = M.fit_panel_nn([cut[u] for u in train_units], c, "daily") if "nn" in model_names else None
        for u in units_eval:
            s = cut[u]
            for name in model_names:
                if name == "nn":
                    f = M.nn_predict(nn, s, c, "daily")
                elif name == "sarimax_trends":
                    if u != D.TARGET: continue
                    x = np.log1p(trends["gta5_interest"].reindex(s.index).astype(float).values).reshape(-1, 1)
                    f = M.d_sarimax_trends(s.values, H, x)
                else:
                    f = M.DAILY[name](s.values, H)
                for h in range(1, H + 1):
                    a = tg[u].get(o + pd.Timedelta(days=h), np.nan)
                    rows.append((u, name, o.date().isoformat(), h, f[h - 1], a, f[h - 1] - a))
    return pd.DataFrame(rows, columns=["unit", "model", "origin", "h", "fc", "actual", "err"])

def window_errors(bt, c):
    """Error of the outcome-window mean (days origin+win_from .. origin+win_to)."""
    w = bt[(bt.h >= c["daily"]["win_from"]) & (bt.h <= c["daily"]["win_to"])]
    g = w.groupby(["unit", "model", "origin"]).agg(fc=("fc", "mean"), actual=("actual", "mean"), n=("actual", "count")).reset_index()
    g = g[g.n == c["daily"]["win_to"] - c["daily"]["win_from"] + 1]
    g["err"] = g.fc - g.actual
    return g

def select(mae, order, margin):
    """Simplest model wins unless a more complex one is better by `margin`."""
    best = None
    for name in order:
        if name in mae and np.isfinite(mae[name]) and (best is None or mae[name] < (1 - margin) * mae[best]):
            best = name
    return best

# ------------------------------------------------------------------ leakage tests
def leakage_tests(c):
    """Corrupt everything after an origin and confirm no forecast for that origin changes."""
    res = []
    for kind, loader, origin in (("monthly", D.load_monthly, pd.Period("2023-10", "M")), ("daily", D.load_daily, pd.Timestamp("2026-10-15"))):
        w = loader(c); w2 = w.copy(); fut = w2.index > origin
        # unit-specific noise (sd 3 log points), so adjusted series are corrupted too, not just shifted together
        w2.loc[fut] += np.random.default_rng(c["seed"]).normal(0, 3.0, size=w2.loc[fut].shape)
        t1, t2 = D.build_targets(w, c), D.build_targets(w2, c)
        for typ in ("raw", "adjusted"):
            same_hist = all(np.allclose(t1[typ][u].loc[:origin], t2[typ][u].loc[:origin]) for u in t1[typ])
            res.append((f"{kind}/{typ}: history up to origin unchanged when the future is corrupted (index is causal)", bool(same_hist)))
            if kind == "monthly":
                a = monthly_backtest(t1[typ], [D.TARGET, "730"], list(M.MONTHLY) + ["nn"], c, origins=[origin])
                b = monthly_backtest(t2[typ], [D.TARGET, "730"], list(M.MONTHLY) + ["nn"], c, origins=[origin])
            else:
                tr = D.trends_daily()
                a = daily_backtest(t1[typ], [D.TARGET, "730"], list(M.DAILY) + ["nn", "sarimax_trends"], c, origins=[origin], trends=tr)
                b = daily_backtest(t2[typ], [D.TARGET, "730"], list(M.DAILY) + ["nn", "sarimax_trends"], c, origins=[origin], trends=tr)
            res.append((f"{kind}/{typ}: forecasts of all models identical when the future is corrupted", bool(np.allclose(a.fc, b.fc, equal_nan=True))))
            res.append((f"{kind}/{typ}: the corrupted run did see different actuals (test has teeth)", bool(not np.allclose(a.actual.dropna(), b.actual.dropna()))))
    wm, wd = D.load_monthly(c), D.load_daily(c)
    res.append(("daily data ends on the freeze origin; partial day 2026-11-16 excluded", str(wd.index[-1].date()) == c["freeze"]["daily_origin"]))
    res.append(("monthly data ends on the freeze month", str(wm.index[-1]) == c["freeze"]["monthly_origin"]))
    res.append(("no data on or after launch day in any input", bool(wd.index[-1] < pd.Timestamp(c["freeze"]["launch"]))))
    res.append(("Trends model is not in the eligible list", "sarimax_trends" not in c["selection"]["daily_order"]))
    return res

# ------------------------------------------------------------------ main
def leakage_only():
    """Re-run just the leakage tests and store the result (the backtest numbers are untouched)."""
    c = D.cfg(); sel = json.load(open(f"{OUT}/selection.json")); leaks = leakage_tests(c)
    sel["leakage_tests"] = [{"check": k, "passed": v} for k, v in leaks]
    json.dump(sel, open(f"{OUT}/selection.json", "w"), indent=1)
    for k, v in leaks: print("PASS" if v else "FAIL", k)
    if not all(v for _, v in leaks): sys.exit("leakage test failed")

def main():
    if "--leakage-only" in sys.argv: return leakage_only()
    t0 = time.time(); c = D.cfg(); os.makedirs(OUT, exist_ok=True)
    wm, wd = D.load_monthly(c), D.load_daily(c)
    tm, td = D.build_targets(wm, c), D.build_targets(wd, c)
    units = D.panel_units(wm) + [D.SIBLING]; trends = D.trends_daily()
    sel = {"monthly": {}, "daily": {}, "tables": {}}; m_all, d_all = [], []
    for typ in ("raw", "adjusted"):
        # pass 1: every candidate on GTA V
        bm = monthly_backtest(tm[typ], [D.TARGET], list(M.MONTHLY) + ["nn"], c); bm["type"] = typ
        bd = daily_backtest(td[typ], [D.TARGET], list(M.DAILY) + ["nn", "sarimax_trends"], c, trends=trends); bd["type"] = typ
        mae_m = bm[bm.h == 2].dropna().groupby("model").err.apply(lambda e: e.abs().mean()).to_dict()
        mae_d = window_errors(bd, c).groupby("model").err.apply(lambda e: e.abs().mean()).to_dict()
        sel["monthly"][typ] = select(mae_m, c["selection"]["monthly_order"], c["selection"]["margin"])
        sel["daily"][typ] = select(mae_d, c["selection"]["daily_order"], c["selection"]["margin"])
        dec = bm[(bm.h == 2) & bm.origin.str.endswith("-10")].dropna().groupby("model").err.agg(lambda e: np.sqrt((e ** 2).mean())).to_dict()
        sel["tables"][typ] = {"monthly_mae_h2_all_origins": mae_m, "monthly_rmse_oct_to_dec": dec, "daily_mae_window": mae_d}
        print(f"[{typ}] monthly MAE(h=2): { {k: round(v, 4) for k, v in mae_m.items()} } -> {sel['monthly'][typ]}")
        print(f"[{typ}] daily window MAE: { {k: round(v, 4) for k, v in mae_d.items()} } -> {sel['daily'][typ]}   ({time.time() - t0:.0f}s)")
        # pass 2: selected model on every other unit (placebos + sibling)
        others = [u for u in units if u != D.TARGET]
        bm2 = monthly_backtest(tm[typ], others, [sel["monthly"][typ]], c); bm2["type"] = typ
        bd2 = daily_backtest(td[typ], others, [sel["daily"][typ]], c); bd2["type"] = typ
        m_all += [bm, bm2]; d_all += [bd, bd2]
        print(f"[{typ}] pass 2 done ({time.time() - t0:.0f}s)")
    bm, bd = pd.concat(m_all), pd.concat(d_all)
    bm.to_csv(f"{OUT}/monthly_errors.csv", index=False); bd.to_csv(f"{OUT}/daily_errors.csv", index=False)
    # per-unit error scales for the selected models
    rows = []
    for typ in ("raw", "adjusted"):
        m = bm[(bm.type == typ) & (bm.model == sel["monthly"][typ]) & (bm.h == 2) & bm.origin.str.endswith("-10")].dropna()
        w = window_errors(bd[(bd.type == typ) & (bd.model == sel["daily"][typ])], c)
        for u in units:
            e2, e1 = m[m.unit == u].err.values, w[w.unit == u].err.values
            rows.append((typ, u, np.sqrt((e2 ** 2).mean()) if len(e2) else np.nan, len(e2), np.sqrt((e1 ** 2).mean()) if len(e1) else np.nan, len(e1)))
    pd.DataFrame(rows, columns=["type", "unit", "rmse_o2", "n_o2", "rmse_o1", "n_o1"]).to_csv(f"{OUT}/unit_rmse.csv", index=False)
    hr = bd.dropna().groupby(["type", "unit", "model", "h"]).err.agg(lambda e: np.sqrt((e ** 2).mean())).rename("rmse").reset_index()
    hr.to_csv(f"{OUT}/daily_rmse_by_horizon.csv", index=False)
    leaks = leakage_tests(c)
    sel["leakage_tests"] = [{"check": k, "passed": v} for k, v in leaks]
    json.dump(sel, open(f"{OUT}/selection.json", "w"), indent=1)
    for k, v in leaks: print("PASS" if v else "FAIL", k)
    print(f"done in {time.time() - t0:.0f}s")
    if not all(v for _, v in leaks): sys.exit("leakage test failed")

if __name__ == "__main__":
    main()
