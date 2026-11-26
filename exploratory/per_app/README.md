# Per-app forecast (exploratory)

**Post-hoc. Not part of the pre-registered test.** Made on 2026-11-26, after the GTA VI launch, to see
Legacy (app 271590) and Enhanced (app 3240220) separately. The frozen forecast in `outputs/frozen/v1/`
is unchanged and remains the only one that is scored.

- **Data:** pre-launch only. Full UTC days up to the freeze origin (2026-11-15) from
  `outputs/dashboard/players_daily.csv`, the per-app split of the series the freeze used. `data/post/` is not read.
- **Method:** the frozen daily method, applied to each app on its own. The model (seasonal naive, the frozen
  raw daily selection), the rolling-origin harness and the window errors are imported from `halo`. Backtest on
  the same 30 daily origins (2026-09-30 to 2026-10-29). Day-by-day intervals = forecast ± z × that app's
  backtest RMSE at each horizon, as in `halo/freeze.py`.
- **Scale:** raw (log daily peak) only. The adjusted series is a ratio to a control index, so it does not add
  across apps.
- **Check:** running the combined series through the same script reproduces the frozen raw point forecast and
  band widths exactly, and Legacy + Enhanced equals the frozen combined forecast (seasonal naive is additive here).

Outputs:
- `outputs/dashboard/per_app_forecast.csv`: date, app, forecast, lo80, hi80, lo95, hi95 (players), 2026-11-16 to 2026-12-02.
- `exploratory/per_app/backtest_summary.csv`: per-app backtest errors (log scale) and the O1 window
  forecast with its t(df=2) 95% interval, as in the freeze. The `combined` row is the reproduction check.

Run: `python exploratory/per_app/forecast_per_app.py`
