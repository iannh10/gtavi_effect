#!/usr/bin/env python3
"""Collect post-launch data for the tracker. Run on your own machine (standard library only).

  python scripts/collect_players.py backfill
      Pulls SteamCharts for GTA V (both apps), the 18 controls and RDR2, and writes
        data/post/panel_daily_peak_post.csv    (days after 2026-11-15)
        data/post/panel_monthly_avg_post.csv   (months after 2026-10)
      in the same format as the frozen panel files. This is the source the frozen forecast was
      built on, so it is the one the tracker scores against. Also writes the two GTA V apps
      separately (see "apps" below) from the same pull. Run it at least every 3 weeks:
      SteamCharts keeps hourly points for ~30 days and daily points for ~90.

  python scripts/collect_players.py apps
      Pulls only the two GTA V apps and writes
        data/post/gtav_apps_daily_post.csv             (date, legacy_peak, enhanced_peak, combined_peak, partial_day)
        outputs/dashboard/players_daily_apps_post.csv  (same file, for the dashboard)
      Descriptive only; the tracker does not read it.

  python scripts/collect_players.py poll [--loop 600]
      Backup only: appends the current GTA V player counts from Valve's public endpoint to
      data/live/players_poll.csv. Not used for scoring (different sampling than SteamCharts).

NOT TESTED against the live sites: the build sandbox had no network. The parsing functions are
tested offline (python scripts/collect_players.py selftest). If SteamCharts refuses scripted
requests, ask Claude to re-pull the same pages through the browser, as was done on 2026-11-16.
"""
import argparse, csv, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GTA = {"legacy": 271590, "enhanced": 3240220}
UA = {"User-Agent": "gtav-halo-research/0.2 (personal portfolio project)"}
MONTHS = {m: i + 1 for i, m in enumerate("January February March April May June July August September October November December".split())}
LAST_FROZEN_DAY, LAST_FROZEN_MONTH = "2026-11-15", "2026-10"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def panel_units():
    """app_id -> (name, role) for every non-GTA unit, read from the frozen panel file."""
    out = {}
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "panel_monthly_avg.csv"))):
        if r["app_id"] != "GTAV":
            out[r["app_id"]] = (r["name"], r["role"])
    return out


def daily_peaks(points, now_ms):
    """chart-data.json points [[ms, players], ...] -> {date: (peak, partial)} for UTC days.
    A day made of hourly samples is partial if it is today (UTC) or has fewer than 23 samples."""
    by = {}
    for i, (t, v) in enumerate(points):
        d = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
        gap = min(abs(t - points[i - 1][0]) if i else 9e15, abs(points[i + 1][0] - t) if i + 1 < len(points) else 9e15)
        e = by.setdefault(d, [0, 0, 0]); e[0] = max(e[0], v); e[1] += 1; e[2] += gap < 2 * 3600 * 1000
    today = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    return {d: (pk, int(d >= today or (hourly > 1 and hourly < 23))) for d, (pk, n, hourly) in by.items()}


def monthly_avgs(html):
    """SteamCharts app page -> {YYYY-MM: avg players} from the monthly table."""
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        m = re.match(r"^(\w+) (\d{4})$", cells[0]) if cells else None
        if m and m.group(1) in MONTHS and len(cells) >= 5:
            out[f"{m.group(2)}-{MONTHS[m.group(1)]:02d}"] = round(float(cells[1].replace(",", "")))
    return out


def write_apps(dl, de):
    """Per-app GTA V daily peaks after the freeze, same format as outputs/dashboard/players_daily.csv."""
    rows = [[d, dl[d][0], de[d][0], dl[d][0] + de[d][0], max(dl[d][1], de[d][1])]
            for d in sorted(set(dl) & set(de)) if d > LAST_FROZEN_DAY]
    for path in (os.path.join(ROOT, "data", "post", "gtav_apps_daily_post.csv"),
                 os.path.join(ROOT, "outputs", "dashboard", "players_daily_apps_post.csv")):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["date", "legacy_peak", "enhanced_peak", "combined_peak", "partial_day"]); w.writerows(rows)
    print(f"wrote {len(rows)} days to data/post/gtav_apps_daily_post.csv and outputs/dashboard/players_daily_apps_post.csv")


def apps():
    now = time.time() * 1000; day = {}
    for aid in map(str, GTA.values()):
        day[aid] = daily_peaks(json.loads(get(f"https://steamcharts.com/app/{aid}/chart-data.json")), now); time.sleep(1)
    write_apps(day[str(GTA["legacy"])], day[str(GTA["enhanced"])])


def backfill():
    units = panel_units(); now = time.time() * 1000
    ids = {**{str(v): None for v in GTA.values()}, **units}
    day, mon = {}, {}
    for aid in ids:
        day[aid] = daily_peaks(json.loads(get(f"https://steamcharts.com/app/{aid}/chart-data.json")), now); time.sleep(1)
        mon[aid] = monthly_avgs(get(f"https://steamcharts.com/app/{aid}")); time.sleep(1)
        print(aid, len(day[aid]), "days,", len(mon[aid]), "months")
    L, E = str(GTA["legacy"]), str(GTA["enhanced"])
    os.makedirs(os.path.join(ROOT, "data", "post"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "post", "panel_daily_peak_post.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["app_id", "name", "role", "date", "peak_players", "partial_day"])
        for d in sorted(set(day[L]) & set(day[E])):
            if d > LAST_FROZEN_DAY:
                w.writerow(["GTAV", "GTA V (Legacy + Enhanced)", "target", d, day[L][d][0] + day[E][d][0], max(day[L][d][1], day[E][d][1])])
        for aid, (name, role) in units.items():
            for d in sorted(day[aid]):
                if d > LAST_FROZEN_DAY: w.writerow([aid, name, role, d, day[aid][d][0], day[aid][d][1]])
    with open(os.path.join(ROOT, "data", "post", "panel_monthly_avg_post.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["app_id", "name", "role", "month", "avg_players"])
        for m in sorted(set(mon[L]) & set(mon[E])):
            if m > LAST_FROZEN_MONTH: w.writerow(["GTAV", "GTA V (Legacy + Enhanced)", "target", m, mon[L][m] + mon[E][m]])
        for aid, (name, role) in units.items():
            for m in sorted(mon[aid]):
                if m > LAST_FROZEN_MONTH: w.writerow([aid, name, role, m, mon[aid][m]])
    write_apps(day[L], day[E])
    print("wrote data/post/. Next: python -m halo.track")


def poll_once():
    out = os.path.join(ROOT, "data", "live"); os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "players_poll.csv"); new = not os.path.exists(path)
    row = [datetime.now(timezone.utc).isoformat(timespec="seconds")]
    for name, appid in GTA.items():
        try:
            row.append(json.loads(get(f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"))["response"]["player_count"])
        except Exception as e:
            print(f"{name}: {e}", file=sys.stderr); row.append("")
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["utc_time"] + [f"{n}_players" for n in GTA])
        w.writerow(row)
    print(row)


def selftest():
    H = 3600 * 1000; d0 = int(datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp() * 1000)
    pts = [[d0 - 3 * 24 * H, 100], [d0 - 2 * 24 * H, 110]] + [[d0 + i * H, 200 + i] for i in range(24)] + [[d0 + 24 * H + i * H, 300 + i] for i in range(5)]
    r = daily_peaks(pts, d0 + 24 * H + 5 * H)
    assert r["2026-11-17"] == (100, 0) and r["2026-11-18"] == (110, 0), r
    assert r["2026-11-20"] == (223, 0) and r["2026-11-21"] == (304, 1), r
    html = "<table><tbody><tr><td>Last 30 Days</td><td>1.0</td><td>-</td><td>-</td><td>2</td></tr><tr class='odd'><td class='month-cell left'>\n December 2026 \n</td><td>46,141.6</td><td>+1</td><td>+2%</td><td>78,603</td></tr></tbody></table>"
    assert monthly_avgs(html) == {"2026-12": 46142}, monthly_avgs(html)
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backfill", "apps", "poll", "selftest"])
    ap.add_argument("--loop", type=int, default=0, help="seconds between polls (poll mode)")
    a = ap.parse_args()
    if a.mode == "backfill": backfill()
    elif a.mode == "apps": apps()
    elif a.mode == "selftest": selftest()
    else:
        while True:
            poll_once()
            if not a.loop: break
            time.sleep(a.loop)
