# Data notes (pulled 2026-11-16 from SteamCharts and Google Trends)

Used by the pipeline
- panel_monthly_avg.csv      monthly average players: GTA V (Legacy + Enhanced summed), 18 controls, RDR2 (sibling)
- panel_daily_peak.csv       daily peak players, 2026-08-20 to 2026-11-16 (Nov 16 partial), same units
- trends_daily_2026-03_to_2026-11.csv   Google Trends "GTA 6" vs "GTA 5", worldwide, daily (backtest of the ineligible Trends model; dashboard)
- gta_events.csv             leaks, official milestones, delays, GTA V and GTA Online events, Steam sales (dashboard markers only)

Reference
- steam_gtav_daily_peak.csv            per-app daily peaks for GTA V
- gtav_monthly_combined.csv            per-app monthly average and peak for GTA V
- steamcharts_gtav_legacy_monthly.csv  Legacy app monthly table as first pulled
- gtav_simultaneous_peak_check.csv     true simultaneous Legacy+Enhanced peak for the last 30 days
- trends_weekly_2021-11_to_2026-11.csv weekly Trends
- raw/                                 raw pulls; scripts/build_panel_from_raw.py rebuilds the panel files from them

Caveats
1. GTA V daily peak = Legacy peak + Enhanced peak. Over the 29 full days with hourly data this is 1.3% above the true simultaneous peak on average, 9% on the worst day (Nov 3).
2. Monthly averages add exactly across the two apps. March 2025 is the migration month (Enhanced launched Mar 4).
3. Daily history before 2026-08-20 is not available from SteamCharts.
4. Trends values are relative to the maximum inside each file; never compare across files.
5. Events with "from memory; confirm" in `source` were not verified. Trends spikes on 2026-05-18 and 2026-10-08 have no identified cause.
6. Days are UTC. SteamCharts samples about hourly.
