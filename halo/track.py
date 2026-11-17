"""Post-launch scoring against the frozen forecast. Never refits anything.
Put new data in data/post/ (same columns as the frozen panel files), then run:  python -m halo.track"""
import argparse, json, os, sys
import numpy as np, pandas as pd
from . import data as D
from .freeze import sha

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", default="v1"); a = ap.parse_args()
    fr = os.path.join(D.ROOT, "outputs", "frozen", a.version); out = os.path.join(D.ROOT, "outputs", "tracker"); os.makedirs(out, exist_ok=True)
    man = json.load(open(f"{fr}/MANIFEST.json"))
    for f, h in man["frozen_files"].items():
        if sha(f"{fr}/{f}") != h: sys.exit(f"{f} does not match the hash in MANIFEST.json. The frozen forecast was altered; stopping.")
    for f in ("data/panel_monthly_avg.csv", "data/panel_daily_peak.csv"):
        if sha(os.path.join(D.ROOT, f)) != man["inputs"][f]: sys.exit(f"{f} changed since the freeze; stopping. New data belongs in data/post/.")
    c = D.cfg(); fz = c["freeze"]; roles, names = D.roles_names()
    wm, wd = D.load_monthly(c, with_post=True), D.load_daily(c, with_post=True)
    tm, td = D.build_targets(wm, c), D.build_targets(wd, c)
    fo = pd.read_csv(f"{fr}/frozen_outcomes.csv", dtype={"unit": str}); fd = pd.read_csv(f"{fr}/frozen_daily.csv", dtype={"unit": str}, parse_dates=["date"])
    # day-by-day gaps
    rows = []
    for (u, typ), g in fd.groupby(["unit", "type"]):
        s = td[typ][u]
        for r in g.itertuples():
            if r.date in s.index:
                act = float(s.loc[r.date]); rows.append((u, names[u], roles[u], typ, r.date.date().isoformat(), r.forecast_log, act, act - r.forecast_log, r.lo90, r.hi90, r.source))
    dg = pd.DataFrame(rows, columns=["unit", "name", "role", "type", "date", "forecast_log", "actual_log", "gap_log", "lo90", "hi90", "source"])
    dg.to_csv(f"{out}/daily_gaps.csv", index=False, float_format="%.6f")
    # outcomes
    win = pd.date_range(fz["launch"], fz["o1_end"], freq="D"); dec = pd.Period("2026-12", "M"); ev = []
    for r in fo.itertuples():
        if r.outcome == "O1":
            s = td[r.type][r.unit]; act = float(s.reindex(win).mean()) if s.reindex(win).notna().all() else np.nan
        else:
            s = tm[r.type][r.unit]; act = float(s.loc[dec]) if dec in s.index else np.nan
        gap = act - r.point
        ev.append(dict(unit=r.unit, name=names[r.unit], role=roles[r.unit], type=r.type, outcome=r.outcome, point=r.point, actual=act, gap_log=gap,
                       gap_pct=100 * (np.exp(gap) - 1), z=gap / r.rmse, lo90=r.lo90, hi90=r.hi90, outside90=bool(act < r.lo90 or act > r.hi90) if np.isfinite(act) else None))
    ev = pd.DataFrame(ev)
    for col, v in (("placebo_rank", np.nan), ("placebo_n", np.nan), ("placebo_p", np.nan), ("verdict", "")): ev[col] = v
    ev["verdict"] = ev["verdict"].astype(object)
    for (typ, oc), g in ev.groupby(["type", "outcome"]):
        pool = g[g.role.isin(["target", "control"]) & g.z.notna()]
        if D.TARGET not in pool.unit.values: continue
        t = ev.index[(ev.type == typ) & (ev.outcome == oc) & (ev.unit == D.TARGET)][0]
        if len(pool) < 10:                                   # sensitivity rows have no placebo pool
            ev.loc[t, "verdict"] = "sensitivity: " + ("outside 90% interval" if ev.loc[t, "outside90"] else "inside 90% interval"); continue
        rank = int((pool.z.abs() >= abs(pool[pool.unit == D.TARGET].z.iloc[0])).sum()); n = len(pool)
        most, outside = rank == 1, bool(ev.loc[t, "outside90"])
        ev.loc[t, ["placebo_rank", "placebo_n", "placebo_p", "verdict"]] = [rank, n, rank / n, "Detected" if most and outside else "Suggestive" if most or outside else "Not detected"]
    ev.to_csv(f"{out}/outcomes_eval.csv", index=False, float_format="%.6f")
    g = ev[ev.unit == D.TARGET]
    print(f"days scored: {dg[(dg.unit == D.TARGET) & (dg.type == 'raw')].shape[0]}  (last: {dg.date.max() if len(dg) else 'none'})")
    print(g[[c_ for c_ in ("type", "outcome", "gap_pct", "z", "outside90", "placebo_rank", "placebo_n", "verdict") if c_ in g]].to_string(index=False))
    from . import report; report.export_dashboard()

if __name__ == "__main__":
    main()
