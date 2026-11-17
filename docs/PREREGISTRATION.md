# Pre-registration: does the GTA VI launch change GTA V play on Steam?

Written 2026-11-16, before any model was fitted or backtested. GTA VI launches 2026-11-19 on PS5 and Xbox Series X|S only.
Anything done after launch that is not described here is exploratory and will be labelled so.

## 1. Question and scope

Does the GTA VI launch change the number of people playing GTA V on Steam, relative to what would have happened without it?

Scope limits, stated up front:

- **Steam only.** GTA VI has no PC version, so a Steam player cannot switch to it on the same platform. Any effect here is indirect. Console GTA V and GTA Online, where direct substitution is most likely, are invisible in this data. The result must not be described as "the effect on GTA V demand".
- **Launch increment, not total hype effect.** Daily data starts 2026-08-20, two days after the August leak wave and after pre-orders opened. The baseline already contains hype. The estimand is the extra change at launch.
- **Bundle effect.** Rockstar may discount GTA V or run GTA Online events around the launch. Those are part of the launch and cannot be separated from it.
- **One event.** With a single launch, a forecast gap is evidence about an association in time, not proof of cause.

## 2. Hypotheses

- **H-halo:** attention spills over and GTA V Steam play rises above its counterfactual.
- **H-cannibal:** players who also own a console shift time to GTA VI (or streamers and friends leave) and GTA V Steam play falls below its counterfactual.
- **H0:** no detectable net change.

The sign is not predicted. All tests are two-sided.

## 3. Data and units

- **Target:** GTA V = Legacy (app 271590) + Enhanced (app 3240220), always combined.
- **Controls (fixed 2026-11-16 before inspecting their data):** Counter-Strike 2, Dota 2, Team Fortress 2, Rust, Euro Truck Simulator 2, Warframe, Rainbow Six Siege, Terraria, Garry's Mod, PAYDAY 2, Unturned, 7 Days to Die, Stardew Valley, War Thunder, DayZ, Arma 3, Dead by Daylight, Left 4 Dead 2. Rule: long-lived Steam games with continuous history, not published by Take-Two. No control is added or dropped after launch, except for missing data.
- **Sibling, descriptive only:** Red Dead Redemption 2 (Rockstar; possibly treated, so not a control).
- **Source:** SteamCharts, pulled 2026-11-16. Days are UTC. Partial days are excluded (2026-11-16 is partial).
- **Daily metric:** daily peak concurrent players. For GTA V this is the sum of the two apps' daily peaks, an upper bound on the true simultaneous peak (1.3% too high on average over the last 29 full days, 9% on the worst day). It is computed the same way before and after launch.
- **Monthly metric:** monthly average concurrent players. Averages add exactly across the two apps.
- **Control index:** chained index of the trimmed mean of the controls' period-over-period log changes (drop the 3 highest and 3 lowest each period). When a control is itself the unit under test (placebo), it is left out of its own index.
- **Two versions of every outcome:** *raw* (log players) and *adjusted* (log players minus the control index). Adjusted is primary because it removes Steam-wide December, Thanksgiving and sale effects to first order.

## 4. Outcomes

Forecast origin: 2026-11-15, the last full day. Monthly origin: October 2026, the last full month.

- **O1, launch fortnight (co-primary):** mean log daily peak over 2026-11-19 to 2026-12-02 (14 days, two full weeks), adjusted. Gap = actual minus frozen forecast.
- **O2, December (co-primary):** log monthly average players for December 2026, adjusted, forecast two months ahead from October. Gap = actual minus frozen forecast. November is not used as the base because half of it is post-launch, and using only Nov 1 to 15 would not match the backtest.
- **Secondary:** O1 and O2 on the raw scale; the day-by-day gap; Red Dead Redemption 2; Google Trends as a mechanism readout.

Gaps are in log points; exp(gap) − 1 is the percent difference.

## 5. Models and selection

Candidates at monthly resolution (forecasting 1 and 2 months ahead):
1. Seasonal naive: last value plus last year's change over the same months.
2. Seasonal climatology: last value plus the average change over the same months in all earlier years.
3. SARIMA (0,1,1)(0,1,1)12 on logs.
4. Neural: one small MLP trained across GTA V and the 18 controls (24 monthly lags, month-of-year inputs).

Candidates at daily resolution (forecasting 17 days ahead):
1. Seasonal naive: repeat the last 7 days.
2. ETS with weekly seasonality, no trend; and the same with a damped trend.
3. SARIMAX with a Google Trends "GTA 5" covariate. Backtested for information only and **not eligible for the frozen forecast**: search interest is already reacting to the launch (it doubled from Nov 9), so it is part of the treatment, not a control for it.
4. Neural: one small MLP trained across the 19 series (14 daily lags, day-of-week inputs).

Rules:
- Selection is by rolling-origin backtest only. Monthly: mean absolute log error two months ahead, origins 2017-10 to 2026-08, GTA V. Daily: mean absolute error of the 14-day window mean at days 4 to 17 ahead, origins 2026-09-30 to 2026-10-29, GTA V. Selection is done separately for raw and adjusted.
- A more complex model must beat the best simpler one by at least 5% to be chosen. Order of simplicity: naive, climatology/ETS, SARIMA, neural.
- Neural hyperparameters are fixed in `config.yaml` before any backtest. There is no tuning: the data cannot support it honestly.
- **Known limit of the neural model:** 88 daily points per series and about 130 to 150 monthly points. Pooling 19 series is the only reason it is trainable at all. If it loses the backtest it is not used.

## 6. Uncertainty and decision rule

- **Prediction intervals.** Centre = frozen point forecast. Scale = backtest RMSE of the selected model for the matching quantity (O2: October-origin, December-target errors; O1: 14-day window errors). Width uses a Student-t quantile. Degrees of freedom: O2 = number of December backtests minus 1. O1 = 2, because 30 overlapping daily origins span only about three independent 14-day windows.
- **Placebo test.** The identical pipeline is frozen for each of the 18 controls (each against an index of the other 17). After launch, each unit's gap is divided by its own backtest RMSE. GTA V's standardized gap is ranked among the 19. The most extreme rank gives a two-sided p of 1/19 = 0.053.
- **Decision, per outcome:**
  - *Detected*: GTA V is outside its 90% interval **and** has the most extreme standardized gap of all 19 units.
  - *Suggestive*: exactly one of the two holds.
  - *Not detected*: neither holds. This is reported together with the minimum detectable effect (the 90% interval half-width), so "not detected" is never read as "no effect".
- Two co-primary outcomes are tested with no multiplicity correction. A single "detected" is therefore weaker than it looks; the claim is strongest if O1 and O2 agree in sign.

## 7. Day-by-day tracker (descriptive)

- Nov 19 to Dec 2: the selected daily model's forecast.
- Dec 3 to Dec 31: October's mean log daily peak, plus the monthly model's forecast October-to-December change, plus the day-of-week pattern. The within-December shape (ramp into the holidays) is **not modelled**, so the cumulative December gap is only interpretable for the full month. This assumes the daily-peak to monthly-average ratio is stable.

## 8. Threats that remain

- Late November contains Thanksgiving and probably the Steam Autumn Sale; late December contains the Winter Sale and usually a GTA Online update. The control index absorbs Steam-wide effects only. A GTA-specific discount or update lands in the gap.
- GTA V's December rise has varied from +16% to +96% (October to December, 2015 to 2025). Only large effects are detectable in O2.
- Daily backtests cover Sep 30 to Nov 15 only: no holiday, no sale. O1's interval may be too narrow for a Thanksgiving week.
- The control pool is exposed to GTA VI too (people have finite time). If controls fall, the adjusted gap understates cannibalization. Raw results are reported alongside for this reason.
- Controls have their own shocks (for example Euro Truck Simulator 2 jumped on Nov 12). Trimming limits, but does not remove, their influence.
- SteamCharts samples hourly. Post-launch data must come from the same source.

## 9. Freeze

All forecasts (GTA V, 18 placebos, sibling) are written once to `outputs/frozen/` with a UTC timestamp and SHA-256 hashes in `MANIFEST.json`. They are committed and pushed before 2026-11-19. After launch nothing is refitted to change these numbers. Any refit is exploratory and is reported next to, never instead of, the frozen result.

## Amendment 1 (2026-11-16, before the freeze)

Section 8 said late November "probably" contains the Steam Autumn Sale. That was wrong for 2026: Valve's published calendar puts the Autumn Sale on Oct 1 to 8 (inside the daily baseline) and the Winter Sale on Dec 17 to Jan 4. So:

- The launch fortnight (O1) contains Thanksgiving and publisher Black Friday discounts, but no storewide Steam sale.
- December (O2) contains the Winter Sale from Dec 17, as in every backtest year.
- The daily baseline contains one sale week (Oct 1 to 8).

This corrects a calendar fact only. No outcome, model, rule or control changes. It was written while backtests were running; it does not depend on their results.

## Amendment 2 (2026-11-16, before the freeze, after the backtests)

The selection rule in section 5 was applied as written and is not changed. It chose the pooled neural model for the adjusted December outcome (lower error over all monthly origins). On the 9 December-only backtests, seasonal climatology had the lower error (RMSE 0.194 vs 0.246), a difference driven mainly by one year (2019).

Because the rule was set first, the neural model stays primary. One sensitivity analysis is added and frozen alongside it: **O2 with seasonal climatology** for GTA V, wherever climatology was not the selected model. It has its own interval but no placebo ranking. If the primary and the sensitivity result disagree after launch, both are reported and the O2 conclusion is called fragile.

## Amendment 3 (2026-11-16, before the freeze): the control index was biased and is replaced

Section 3 defined the control index as a chained *trimmed* mean of the controls' log changes. A check after the first backtest showed that this index drifts: over the 88 daily points it fell 0.24 log points (about 22%) relative to the plain average of the same 18 games, and 1.5 log points over the monthly history. The cause is skew. A game's update produces one large jump followed by a long slow decline; trimming removes the jump and keeps the decline, and chaining accumulates the difference. The adjusted GTA V series was therefore rising for a reason that had nothing to do with GTA V.

Change: the index is now the chained **plain mean** of the controls' log changes (an equal-weight geometric index, `index.trim: 0`). It cannot drift this way. Its cost is less protection against a single control's shock: one control doubling moves the index by about 4%.

Consequences, stated plainly:
- All backtests were re-run from scratch with the corrected index, and the selection rule in section 5 was applied again as written.
- A first freeze made with the biased index, minutes earlier, was discarded before it was delivered or committed. The freeze in `outputs/frozen/v1` is the only one.
- Amendment 2's numbers referred to the biased index. With the corrected index the picture is the same in kind: the rule again selects the neural model for adjusted December (all-origin error 0.151 vs 0.177), while on the 9 December-only backtests climatology is lower (RMSE 0.201 vs 0.237). The sensitivity analysis stays. The adjusted daily model is now seasonal naive.
- Nothing post-launch had been observed.
