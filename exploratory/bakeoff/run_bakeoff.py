"""Exploratory bake-off: deep forecasting models vs the frozen backtest winners. See PLAN.md.

    python exploratory/bakeoff/run_bakeoff.py --resolution monthly --device cuda --out results/
    python exploratory/bakeoff/run_bakeoff.py --resolution daily --device cpu --smoke

Order of work: isolation guard + hash check -> seasonal-naive reproduction gate -> each model in turn.
Each fit's forecasts are cached under <out>/cache/ and each finished model is written to
<out>/<resolution>/<model>_errors.csv (same columns as outputs/backtest/<resolution>_errors.csv).
A model whose errors file exists is skipped, so a run can be restarted after a disconnect.
"""
import argparse, json, os, platform, sys, time
from datetime import datetime, timezone

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")   # deterministic cuBLAS; must precede any CUDA context
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from exploratory.bakeoff import guards as G  # noqa: E402  (stdlib only)

G.install_audit_hook()

import numpy as np, pandas as pd                        # noqa: E402  (imports read no data; the hash check runs first in main)
from halo import data as D, models as M                 # noqa: E402
from exploratory.bakeoff import adapter as A, specs as S  # noqa: E402

N = None                                                # exploratory.bakeoff.neural, imported after the checks

SMOKE_MODEL, SMOKE_STEPS = "nhits", 5


def log(*a):
    print(f"[{datetime.now().strftime('%H:%M:%S')}]", *a, flush=True)


def parse():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resolution", choices=["monthly", "daily"], required=True)
    p.add_argument("--device", choices=["cuda", "cpu"], required=True)
    p.add_argument("--models", nargs="+", default=list(S.MODELS), choices=list(S.MODELS))
    p.add_argument("--smoke", action="store_true", help="one origin, one model, 1 seed, a few training steps")
    p.add_argument("--out", default=None, help="results folder (default exploratory/bakeoff/results, or results_smoke with --smoke)")
    a = p.parse_args()
    if a.out is None:
        a.out = os.path.join(HERE, "results_smoke" if a.smoke else "results")
    if a.smoke:
        a.models = [a.models[0] if "--models" in sys.argv else SMOKE_MODEL]
    return a


# --------------------------------------------------------------------------- forecasting engine
class Engine:
    """Fits one model on one target type, following the refit schedule, with an on-disk per-fit cache."""

    def __init__(self, res, model, typ, tg, train_units, origins, c, device, steps, out, seeds):
        self.res, self.model, self.typ, self.tg, self.train_units = res, model, typ, tg, train_units
        self.origins, self.c, self.device, self.steps, self.out, self.seeds = origins, c, device, steps, out, seeds
        self.k = S.REFIT_EVERY[res]
        self.h = c["monthly"]["horizon"] if res == "monthly" else c["daily"]["horizon"]
        self.mem = {}
        self.pos = {o: i for i, o in enumerate(origins)}

    def cfg(self, cid):
        return (S.MONTHLY if self.res == "monthly" else S.DAILY)[self.model][cid]

    def _path(self, cid, seed, r):
        d = os.path.join(self.out, "cache", self.res, self.model, self.typ, cid)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"seed{seed}_refit{str(r)[:10]}.csv")

    def block(self, cid, seed, o):
        """Forecasts of every unit from every origin served by the refit that covers origin o."""
        i = self.pos[o]; r = self.origins[i - i % self.k]; served = self.origins[i - i % self.k: i - i % self.k + self.k]
        key = (cid, seed, str(r))
        if key in self.mem:
            return self.mem[key]
        path = self._path(cid, seed, r)
        if os.path.exists(path):
            df = pd.read_csv(path, dtype={"unit": str, "origin": str}, float_precision="round_trip")
        else:
            train = {u: self.tg[u].loc[:r] for u in self.train_units}
            assert all(len(s) == 0 or s.index[-1] <= r for s in train.values())          # leakage guard
            t0 = time.time()
            fit = N.Fitted(self.model, self.cfg(cid), self.res, self.h, seed, self.device, train, max_steps=self.steps)
            t_fit = time.time() - t0; rows = []
            for so in served:
                cut = {u: s.loc[:so] for u, s in self.tg.items()}
                cut = {u: s for u, s in cut.items() if len(s) and s.index[-1] == so}
                for u, f in fit.forecast(cut).items():
                    rows += [(str(so) if self.res == "monthly" else so.date().isoformat(), u, hh + 1, f[hh]) for hh in range(self.h)]
            df = pd.DataFrame(rows, columns=["origin", "unit", "h", "fc"])
            df.to_csv(path + ".tmp", index=False); os.replace(path + ".tmp", path)
            runlog(self.out, dict(resolution=self.res, model=self.model, type=self.typ, config=cid, seed=seed, refit_origin=str(r)[:10],
                                  n_origins=len(served), fit_seconds=round(t_fit, 2), total_seconds=round(time.time() - t0, 2), device=self.device))
        table = {(o_, u_): g.sort_values("h").fc.values for (o_, u_), g in df.groupby(["origin", "unit"])}
        self.mem[key] = table
        return table

    def forecaster(self, cid, seeds=None):
        seeds = seeds if seeds is not None else self.seeds
        def f(u, o):
            ok = str(o) if self.res == "monthly" else o.date().isoformat()
            fs = [self.block(cid, s, o).get((ok, u), np.full(self.h, np.nan)) for s in seeds]
            return np.mean(fs, axis=0)
        return f


def runlog(out, row):
    path = os.path.join(out, "run_log.csv")
    row = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


# --------------------------------------------------------------------------- gates
def naive_gate(res, targets, c):
    """Seasonal naive through the adapter must reproduce the frozen rows and metric exactly."""
    frozen = pd.read_csv(os.path.join(ROOT, "outputs", "backtest", f"{res}_errors.csv"),
                         dtype={"unit": str, "origin": str, "target": str}, float_precision="round_trip")
    sel = json.load(open(os.path.join(ROOT, "outputs", "backtest", "selection.json")))
    key = "monthly_mae_h2_all_origins" if res == "monthly" else "daily_mae_window"
    H = c["monthly"]["horizon"] if res == "monthly" else c["daily"]["horizon"]
    base = M.m_naive if res == "monthly" else M.d_naive
    report = {}
    for typ in ("raw", "adjusted"):
        tg = targets[typ]
        mine = A.run_harness(res, tg, [D.TARGET], "bakeoff_naive", lambda u, o: base(tg[u].loc[:o].values, H), c)
        mine["model"] = "naive"
        ref = frozen[(frozen.unit == D.TARGET) & (frozen.model == "naive") & (frozen.type == typ)].drop(columns="type")
        cols = [k for k in ref.columns if k not in ("unit", "model")]
        a = mine.sort_values(["origin", "h"]).reset_index(drop=True); b = ref.sort_values(["origin", "h"]).reset_index(drop=True)
        if len(a) != len(b):
            sys.exit(f"ABORT: naive gate {res}/{typ}: {len(a)} rows vs frozen {len(b)}")
        for k in cols:
            x, y = a[k].values, b[k].values
            same = (x == y) | (pd.isna(x) & pd.isna(y)) if x.dtype.kind == "f" else (x.astype(str) == y.astype(str))
            if not same.all():
                diff = np.nanmax(np.abs(x.astype(float) - y.astype(float))) if x.dtype.kind == "f" else "n/a"
                sys.exit(f"ABORT: naive gate {res}/{typ}: column {k} differs from the frozen backtest in {(~same).sum()} rows (max diff {diff})")
        # Score exactly as halo did: the frozen GTA V frame of this type, with its naive rows replaced by ours.
        # (pandas' grouped mean can differ in the last bit depending on which other models share the frame.)
        others = frozen[(frozen.unit == D.TARGET) & (frozen.model != "naive") & (frozen.type == typ)].drop(columns="type")
        combined = A.selection_metric(pd.concat([others, mine[ref.columns]], ignore_index=True), res, c)
        bad = {k: (v, sel["tables"][typ][key][k]) for k, v in combined.items() if v != sel["tables"][typ][key][k]}
        if bad:
            sys.exit(f"ABORT: naive gate {res}/{typ}: scores differ from selection.json: {bad}")
        mae, ref_mae = combined["naive"], sel["tables"][typ][key]["naive"]
        alone = A.selection_metric(mine, res, c)["naive"]
        report[typ] = {"rows": len(a), "rows_identical": True, "mae": mae, "frozen_mae": ref_mae, "exact": True,
                       "mae_scored_alone": alone, "alone_minus_frozen": alone - ref_mae}
        log(f"naive gate {res}/{typ}: {len(a)} rows identical to the frozen backtest; MAE {mae!r} == frozen {ref_mae!r}"
            + ("" if alone == ref_mae else f" (scored alone: {alone - ref_mae:+.1e}, pandas summation order)"))
    return report


def leakage_check(res, model, cid, origin, c, device, steps, seed):
    """Corrupt everything after `origin`, refit, and confirm the forecasts from `origin` do not change."""
    loader = D.load_monthly if res == "monthly" else D.load_daily
    w = loader(c, with_post=False); w2 = w.copy(); fut = w2.index > origin
    w2.loc[fut] += np.random.default_rng(c["seed"]).normal(0, 3.0, size=w2.loc[fut].shape)
    cfg = (S.MONTHLY if res == "monthly" else S.DAILY)[model][cid]
    h = c["monthly"]["horizon"] if res == "monthly" else c["daily"]["horizon"]
    outs = []
    for ww in (w, w2):
        tg = D.build_targets(ww, c)["raw"]
        cut = {u: s.loc[:origin] for u, s in tg.items()}
        fit = N.Fitted(model, cfg, res, h, seed, device, {u: cut[u] for u in tg if u != D.SIBLING and len(cut[u])}, max_steps=steps)
        outs.append(fit.forecast({u: s for u, s in cut.items() if len(s) and s.index[-1] == origin}))
    diff = max(float(np.nanmax(np.abs(outs[0][u] - outs[1][u]))) for u in outs[0] if np.isfinite(outs[0][u]).any())
    tol = 1e-4 if device == "cuda" else 0.0
    if not diff <= tol:
        sys.exit(f"ABORT: leakage check failed for {model}: forecasts changed by {diff} when the future was corrupted")
    log(f"leakage check {res}/{model}: forecasts unchanged when the future is corrupted (max diff {diff:.2e})")
    return diff


# --------------------------------------------------------------------------- one model
def run_model(a, model, targets, c, origins, seeds, steps):
    res = a.resolution; t_model = time.time()
    roles, _ = D.roles_names()
    controls = [u for u in targets["raw"] if roles[u] == "control"]
    frames, meta = [], {"model": model, "resolution": res, "types": {}}
    eval_origins = origins if a.smoke else None                      # None = halo's own default origins
    for typ in ("raw", "adjusted"):
        tg = targets[typ]; t_typ = time.time()
        train_units = [u for u in tg if u != D.SIBLING]
        eng = Engine(res, model, typ, tg, train_units, origins, c, a.device, steps, a.out, seeds)
        info = {}
        if res == "monthly":                                          # choose a config on controls, tuning origins only
            last = pd.Period(S.TUNING_LAST_ORIGIN, "M")
            tune = [o for o in origins if o <= last]
            h2 = {}
            for cid in S.CONFIG_ORDER:
                bt = A.run_harness(res, tg, controls, model, eng.forecaster(cid), c, origins=tune)
                h2[cid] = bt[bt.h == 2].set_index(["unit", "origin"]).err
                log(f"{model}/{typ} tuning config {cid} done ({time.time() - t_typ:.0f}s)")
            common = None
            for e in h2.values():
                idx = e.dropna().index
                common = idx if common is None else common.intersection(idx)
            scores = {cid: float(h2[cid].loc[common].abs().mean()) for cid in S.CONFIG_ORDER}
            chosen = min(S.CONFIG_ORDER, key=lambda k: (scores[k], S.CONFIG_ORDER.index(k)))
            info.update(tuning_scores=scores, tuning_pairs=len(common), tuning_origins=[str(tune[0]), str(tune[-1])], config=chosen)
            log(f"{model}/{typ} tuning MAE on controls {', '.join(f'{k}={v:.4f}' for k, v in scores.items())} -> {chosen}")
        else:
            chosen = "D"; info.update(config=chosen, tuning="none (fixed defaults)")
        bt = A.run_harness(res, tg, [D.TARGET], model, eng.forecaster(chosen), c, origins=eval_origins)
        if not a.smoke:
            seen = sorted(set(bt.origin)); expect = sorted(str(o) if res == "monthly" else o.date().isoformat() for o in origins)
            assert seen == expect, "harness origins differ from the refit schedule's origins"
        bt["type"] = typ; frames.append(bt)
        info["mae"] = A.selection_metric(bt, res, c).get(model)
        info["n"] = A.selection_n(bt, res, c).get(model, 0)
        info["per_seed_mae"] = {}
        for s in seeds:
            bs = A.run_harness(res, tg, [D.TARGET], model, eng.forecaster(chosen, [s]), c, origins=eval_origins)
            info["per_seed_mae"][str(s)] = A.selection_metric(bs, res, c).get(model)
        info["seconds"] = round(time.time() - t_typ, 1)
        meta["types"][typ] = info
        log(f"{model}/{typ}: GTA V selection-metric MAE {info['mae']:.4f} (n={info['n']}, config {chosen}, {info['seconds']:.0f}s)")
    cid = meta["types"]["raw"]["config"]
    chk_origin = origins[0] if a.smoke else (pd.Period("2023-10", "M") if res == "monthly" else pd.Timestamp("2026-10-15"))
    meta["leakage_max_diff"] = leakage_check(res, model, cid, chk_origin, c, a.device, steps, seeds[0])
    meta["seconds"] = round(time.time() - t_model, 1)
    meta.update(steps=steps, seeds=seeds, refit_every=S.REFIT_EVERY[res], smoke=a.smoke, device=a.device, env=environment(a.device),
                finished_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    d = os.path.join(a.out, res); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{model}_meta.json"), "w") as f:
        json.dump(meta, f, indent=1, default=str)
    out = pd.concat(frames, ignore_index=True)
    path = os.path.join(d, f"{model}_errors.csv")
    out.to_csv(path + ".tmp", index=False); os.replace(path + ".tmp", path)    # written last: its presence means "done"
    log(f"{model} finished in {meta['seconds']:.0f}s -> {path}")


def environment(device):
    import neuralforecast, torch
    import pytorch_lightning as pl
    env = dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__, torch=torch.__version__,
               neuralforecast=neuralforecast.__version__, lightning=pl.__version__, platform=platform.platform())
    if device == "cuda":
        env["gpu"] = torch.cuda.get_device_name(0)
    return env


# --------------------------------------------------------------------------- main
def main():
    global N
    a = parse()
    log(f"bake-off {a.resolution} on {a.device}{' (SMOKE)' if a.smoke else ''}; models {a.models}; out {a.out}")
    hashes = G.verify_inputs(log)                                     # before any data is read
    import torch
    if a.device == "cuda" and not torch.cuda.is_available():
        sys.exit("ABORT: --device cuda but torch.cuda.is_available() is False")
    if a.device == "cpu":
        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    from exploratory.bakeoff import neural
    N = neural
    os.makedirs(os.path.join(a.out, a.resolution), exist_ok=True)

    c = D.cfg()
    w = (D.load_monthly if a.resolution == "monthly" else D.load_daily)(c, with_post=False)
    last = c["freeze"]["monthly_origin"] if a.resolution == "monthly" else c["freeze"]["daily_origin"]
    assert str(w.index[-1])[:10] == last, f"data must end at the freeze origin {last}, ends {w.index[-1]}"
    targets = D.build_targets(w, c)

    gate = naive_gate(a.resolution, targets, c)
    with open(os.path.join(a.out, a.resolution, "gate.json"), "w") as f:
        json.dump({"hash_check": hashes, "naive_gate": gate, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}, f, indent=1)

    origins = A.all_origins(a.resolution, c)
    seeds = [c["seed"] + k for k in range(1 if a.smoke else S.SEEDS)]
    steps = SMOKE_STEPS if a.smoke else S.STEPS[a.resolution]
    if a.smoke:
        origins = origins[:1]
    for model in a.models:
        if os.path.exists(os.path.join(a.out, a.resolution, f"{model}_errors.csv")):
            log(f"{model}: results file exists, skipping"); continue
        run_model(a, model, targets, c, origins, seeds, steps)
    log("all requested models done")


if __name__ == "__main__":
    main()
