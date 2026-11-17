#!/usr/bin/env python3
"""Turn the raw SteamCharts pulls (data/raw/*.txt, pulled 2026-11-16) into tidy CSVs.
Provenance only: re-running it reproduces the CSVs in data/ byte for byte."""
import csv, os
from datetime import date, timedelta
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
def months(start, n):
    y, m = int(start[:4]), int(start[5:7]); out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out
def days(start, n):
    d0 = date.fromisoformat(start); return [(d0 + timedelta(i)).isoformat() for i in range(n)]

mon, day = [], []   # long rows
# controls
for line in open(f"{R}/raw/controls_pull_2026-11-16.txt"):
    aid, name, m0, avg, drange, dpk = line.rstrip("\n").split("|")
    avg = [int(x) for x in avg.split(",")]; dpk = [int(x) for x in dpk.split(",")]
    d0, d1, hrs = drange.split("/")
    for m, v in zip(months(m0, len(avg)), avg): mon.append([aid, name, "control", m, v])
    ds = days(d0, len(dpk)); assert ds[-1] == d1, (name, ds[-1], d1)
    for d, v in zip(ds, dpk): day.append([aid, name, "control", d, v, int(d == "2026-11-16")])
# GTA V legacy monthly (existing csv) + enhanced + RDR2
leg = list(csv.DictReader(open(f"{R}/steamcharts_gtav_legacy_monthly.csv")))
L_avg = {r["month"][:7]: round(float(r["avg_players"])) for r in leg}
L_pk = {r["month"][:7]: int(r["peak_players"]) for r in leg}
E_avg, E_pk = {}, {}
for line in open(f"{R}/raw/gta_extra_pull_2026-11-16.txt"):
    p = line.rstrip("\n").split("|")
    if p[0] == "3240220":
        vals = [int(x) for x in p[4].split(",")]
        (E_avg if p[3] == "avg" else E_pk).update(dict(zip(months(p[2], len(vals)), vals)))
    elif p[0] == "1174180" and p[3] == "avg":
        vals = [int(x) for x in p[4].split(",")]
        for m, v in zip(months(p[2], len(vals)), vals): mon.append(["1174180", p[1], "sibling", m, v])
    elif p[0] == "1174180" and p[3] == "dpeak":
        vals = [int(x) for x in p[4].split(",")]
        for d, v in zip(days(p[2], len(vals)), vals): day.append(["1174180", p[1], "sibling", d, v, int(d == "2026-11-16")])
    elif p[0] == "sim":
        with open(f"{R}/gtav_simultaneous_peak_check.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["date", "true_simultaneous_peak", "hours", "combined_avg"])
            for item in p[2].split(","): w.writerow(item.split(":"))
with open(f"{R}/gtav_monthly_combined.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["month", "legacy_avg", "enhanced_avg", "combined_avg", "legacy_peak", "enhanced_peak", "combined_peak_sum"])
    for m in sorted(L_avg):
        ea, ep = E_avg.get(m, 0), E_pk.get(m, 0)
        w.writerow([m, L_avg[m], ea or "", L_avg[m] + ea, L_pk[m], ep or "", L_pk[m] + ep])
        mon.append(["GTAV", "GTA V (Legacy + Enhanced)", "target", m, L_avg[m] + ea])
for r in csv.DictReader(open(f"{R}/steam_gtav_daily_peak.csv")):
    day.append(["GTAV", "GTA V (Legacy + Enhanced)", "target", r["date"], int(r["combined_peak_sum"]), int(r["partial_day"])])
with open(f"{R}/panel_monthly_avg.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["app_id", "name", "role", "month", "avg_players"]); w.writerows(mon)
with open(f"{R}/panel_daily_peak.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["app_id", "name", "role", "date", "peak_players", "partial_day"]); w.writerows(day)
print(len(mon), "monthly rows;", len(day), "daily rows")
