"""Fit the selected models once on data up to the freeze origin and write the frozen forecast.
Run:  python -m halo.freeze            (refuses to overwrite an existing freeze)
      python -m halo.freeze --version v2   (a new, separately hashed freeze; only valid before launch)"""
import argparse, hashlib, json, os, platform, sys
from datetime import datetime, timezone
import numpy as np, pandas as pd
from scipy import stats
from . import data as D, models as M

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", default="v1"); a = ap.parse_args()
    out = os.path.join(D.ROOT, "outputs", "frozen", a.version)
    if os.path.exists(os.path.join(out, "MANIFEST.json")):
        sys.exit(f"{out} is already frozen. Frozen forecasts are never overwritten; use --version for a new one.")
    os.makedirs(out, exist_ok=True)
    c = D.cfg(); bt = os.path.join(D.ROOT, "outputs", "backtest")
    sel = json.load(open(f"{bt}/selection.json")); rm = pd.read_csv(f"{bt}/unit_rmse.csv", dtype={"unit": str})
    hr = pd.read_csv(f"{bt}/daily_rmse_by_horizon.csv", dtype={"unit": str})
    assert all(t["passed"] for t in sel["leakage_tests"]), "leakage tests did not pass"
    wm, wd = D.load_monthly(c), D.load_daily(c)
    fo, mo, fz = pd.Timestamp(c["freeze"]["daily_origin"]), pd.Period(c["freeze"]["monthly_origin"], "M"), c["freeze"]
    assert wd.index[-1] == fo and wm.index[-1] == mo, "input data must end exactly at the freeze origin"
    tm, td = D.build_targets(wm, c), D.build_targets(wd, c)
    units = D.panel_units(wm) + [D.SIBLING]; H = c["daily"]["horizon"]
    days = pd.date_range(fo + pd.Timedelta(days=1), fz["end"], freq="D"); dec = pd.Period("2026-12", "M")
    q = {80: 0.90, 90: 0.95, 95: 0.975}; orows, drows = [], []
    for typ in ("raw", "adjusted"):
        mname, dname = sel["monthly"][typ], sel["daily"][typ]
        train_m = [tm[typ][u] for u in D.panel_units(wm)]; train_d = [td[typ][u] for u in D.panel_units(wm)]
        mnn = M.fit_panel_nn(train_m, c, "monthly") if mname == "nn" else None
        dnn = M.fit_panel_nn(train_d, c, "daily") if dname == "nn" else None
        for u in units:
            sm, sd = tm[typ][u], td[typ][u]
            assert sm.index[-1] == mo and sd.index[-1] == fo                               # nothing after the origin
            fm = M.nn_predict(mnn, sm, c, "monthly") if mname == "nn" else M.MONTHLY[mname](sm.values, 2)
            fd = M.nn_predict(dnn, sd, c, "daily") if dname == "nn" else M.DAILY[dname](sd.values, H)
            r = rm[(rm.type == typ) & (rm.unit == u)].iloc[0]
            # O2: December monthly average (log level on this unit's series)
            row = dict(unit=u, type=typ, outcome="O2", period="2026-12", base_oct=sm.values[-1], point=fm[1], rmse=r.rmse_o2, df=int(r.n_o2) - 1, n_backtest=int(r.n_o2), model=mname)
            for lv, p in q.items():
                k = stats.t.ppf(p, row["df"]) * r.rmse_o2; row[f"lo{lv}"], row[f"hi{lv}"] = fm[1] - k, fm[1] + k
            orows.append(row)
            # O1: mean log daily peak over the launch fortnight
            p1 = fd[c["daily"]["win_from"] - 1: c["daily"]["win_to"]].mean()
            row = dict(unit=u, type=typ, outcome="O1", period=f"{fz['launch']}..{fz['o1_end']}", base_oct=np.nan, point=p1, rmse=r.rmse_o1, df=2, n_backtest=int(r.n_o1), model=dname)
            for lv, p in q.items():
                k = stats.t.ppf(p, 2) * r.rmse_o1; row[f"lo{lv}"], row[f"hi{lv}"] = p1 - k, p1 + k
            orows.append(row)
            # day-by-day path (descriptive)
            hru = hr[(hr.type == typ) & (hr.unit == u) & (hr.model == dname)].set_index("h").rmse
            dow = M.dow_effects(sd); p_oct = sd.loc["2026-10-01":"2026-10-31"].mean(); delta = fm[1] - sm.values[-1]
            for i, d in enumerate(days):
                h = i + 1
                if h <= H:
                    f, s, src = fd[h - 1], float(hru.get(h, np.nan)), "daily_model"
                    z = {lv: stats.norm.ppf(p) for lv, p in q.items()}
                else:
                    f, s, src = p_oct + delta + dow[d.dayofweek], float(np.sqrt(r.rmse_o2 ** 2 + hru.get(H, 0.0) ** 2)), "october_level_plus_monthly_change"
                    z = {lv: stats.t.ppf(p, int(r.n_o2) - 1) for lv, p in q.items()}
                row = dict(unit=u, type=typ, date=d.date().isoformat(), h=h, forecast_log=f, band_sd=s, source=src)
                for lv in q: row[f"lo{lv}"], row[f"hi{lv}"] = f - z[lv] * s, f + z[lv] * s
                drows.append(row)
    # declared sensitivity (pre-registration, amendment 2): December with seasonal climatology where it was not the selected model
    bm = pd.read_csv(f"{bt}/monthly_errors.csv", dtype={"unit": str})
    for typ in ("raw", "adjusted"):
        if sel["monthly"][typ] == "clim": continue
        sm = tm[typ][D.TARGET]; fm = M.m_clim(sm.values, 2)
        e = bm[(bm.type == typ) & (bm.unit == D.TARGET) & (bm.model == "clim") & (bm.h == 2) & bm.origin.str.endswith("-10")].err.dropna().values
        rmse = float(np.sqrt((e ** 2).mean()))
        row = dict(unit=D.TARGET, type=typ, outcome="O2_sensitivity_clim", period="2026-12", base_oct=sm.values[-1], point=fm[1], rmse=rmse, df=len(e) - 1, n_backtest=len(e), model="clim")
        for lv, p in q.items():
            k = stats.t.ppf(p, len(e) - 1) * rmse; row[f"lo{lv}"], row[f"hi{lv}"] = fm[1] - k, fm[1] + k
        orows.append(row)
    pd.DataFrame(orows).to_csv(f"{out}/frozen_outcomes.csv", index=False, float_format="%.6f")
    pd.DataFrame(drows).to_csv(f"{out}/frozen_daily.csv", index=False, float_format="%.6f")
    inputs = ["config.yaml", "docs/PREREGISTRATION.md", "data/panel_monthly_avg.csv", "data/panel_daily_peak.csv",
              "outputs/backtest/selection.json", "outputs/backtest/monthly_errors.csv", "outputs/backtest/unit_rmse.csv", "outputs/backtest/daily_rmse_by_horizon.csv"]
    inputs += sorted(f"halo/{f}" for f in os.listdir(os.path.join(D.ROOT, "halo")) if f.endswith(".py"))
    import torch, statsmodels
    man = dict(version=a.version, created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               daily_origin=fz["daily_origin"], monthly_origin=fz["monthly_origin"], launch=fz["launch"],
               selected_models={"monthly": sel["monthly"], "daily": sel["daily"]},
               frozen_files={f: sha(f"{out}/{f}") for f in ("frozen_outcomes.csv", "frozen_daily.csv")},
               inputs={f: sha(os.path.join(D.ROOT, f)) for f in inputs},
               environment=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, statsmodels=statsmodels.__version__, torch=torch.__version__),
               note="The frozen CSVs are the record. Re-running on other hardware may differ in late decimals for neural models.")
    json.dump(man, open(f"{out}/MANIFEST.json", "w"), indent=1)
    print("frozen ->", out); print("MANIFEST sha256:", sha(f"{out}/MANIFEST.json"))

if __name__ == "__main__":
    main()
