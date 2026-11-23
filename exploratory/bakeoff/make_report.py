"""Build REPORT.md from bake-off results, with the frozen backtest candidates side by side.

    python exploratory/bakeoff/make_report.py --results exploratory/bakeoff/results
"""
import argparse, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from exploratory.bakeoff import guards as G  # noqa: E402

G.install_audit_hook()

import numpy as np, pandas as pd                          # noqa: E402
from halo import data as D, backtest as B                 # noqa: E402
from exploratory.bakeoff import adapter as A, specs as S  # noqa: E402

FIRST = "Exploratory, run after the freeze on pre-launch data only. Does not change the pre-registered test or its verdict."
NAMES = {"naive": "seasonal naive", "clim": "climatology", "sarima": "SARIMA", "nn": "pooled MLP (frozen nn)", "ets": "ETS",
         "ets_damped": "ETS damped", "sarimax_trends": "SARIMAX + Trends", "nbeats": "N-BEATS", "nhits": "N-HiTS", "gru": "GRU",
         "lstm": "LSTM", "patchtst": "PatchTST", "tft": "TFT"}
METRIC = {"monthly": "MAE, h = 2, all 107 origins", "daily": "MAE of days 4-17 window mean, 30 origins"}


def f4(x):
    return "" if x is None or not np.isfinite(x) else f"{x:.4f}"


def monthly_extras(bt):
    e = bt[bt.h == 2].dropna(subset=["err"])
    dec = e[e.origin.str.endswith("-10")]
    hold = e[e.origin >= "2024-09"]
    return (float(np.sqrt((dec.err ** 2).mean())) if len(dec) else np.nan, len(dec),
            float(hold.err.abs().mean()) if len(hold) else np.nan, len(hold))


def load_new(res_dir, res):
    out = {}
    for m in S.MODELS:
        p = os.path.join(res_dir, res, f"{m}_errors.csv")
        if os.path.exists(p):
            df = pd.read_csv(p, dtype={"unit": str, "origin": str, "target": str}, float_precision="round_trip")
            meta_p = os.path.join(res_dir, res, f"{m}_meta.json")
            out[m] = (df, json.load(open(meta_p)) if os.path.exists(meta_p) else {})
    return out


def section(res, c, sel, new, lines, verdicts):
    frozen = pd.read_csv(os.path.join(ROOT, "outputs", "backtest", f"{res}_errors.csv"),
                         dtype={"unit": str, "origin": str, "target": str}, float_precision="round_trip")
    order = c["selection"][f"{res}_order"]; margin = c["selection"]["margin"]
    key = "monthly_mae_h2_all_origins" if res == "monthly" else "daily_mae_window"
    lines += [f"## {res.capitalize()}", ""]
    for typ in ("raw", "adjusted"):
        fz = frozen[(frozen.unit == D.TARGET) & (frozen.type == typ)]
        mae_f, n_f = A.selection_metric(fz, res, c), A.selection_n(fz, res, c)
        for k, v in mae_f.items():
            assert abs(v - sel["tables"][typ][key][k]) < 1e-12, f"frozen {res}/{typ}/{k} does not reproduce selection.json"
        winner = sel[res][typ]
        assert B.select(mae_f, order, margin) == winner
        w_mae, w_n = mae_f[winner], n_f[winner]
        rows = []
        for k in sorted(mae_f, key=mae_f.get):
            ex = monthly_extras(fz[fz.model == k]) if res == "monthly" else None
            elig = "frozen candidate" if k in order else "frozen, not eligible (uses Trends)"
            rows.append(dict(model=k, kind=elig, config="", mae=mae_f[k], n=n_f[k], ex=ex,
                             ratio=mae_f[k] / w_mae, verdict="**frozen winner**" if k == winner else ""))
        new_mae = {}
        for m, (df, meta) in new.items():
            d = df[df.type == typ]
            mae, n = A.selection_metric(d, res, c).get(m, np.nan), A.selection_n(d, res, c).get(m, 0)
            ratio = mae / w_mae
            if n < w_n:
                v = f"incomplete ({n} of {w_n} origins)"
            elif B.select({**mae_f, m: mae}, order + [m], margin) == m:
                v = "**beats**"
            elif ratio < 1:
                v = "better, but not by 5%"
            else:
                v = "does not beat"
            if n >= w_n and abs(ratio - (1 - margin)) < 0.005:
                v += " (borderline)"
            if n >= w_n:
                new_mae[m] = mae
            t = meta.get("types", {}).get(typ, {})
            ps = [x for x in t.get("per_seed_mae", {}).values() if x is not None]
            rows.append(dict(model=m, kind="new", config=t.get("config", ""), mae=mae, n=n,
                             ex=monthly_extras(d) if res == "monthly" else None, ratio=ratio, verdict=v,
                             seeds=f"{min(ps):.4f}-{max(ps):.4f}" if ps else ""))
            verdicts.append(dict(res=res, typ=typ, model=m, mae=mae, ratio=ratio, verdict=v, winner=winner, w_mae=w_mae))
        rows.sort(key=lambda r: (np.inf if not np.isfinite(r["mae"]) else r["mae"]))
        lines += [f"### {typ.capitalize()} target", "",
                  f"Frozen winner: **{NAMES[winner]}** (`{winner}`), {METRIC[res]} {w_mae:.4f}. "
                  f"A new model beats it if its error is below {(1 - margin) * w_mae:.4f}.", ""]
        if res == "monthly":
            lines += ["| model | type | config | MAE all origins | vs winner | Dec-only RMSE (9) | MAE 2024-09 to 2026-08 (24) | seed range | verdict |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for r in rows:
                dec, nd, hold, nh = r["ex"]
                lines.append(f"| {NAMES.get(r['model'], r['model'])} | {r['kind']} | {r['config']} | {f4(r['mae'])} | {r['ratio']:.3f} | "
                             f"{f4(dec)} | {f4(hold)} | {r.get('seeds', '')} | {r['verdict']} |")
        else:
            lines += ["| model | type | config | window MAE | vs winner | seed range | verdict |", "|---|---|---|---|---|---|---|"]
            for r in rows:
                lines.append(f"| {NAMES.get(r['model'], r['model'])} | {r['kind']} | {r['config']} | {f4(r['mae'])} | {r['ratio']:.3f} | "
                             f"{r.get('seeds', '')} | {r['verdict']} |")
        allin_order = order + [m for m in S.MODELS if m in new_mae]
        allin = B.select({**{k: v for k, v in mae_f.items() if k in order}, **new_mae}, allin_order, margin)
        lines += ["", f"All-in selection (frozen order, then {', '.join(NAMES[m] for m in allin_order[len(order):]) or 'no complete new models'}): "
                  f"**{NAMES[allin]}** (`{allin}`).", ""]
        if res == "monthly" and new:
            years = sorted(o for o in fz.origin.unique() if o.endswith("-10"))
            hdr = [winner] + [m for m in new]
            lines += [f"December-only errors (forecast from October, log points; actual minus forecast is the negative of these):", "",
                      "| year | " + " | ".join(NAMES[m] for m in hdr) + " |", "|---|" + "---|" * len(hdr)]
            for o in years:
                cells = []
                for m in hdr:
                    src = fz[fz.model == m] if m == winner else new[m][0][new[m][0].type == typ]
                    e = src[(src.origin == o) & (src.h == 2)].err
                    cells.append(f"{e.iloc[0]:+.3f}" if len(e) and np.isfinite(e.iloc[0]) else "")
                lines.append(f"| {int(o[:4]) } | " + " | ".join(cells) + " |")
            lines.append("")
        if res == "monthly" and new:
            lines += ["Config choice (tuned on the 18 controls, origins 2017-10 to 2024-08; GTA V not used):", "",
                      "| model | A | B | C | chosen |", "|---|---|---|---|---|"]
            for m, (_, meta) in new.items():
                t = meta.get("types", {}).get(typ, {}); sc = t.get("tuning_scores", {})
                lines.append(f"| {NAMES[m]} | {f4(sc.get('A'))} | {f4(sc.get('B'))} | {f4(sc.get('C'))} | {t.get('config', '')} |")
            lines.append("")


def run_times(res_dir, lines):
    p = os.path.join(res_dir, "run_log.csv")
    lines += ["## Run times", ""]
    if not os.path.exists(p):
        lines += ["No run log found.", ""]; return
    rl = pd.read_csv(p)
    g = rl.groupby(["resolution", "model"]).agg(fits=("fit_seconds", "size"), fit_min=("fit_seconds", lambda s: s.sum() / 60),
                                                   mean_fit_s=("fit_seconds", "mean"), device=("device", "first")).reset_index()
    lines += ["Counted from the per-fit log (a fit restored from cache after a disconnect keeps its original time).", "",
              "| resolution | model | fits | total fit time, min | mean per fit, s | device |", "|---|---|---|---|---|---|"]
    for _, r in g.iterrows():
        lines.append(f"| {r.resolution} | {NAMES.get(r.model, r.model)} | {r.fits} | {r.fit_min:.1f} | {r.mean_fit_s:.1f} | {r.device} |")
    lines += ["", f"Total: {rl.fit_seconds.sum() / 3600:.2f} GPU/CPU-hours of fitting over {len(rl)} fits.", ""]


def conclusion(verdicts, missing):
    out = ["## Conclusion", ""]
    if not verdicts:
        return out + ["No bake-off results were found.", ""]
    for (res, typ), grp in pd.DataFrame(verdicts).groupby(["res", "typ"], sort=False):
        w = grp.winner.iloc[0]; inc = grp[grp.verdict.str.startswith("incomplete")]
        grp = grp[~grp.verdict.str.startswith("incomplete")]
        if inc.size:
            out.append(f"- **{res}, {typ}:** incomplete, so not scored: {', '.join(NAMES[m] for m in inc.model)}.")
        if grp.empty:
            continue
        wins = grp[grp.verdict.str.startswith("**beats")]
        best = grp.sort_values("mae").iloc[0]
        if len(wins):
            names = ", ".join(f"{NAMES[r.model]} ({r.mae:.4f}, {100 * (1 - r.ratio):.0f}% lower)" for r in wins.itertuples())
            out.append(f"- **{res}, {typ}:** {names} would have been selected over the frozen {NAMES[w]} ({best.w_mae:.4f}) under the 5% rule.")
        elif best.ratio < 1:
            out.append(f"- **{res}, {typ}:** no deep model clears the 5% margin over the frozen {NAMES[w]} ({best.w_mae:.4f}). "
                       f"The closest, {NAMES[best.model]} ({best.mae:.4f}), is {100 * (1 - best.ratio):.1f}% lower, short of 5%.")
        else:
            out.append(f"- **{res}, {typ}:** no deep model beats the frozen {NAMES[w]} ({best.w_mae:.4f}); "
                       f"the best, {NAMES[best.model]}, is {100 * (best.ratio - 1):.1f}% worse.")
    if missing:
        out.append(f"- Not run or not finished: {', '.join(missing)}.")
    out += ["", "In plain terms: the frozen models were chosen by a fixed rule before launch, and that choice stands. "
            "This bake-off only asks whether heavier models would have changed that choice on the same backtests. "
            "Either answer leaves the pre-registered forecasts, intervals and verdict exactly as frozen. "
            "The daily backtest has about three independent windows and the December-only column nine years, so "
            "small differences there are noise.", ""]
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", default=os.path.join(HERE, "results"))
    p.add_argument("--out", default=None, help="default: REPORT.md next to the results folder")
    a = p.parse_args()
    a.out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.results.rstrip("/\\"))), "REPORT.md")
    G.verify_inputs()
    c = D.cfg(); sel = json.load(open(os.path.join(ROOT, "outputs", "backtest", "selection.json")))
    lines = [FIRST, "", "# Bake-off report: deep forecasting models vs the frozen backtest winners", ""]
    metas = [json.load(open(m)) for m in glob.glob(os.path.join(a.results, "*", "*_meta.json"))]
    if any(m.get("smoke") for m in metas):
        lines += ["> **SMOKE-TEST OUTPUT, NOT A REAL RUN.** One origin, one seed, a few training steps. Ignore every number below.", ""]
    envs = {json.dumps(m.get("env", {}), sort_keys=True) for m in metas}
    lines += ["Plan: `exploratory/bakeoff/PLAN.md` (committed before any result). Errors are in log points (0.10 is about 10%). "
              "Frozen numbers are recomputed from `outputs/backtest/` and checked against `selection.json`.", ""]
    for res in ("monthly", "daily"):
        gp = os.path.join(a.results, res, "gate.json")
        if os.path.exists(gp):
            g = json.load(open(gp))
            lines.append(f"- {res}: input hash check passed ({g['hash_check']['files']} files); seasonal naive through the adapter reproduced "
                         f"the frozen backtest exactly (raw {g['naive_gate']['raw']['rows']} rows, adjusted {g['naive_gate']['adjusted']['rows']} rows).")
    for e in envs:
        e = json.loads(e)
        if e:
            lines.append(f"- environment: {e.get('gpu', 'cpu')}; python {e.get('python')}, torch {e.get('torch')}, "
                         f"neuralforecast {e.get('neuralforecast')}, pandas {e.get('pandas')}, numpy {e.get('numpy')}")
    lines.append("")
    verdicts, missing = [], []
    for res in ("monthly", "daily"):
        new = load_new(a.results, res)
        missing += [f"{res}/{m}" for m in S.MODELS if m not in new]
        if new:
            section(res, c, sel, new, lines, verdicts)
    run_times(a.results, lines)
    lines += conclusion(verdicts, missing)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
