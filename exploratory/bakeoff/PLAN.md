# Exploratory bake-off plan: would heavier neural models have beaten the frozen winners?

Written 2026-11-23, after the freeze (2026-11-16) and after launch, **before any bake-off model was trained or scored**.
This is exploratory. It does not change the pre-registered test, its frozen forecasts, its selected models or its verdict,
whatever the results. Nothing here is used to re-forecast O1 or O2.

## 1. Question

On exactly the backtests that selected the frozen models, would any of six off-the-shelf deep forecasting models have
been selected instead, under the same 5% rule?

## 2. Data and isolation rules

- **Pre-launch data only.** The only data read are the hashed inputs in `outputs/frozen/v1/MANIFEST.json`
  (`data/panel_monthly_avg.csv` to 2026-10, `data/panel_daily_peak.csv` to 2026-11-15) and the frozen backtest outputs.
  Never read: `data/post/`, `outputs/tracker/`, `outputs/dashboard/tracker.csv`, or anything collected after the freeze.
- Every run (local or Colab) first checks the SHA-256 of every MANIFEST input, of `MANIFEST.json` itself
  (`4436e395…`, as committed in freeze commit `683a8fb`) and of `outputs/backtest/daily_errors.csv` (`fe0b8a3a…`, same
  commit; it is not listed in the MANIFEST). It aborts on any difference. A Windows checkout with `core.autocrlf` changes
  line endings only, so a file also passes if its bytes match after CRLF→LF; the log says which way it matched.
- A Python audit hook refuses to open any path under `data/post/`, `outputs/tracker/` or `outputs/dashboard/tracker.csv`.
- Data are loaded with `halo.data.load_monthly/load_daily(c, with_post=False)`.
- Nothing under `outputs/`, `docs/`, `halo/` or `config.yaml` is written. All code and results live in `exploratory/bakeoff/`.

## 3. Harness: identical to the frozen backtests

The bake-off imports and calls halo's own functions; nothing is copied or edited.

| | monthly | daily |
|---|---|---|
| harness | `halo.backtest.monthly_backtest` | `halo.backtest.daily_backtest` |
| origins | 107, 2017-10 to 2026-08 | 30, 2026-09-30 to 2026-10-29 |
| horizon | 1–2 months | 1–17 days |
| unit scored | GTA V (Legacy + Enhanced) | GTA V |
| targets | raw = log monthly avg players; adjusted = raw minus control index (`halo.data.build_targets`) | same, log daily peak |
| selection metric | MAE of log error at h = 2, all origins | MAE of the 14-day window mean, days 4–17 (`halo.backtest.window_errors`) |
| December-only | RMSE at h = 2 from the 9 October origins (Oct→Dec) | n/a |
| rule | `halo.backtest.select`, margin 0.05 | same |

The adapter registers each deep model under its own name in `halo.models.MONTHLY` / `halo.models.DAILY` in memory
for the duration of the call, so halo's loop decides which origins, units and actuals are used and writes rows in the
same format as `outputs/backtest/*_errors.csv`. The adapter identifies (unit, origin) from the history halo hands it and
asserts that history is exactly the unit's series cut at that origin.

**Gate:** before any model is trained, seasonal naive is run through the same adapter and must reproduce the frozen
`naive` rows of `outputs/backtest/{monthly,daily}_errors.csv` for GTA V (raw and adjusted) exactly, and the frozen
selection-metric values in `selection.json`. Otherwise the run aborts.

### Frozen scores to beat (from `outputs/backtest/selection.json`)

| resolution | target | frozen winner | winner MAE | a new model "beats" it if its MAE is below |
|---|---|---|---|---|
| monthly (h = 2) | raw | clim | 0.16224 | 0.15412 |
| monthly (h = 2) | adjusted | nn | 0.15049 | 0.14296 |
| daily (window) | raw | naive | 0.02967 | 0.02819 |
| daily (window) | adjusted | naive | 0.02058 | 0.01956 |

December-only RMSE of the frozen candidates (reported, not part of the rule): raw clim 0.185, nn 0.217, sarima 0.254,
naive 0.262; adjusted clim 0.201, nn 0.237, sarima 0.257, naive 0.292.

## 4. Models

Six models from Nixtla `neuralforecast` 3.3.1, in this complexity order:
**N-BEATS, N-HiTS, GRU, LSTM, PatchTST, TFT** (MLP-based, then recurrent, then attention).

- **Global**, like the frozen pooled MLP: one model per (origin, target) trained on GTA V and the 18 controls cut at the
  origin (`halo.backtest`'s `train_units`: every unit except the RDR2 sibling). A series enters training only if it has
  at least `input_size + h` points at that origin.
- Direct multi-horizon output (h = 2 monthly, h = 17 daily), on the same log scale as the frozen models.
- Per-window robust scaling inside each model (uses only the input window), MAE training loss, Adam, lr 1e-3,
  batch 32 series, 128 windows per step.
- **Fixed step budget, no validation set, no early stopping:** 500 steps monthly, 300 steps daily.
- **Seeds:** 20261116, 20261117, 20261118 (config seed + 0, 1, 2, as the frozen MLP). The forecast is the mean over the
  three seeds, as the frozen MLP's ensemble.
- **Exogenous inputs: calendar only, no Google Trends.** Month-of-year sin/cos (monthly) or day-of-week one-hot (daily)
  as future-known inputs, for models that accept them (N-HiTS, GRU, LSTM, TFT). N-BEATS and PatchTST take none.
- **Refit schedule.** Daily: refit at every origin, as the frozen MLP. Monthly: refit every 6 origins, anchored at
  2017-10 (refits on each October and April); between refits the model forecasts from each origin with the newest data
  as input and no weight update. This is a compute-driven departure from the frozen MLP, which refits every month. It
  can only make the deep models staler, never let them see the future. Every October origin (the December-only
  quantity) gets a fresh fit.

## 5. Hyperparameter budget (fixed now)

**Monthly: 3 configs × 3 seeds per model**, chosen separately for raw and adjusted.

| model | A | B | C |
|---|---|---|---|
| N-BEATS | 24 lags, 3 stacks × [128,128] | 24 lags, [256,256] | 12 lags, [256,256] |
| N-HiTS | 24 lags, [128,128], pool [2,2,1], downsample [2,1,1] | 24 lags, [256,256], same pooling | 12 lags, [256,256], pool [2,1,1] |
| GRU | 24 lags, 1 layer × 32 | 24 lags, 2 layers × 64 | 12 lags, 2 layers × 64 |
| LSTM | 24 lags, 1 layer × 32 | 24 lags, 2 layers × 64 | 12 lags, 2 layers × 64 |
| PatchTST | 24 lags, patch 6/stride 3, d 32, 2 layers | 24 lags, patch 6/3, d 64, 3 layers | 12 lags, patch 4/2, d 64, 3 layers |
| TFT | 24 lags, hidden 16, 2 heads | 24 lags, hidden 32, 4 heads | 12 lags, hidden 32, 4 heads |

Exact values are in `exploratory/bakeoff/specs.py`; that file is the record and must agree with this table.
Lags never exceed 24, so GTA V (31 points at 2017-10) has a forecast at every origin under every config.

**Choosing the config:**
- Tuning origins: monthly origins **2017-10 to 2024-08** only, i.e. at least 2 years before the last backtest origin
  (2026-08).
- Tuning units: **the 18 controls only.** GTA V's errors are never used to choose a config.
- Score: MAE of the 3-seed mean forecast at h = 2 over (control, origin) pairs that all three configs can forecast.
  Lowest wins; ties go to A, then B, then C.
- The chosen config is then scored on GTA V over all 107 origins. No other tuning, no re-runs, no extra configs.
- Because the tuning origins overlap the evaluation origins in time (on other units), the report also gives the MAE on
  the **24 untouched origins 2024-09 to 2026-08**, for every model including the frozen ones. That subset is descriptive.

**Daily: no tuning.** 88 daily points cannot support a separate tuning window, so each model uses one fixed default
config (D: 14 lags, the frozen MLP's `daily_lags`; widths as config B). Stated plainly: daily configs were not tuned.

## 6. Metrics and verdict

- Same metrics as the frozen backtests (section 3), computed with halo's functions, in log points.
- **"Beats" = the pre-registration's rule:** a more complex model is chosen only if its selection-metric error is at
  least 5% below the best simpler model's. Every deep model is more complex than every frozen candidate, so model X
  beats the frozen winner W iff `MAE_X < 0.95 × MAE_W`, for that resolution and target. Equivalently, `halo.backtest.select`
  over the frozen order with X appended returns X.
- A model must have a GTA V forecast at every origin the frozen winner has; otherwise it is reported as incomplete and
  cannot beat.
- **All-in selection** (secondary): `select` over the frozen order followed by the six models in the order of section 4.
- If `MAE_X / MAE_W` is within 0.5 percentage points of 0.95, the verdict is marked borderline.
- Reported but not part of the verdict: December-only RMSE and per-year December errors, the untouched 2024-09 to
  2026-08 subset, seed-to-seed spread, run times.

## 7. Hardware and reproducibility

- Training runs on Google Colab with an NVIDIA GPU (`--device cuda`). This PC (no CUDA) only smoke-tests on CPU.
- Results must not depend on hardware beyond floating-point noise: fixed seeds, Lightning `deterministic="warn"`,
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`. Package versions and the device are logged with the results.
- A leakage check runs once per model: fit on data cut at an origin, then corrupt everything after the origin, refit,
  and confirm the forecasts are unchanged (to 1e-4 log points on GPU).
- Results are saved per fit and per model, so a Colab disconnect loses at most one fit; finished models are skipped on
  restart.
- Expected Colab time: roughly 3 to 6 hours in total (about 1,650 monthly fits and 1,080 daily fits of a few seconds each).

## 8. What to expect

With about 125 to 150 monthly points per game and 88 daily points, deep models may well not win. The frozen pooled MLP
already missed the 5% margin on monthly raw by a hair, and seasonal naive won daily. "No deep model beats the frozen
winners" is a valid, informative result and will be reported as such.

## 9. Deviations

Any change to this plan after results exist will be listed here with its date and reason, and the original
version stays in git history.
