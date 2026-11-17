#!/usr/bin/env python3
"""Build a self-contained local preview of the dashboard: dashboard/preview.html.
The published dashboard is a Claude Data artifact that supplies `dash` and the theme. This script
supplies a small stand-in for both so the same index.html and app.js can be opened offline.

  python dashboard/dev_preview.py [--data outputs/dashboard] [--d3 path/to/d3.min.js]
"""
import argparse, csv, json, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ap = argparse.ArgumentParser(); ap.add_argument("--data", default=os.path.join(ROOT, "outputs", "dashboard")); ap.add_argument("--d3", default=None); ap.add_argument("--out", default=os.path.join(HERE, "preview.html"))
a = ap.parse_args()
data = {}
for f in sorted(os.listdir(a.data)):
    name, ext = os.path.splitext(f); p = os.path.join(a.data, f)
    if ext == ".csv": data[name] = [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(open(p))]   # cells are text, empty is null
    elif ext == ".json": data[name] = json.load(open(p))
d3 = f"<script>{open(a.d3).read()}</script>" if a.d3 else '<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>'
SHIM = """
window.dash = (() => {
  const store = __DATA__, calcs = {}, draws = {}, ons = [];
  const data = (id) => {
    if (calcs[id]) { const ins = calcs[id].inputs.map(data); if (ins.some((g) => g.status !== 'ok')) return {status: 'loading', data: null}; return {status: 'ok', data: calcs[id].fn(...ins.map((g) => g.data))}; }
    return store[id] ? {status: 'ok', data: store[id]} : {status: 'missing', data: []};
  };
  const run = (name) => document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => { if (!el.closest('[hidden]') && draws[name]) draws[name](el); });
  const all = () => { ons.forEach((f) => f()); Object.keys(draws).forEach(run); };
  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(all, 120); });
  window.addEventListener('DOMContentLoaded', all);
  return { data, colors: ['#3b6fb6', '#c2622d', '#2f8f6b', '#8a5bc7'], calc: (id, c) => { calcs[id] = c; }, onData: (f) => ons.push(f),
           draw: (name, fn) => { if (fn) draws[name] = fn; else run(name); }, params: () => ({}), setParams() {}, setLink() {} };
})();
"""
THEME = """<style>
:root { --color-fg:#1f1e1d; --color-fg-muted:#6b6a68; --color-bg:#ffffff; --color-panel:#faf9f5; --color-border-line:#e3e1da; --color-ok:#2f8f6b; --color-warn:#b7791f; --color-bad:#c0392b;
 --font-anthropic-sans: system-ui, sans-serif; --font-anthropic-serif: Georgia, serif; --cds-font-size-caption:12px; --cds-font-size-body:14px; --cds-font-size-heading:16px; --cds-font-size-title:26px; --cds-font-weight-medium:600;
 --cds-gap-xs:4px; --cds-gap-sm:8px; --cds-gap-md:12px; --cds-gap-lg:16px; --cds-gap-xl:28px; --cds-pad-xs:4px; --cds-pad-sm:8px; --cds-pad-md:12px; --cds-pad-lg:16px; --cds-pad-xl:24px; --cds-radius:8px;
 --cds-chart-muted:#9a9891; --cds-chart-status-critical:#c0392b; --cds-chart-grid:#eceae4; --cds-chart-axis:#cfcdc6; --cds-chart-reference:#8a8882; --cds-text-secondary:#6b6a68; --cds-surface-popover:#fff; --cds-border:#d9d7d0; --cds-shadow-popover:0 4px 14px rgba(0,0,0,.12); }
body { margin: 0; background: var(--color-bg); } #dash-root { padding: 20px; max-width: 1100px; margin: 0 auto; }
select.dash-select { font: inherit; padding: 4px 8px; }
</style>"""
page = open(os.path.join(HERE, "index.html")).read().replace('<script src="app.js"></script>', "<script>" + open(os.path.join(HERE, "app.js")).read() + "</script>")
html = "<!doctype html><html><head><meta charset='utf-8'><title>GTA V halo test, local preview</title>" + THEME + d3 + "<script>" + SHIM.replace("__DATA__", json.dumps(data)) + "</script></head><body><div id='dash-root'>" + page + "</div></body></html>"
open(a.out, "w").write(html); print("wrote", a.out, f"({len(html) // 1024} KB)")
