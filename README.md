# GTA V halo test: does the GTA VI launch change GTA V play on Steam?

A pre-registered forecast-gap study. Models are fitted on data up to 2026-11-15, the forecast for
2026-11-19 to 2026-12-31 is frozen and hashed before launch, and the gap between actual and forecast is
scored afterwards against 18 placebo games. Read `docs/PREREGISTRATION.md` first.

## Layout

    config.yaml                 every setting, fixed before the backtests
    data/                       inputs as pulled on 2026-11-16 (see data/README.md); data/raw/ = raw pulls
    data/post/                  post-launch data goes here (created by the collector)
    halo/data.py                loading and the control index
    halo/models.py              seasonal naive, climatology, SARIMA, ETS, SARIMAX+Trends, pooled neural MLP
    halo/backtest.py            rolling-origin backtests, selection rule, leakage tests
    halo/freeze.py              writes outputs/frozen/v1 with SHA-256 manifest
    halo/track.py               post-launch scoring; refuses to run if frozen files changed
    halo/report.py              backtest report and dashboard data files
    scripts/collect_players.py  post-launch data collector (run on your machine)
    dashboard/                  page source of the published dashboard + local preview builder
    docs/                       pre-registration, backtest report
    outputs/frozen/v1/          THE frozen forecast. Do not edit.

## Setup

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

Python 3.11+. A GPU is not needed: the largest model trains on about 2,400 rows in two seconds on CPU.
`nn.device: auto` in `config.yaml` uses CUDA if present.

## Before launch (by 2026-11-18): commit the freeze

    git init && git add -A && git commit -m "Freeze GTA V counterfactual forecast v1 (pre-launch)"
    git remote add origin <your public repo> && git push -u origin main
    sha256sum outputs/frozen/v1/MANIFEST.json      # macOS: shasum -a 256 ...

The push time on a public host is the independent timestamp. Do not re-run `halo.freeze`: the frozen CSVs
are the record, and neural results can differ in late decimals on other hardware.

## After launch

    python scripts/collect_players.py selftest     # offline check of the parsers
    python scripts/collect_players.py backfill     # at least every 3 weeks; writes data/post/
    python -m halo.track                           # scores against the frozen forecast, writes outputs/tracker and outputs/dashboard

Then replace `tracker.csv` and `outcomes.csv` in the dashboard (Sources, as an editor), or run
`python dashboard/dev_preview.py` and open `dashboard/preview.html` locally.

The collector was not run against the live sites from the build sandbox. If SteamCharts blocks it, ask
Claude to pull the same pages through the browser and write the two files in `data/post/`.

Milestones: Dec 3 (launch fortnight complete, outcome O1) and early January (December average, outcome O2).

## Reproducing the pre-launch work (optional, about 15 minutes on CPU)

    python -m halo.backtest      # backtests, selection, leakage tests -> outputs/backtest
    python -m halo.report        # docs/BACKTEST_REPORT.md and dashboard files

`python -m halo.freeze` will refuse to overwrite `outputs/frozen/v1`.

## What is enforced

- `halo.track` stops if either frozen CSV or either frozen input panel differs from the hashes in `MANIFEST.json`.
- The manifest also records hashes of the config, the pre-registration and the code at freeze time, for the record.
- Backtests assert that no training point is later than the forecast origin, and corrupt-the-future tests confirm it.

## Honest limits

See section 8 of the pre-registration and "Limits" in the backtest report. In short: Steam only; one
event; 88 days of daily history with no holiday in it; December is so variable that only a change of
roughly a third or more is detectable there.
