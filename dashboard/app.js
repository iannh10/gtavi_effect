(() => {
  const num = (v) => (v === null || v === undefined || v === '' ? null : +v);
  const day = (s) => new Date(s + 'T00:00:00Z');
  const fInt = d3.format(',.0f'), f1 = d3.format('.1f'), fSI = d3.format('~s');
  const sPct = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + f1(Math.abs(v)) + '%';
  const fDay = d3.utcFormat('%b %-d'), fDayY = d3.utcFormat('%a %b %-d, %Y'), fMon = d3.utcFormat('%b %Y');
  const ok = (id) => { const g = dash.data(id); return g.status === 'ok' ? g.data : null; };
  const blank = (el) => el.replaceChildren(document.createTextNode('—'));
  const state = { view: 'raw', mrange: '2015' };
  const MODEL = { naive: 'Seasonal naive', clim: 'Seasonal climatology', sarima: 'SARIMA', nn: 'Neural, pooled across 19 games', ets: 'ETS', ets_damped: 'ETS, damped trend', sarimax_trends: 'SARIMAX with Trends' };
  const OUTCOME = { O1: 'Launch fortnight', O2: 'December', O2_sensitivity_clim: 'December, sensitivity' };
  const TARGET = { raw: 'Raw players', adjusted: 'Control-adjusted (primary)' };
  const DOMAIN = [day('2026-08-20'), day('2026-12-31')], LAUNCH = day('2026-11-19');   // fixed by the pre-registration

  // ---- values worked out from the files (readers can see these functions in Sources)
  dash.calc('prelaunch', {
    inputs: ['players_daily'], title: 'Pre-launch level',
    description: 'Mean combined daily peak over the last 14 full days before the freeze (Nov 2 to 15, 2026).',
    fn: (players_daily) => {
      const full = players_daily.filter((r) => +r.partial_day === 0).slice(-14);
      return full.length ? Math.round(full.reduce((s, r) => s + +r.combined_peak, 0) / full.length) : null;
    },
  });
  dash.calc('latest', {
    inputs: ['tracker'], title: 'Latest scored day',
    description: 'The most recent scored day of the launch fortnight in the tracker file.',
    fn: (tracker) => {
      const scored = tracker.filter((r) => r.days_scored !== null && r.days_scored !== '' && r.days_scored !== undefined);
      const last = scored[scored.length - 1];
      return last ? [{ date: last.date, days_scored: +last.days_scored, mean_gap_pct: +last.mean_gap_pct, adj_mean_gap_pct: +last.adj_mean_gap_pct }] : [];
    },
  });

  // ---- which sentences and panels show (runs before the drawings)
  dash.onData(() => {
    const l = dash.data('latest'), live = l.status === 'ok' && Array.isArray(l.data) && l.data.length > 0;
    document.querySelectorAll('[data-take]').forEach((e) => { e.hidden = (e.dataset.take === 'live') !== live; });
    const t = dash.data('tracker'), scored = t.status === 'ok' && t.data.some((r) => num(r.gap_pct) !== null);
    document.querySelectorAll('[data-gap]').forEach((e) => { e.hidden = scored; });
    document.querySelectorAll('[data-draw="gap-chart"]').forEach((e) => { e.hidden = !scored; });
    const o = dash.data('outcomes'), pl = o.status === 'ok' && o.data.some((r) => r.role === 'control' && num(r.z) !== null);
    document.querySelectorAll('[data-pl]').forEach((e) => { e.hidden = pl; });
    document.querySelectorAll('[data-draw="placebo-chart"]').forEach((e) => { e.hidden = !pl; });
    document.querySelectorAll('[data-c]').forEach((e) => { e.style.borderTopColor = dash.colors[+e.dataset.c]; });
    document.querySelectorAll('[data-cbg]').forEach((e) => { e.style.background = dash.colors[+e.dataset.cbg]; });
    document.querySelectorAll('[data-tri]').forEach((e) => { e.style.stroke = dash.colors[2]; e.style.strokeWidth = '1.2'; e.style.fill = e.dataset.tri === 'fill' ? dash.colors[2] : 'var(--color-bg)'; });
  });
  document.querySelectorAll('#mrange').forEach((sel) => sel.addEventListener('change', () => { state.mrange = sel.value; dash.draw('monthly-chart'); }));
  document.querySelectorAll('#view').forEach((sel) => sel.addEventListener('change', () => {
    state.view = sel.value;
    ['players-chart', 'dec-chart', 'gap-chart', 'placebo-chart'].forEach((n) => dash.draw(n));
  }));

  // ---- single figures
  const figure = (name, src, pick, fmt) => dash.draw(name, (el) => {
    const g = dash.data(src); const v = g.status === 'ok' ? pick(g.data) : null;
    el.textContent = v === null || v === undefined || Number.isNaN(v) ? '—' : fmt(v);
  });
  const oc = (key, field) => (rows) => { const r = rows.find((x) => x.key === key); return r ? num(r[field]) : null; };
  figure('c-pre', 'prelaunch', (v) => v, fInt);
  figure('c-o1', 'outcomes', oc('GTAV|raw|O1', 'forecast'), fInt);
  figure('c-o1-lo', 'outcomes', oc('GTAV|raw|O1', 'lo90'), fInt);
  figure('c-o1-hi', 'outcomes', oc('GTAV|raw|O1', 'hi90'), fInt);
  figure('c-o2', 'outcomes', oc('GTAV|raw|O2', 'forecast'), fInt);
  figure('c-o2-lo', 'outcomes', oc('GTAV|raw|O2', 'lo90'), fInt);
  figure('c-o2-hi', 'outcomes', oc('GTAV|raw|O2', 'hi90'), fInt);
  figure('c-mde1d', 'outcomes', oc('GTAV|adjusted|O1', 'detectable_down_pct'), sPct);
  figure('c-mde1', 'outcomes', oc('GTAV|adjusted|O1', 'detectable_up_pct'), sPct);
  figure('c-mde2d', 'outcomes', oc('GTAV|adjusted|O2', 'detectable_down_pct'), sPct);
  figure('c-mde2', 'outcomes', oc('GTAV|adjusted|O2', 'detectable_up_pct'), sPct);
  figure('t-days', 'latest', (r) => (r && r[0] ? r[0].days_scored : null), (v) => String(v));
  figure('t-gap', 'latest', (r) => (r && r[0] ? r[0].mean_gap_pct : null), sPct);
  figure('t-adj', 'latest', (r) => (r && r[0] ? r[0].adj_mean_gap_pct : null), sPct);

  // ---- chart helpers
  function frame(el, h, label) {
    const w = Math.max(260, el.clientWidth || 640);
    el.replaceChildren();
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('height', h).attr('viewBox', `0 0 ${w} ${h}`).attr('role', 'img').attr('aria-label', label);
    const tip = d3.select(el).append('div').attr('class', 'hx-tip').style('display', 'none');
    return { w, h, svg, tip };
  }
  function leftMargin(svg, scale, fmt, n) {
    const g = svg.append('g').attr('class', 'hx-axis').call(d3.axisLeft(scale).ticks(n).tickFormat(fmt));
    let mx = 0; g.selectAll('text').each(function () { mx = Math.max(mx, this.getComputedTextLength()); }); g.remove();
    return Math.ceil(mx) + 14;
  }
  function axes(g, x, y, iw, ih, yfmt, xfmt, xn) {
    g.append('g').attr('class', 'hx-grid').call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat(''));
    g.append('g').attr('class', 'hx-axis').call(d3.axisLeft(y).ticks(5).tickFormat(yfmt).tickSize(0).tickPadding(8)).call((a) => a.select('.domain').remove());
    const ax = d3.axisBottom(x).ticks(Math.max(2, Math.floor(iw / (xn || 90)))).tickSizeOuter(0);
    if (xfmt) ax.tickFormat(xfmt);
    g.append('g').attr('class', 'hx-axis').attr('transform', `translate(0,${ih})`).call(ax);
  }
  function showTip(f, el, px, py, title, lines, notes) {
    const n = f.tip.node(); n.replaceChildren();
    const b = document.createElement('b'); b.textContent = title; n.append(b);
    lines.forEach((t) => { const d = document.createElement('div'); d.textContent = t; n.append(d); });
    (notes || []).forEach((t) => { const d = document.createElement('div'); d.className = 'hx-tip-ev'; d.textContent = t; n.append(d); });
    f.tip.style('display', 'block');
    const tw = n.offsetWidth, th = n.offsetHeight, cw = el.clientWidth;
    f.tip.style('left', Math.max(0, Math.min(px + 14, cw - tw - 2)) + 'px').style('top', Math.max(0, py - th - 10) + 'px');
  }
  function eventsIn(E, dom) {
    return E.map((e) => ({ d: day(e.date), end: e.end_date ? day(e.end_date) : null, group: e.group, title: e.title }))
      .filter((e) => (e.end || e.d) >= dom[0] && e.d <= dom[1]);
  }
  function drawEvents(g, x, ev, ih, top) {
    const cl = (d) => new Date(Math.max(+x.domain()[0], Math.min(+x.domain()[1], +d)));
    g.append('g').selectAll('rect').data(ev.filter((e) => e.group === 'steam' && e.end)).join('rect')
      .attr('x', (e) => x(cl(e.d))).attr('width', (e) => Math.max(1, x(cl(e.end)) - x(cl(e.d)))).attr('y', 0).attr('height', ih)
      .style('fill', 'var(--cds-chart-muted)').style('opacity', 0.14);
    const row = { leak: top, gta6: top + 11, gta5: top + 22 };
    const pts = ev.filter((e) => row[e.group] !== undefined && e.d >= x.domain()[0]);
    g.append('g').selectAll('path').data(pts).join('path')
      .attr('transform', (e) => `translate(${x(e.d)},${row[e.group]})${e.group === 'leak' ? ' rotate(180)' : ''}`)
      .attr('d', (e) => d3.symbol(e.group === 'leak' ? d3.symbolTriangle : e.group === 'gta6' ? d3.symbolCircle : d3.symbolSquare, e.group === 'leak' ? 46 : 34)())
      .style('fill', (e) => (e.group === 'leak' ? 'var(--color-bad)' : e.group === 'gta6' ? 'var(--color-fg)' : 'var(--cds-chart-muted)'));
  }
  const evNotes = (ev, d) => ev.filter((e) => (e.end ? d >= e.d && d <= e.end : +e.d === +d))
    .map((e) => ({ leak: 'Leak: ', gta6: 'GTA VI: ', gta5: 'GTA V: ', steam: 'Steam: ' }[e.group] || '') + e.title);
  function hover(g, f, el, x, m, iw, ih, at) {
    const rule = g.append('line').attr('y1', 0).attr('y2', ih).style('stroke', 'var(--cds-chart-reference)').style('display', 'none');
    g.append('rect').attr('width', iw).attr('height', ih).style('fill', 'transparent')
      .on('pointermove', (evt) => {
        const [px, py] = d3.pointer(evt); const r = at(x.invert(px)); if (!r) return;
        rule.style('display', null).attr('x1', x(r.d)).attr('x2', x(r.d));
        showTip(f, el, m.l + x(r.d), m.t + py, r.title, r.lines, r.notes);
      })
      .on('pointerleave', () => { rule.style('display', 'none'); f.tip.style('display', 'none'); });
  }
  const snapDay = (d) => new Date(Math.round(+d / 864e5) * 864e5);

  // ---- daily players, forecast, events
  dash.draw('players-chart', (el) => {
    const P = ok('players_daily'), AH = ok('adjusted_history'), F = ok('forecast'), T = ok('tracker'), E = ok('events');
    if (!P || !AH || !F || !T || !E) return blank(el);
    const adj = state.view === 'adj', k = adj ? 'adj_' : '';
    const full = P.filter((r) => +r.partial_day === 0);
    const hist = adj ? AH.map((r) => ({ d: day(r.date), v: num(r.adj_index) })) : full.map((r) => ({ d: day(r.date), v: num(r.combined_peak) }));
    const apps = adj ? [] : full.map((r) => ({ d: day(r.date), a: num(r.legacy_peak), b: num(r.enhanced_peak) }));
    const fc = F.map((r) => ({ d: day(r.date), f: num(r[k + 'forecast']), l8: num(r[k + 'lo80']), h8: num(r[k + 'hi80']), l9: num(r[k + 'lo95']), h9: num(r[k + 'hi95']), dec: r.basis !== 'daily_model' }));
    const act = T.map((r) => ({ d: day(r.date), v: num(adj ? r.adj_actual : r.actual), partial: +r.partial_day === 1, gap: num(adj ? r.adj_gap_pct : r.gap_pct) })).filter((r) => r.v !== null);
    const ev = eventsIn(E, DOMAIN);
    const f = frame(el, 360, 'GTA V daily peak players on Steam with the frozen forecast, its bands and dated events');
    const all = hist.map((r) => r.v).concat(fc.map((r) => r.h9), fc.map((r) => r.l9), act.map((r) => r.v));
    const y = d3.scaleLinear().domain(adj ? [d3.min(all) * 0.95, d3.max(all) * 1.03] : [0, d3.max(all) * 1.03]).nice();
    const yfmt = adj ? d3.format('.0f') : fSI;
    const m = { t: 44, r: 16, b: 28, l: leftMargin(f.svg, y, yfmt, 5) }, iw = f.w - m.l - m.r, ih = f.h - m.t - m.b;
    const x = d3.scaleUtc().domain(DOMAIN).range([0, iw]); y.range([ih, 0]);
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    axes(g, x, y, iw, ih, yfmt, fDay);
    drawEvents(g, x, ev, ih, -32);
    const c0 = dash.colors[0], c1 = dash.colors[1];
    [fc.filter((r) => !r.dec), fc.filter((r) => r.dec)].forEach((seg) => {
      g.append('path').datum(seg).attr('d', d3.area().x((r) => x(r.d)).y0((r) => y(r.l9)).y1((r) => y(r.h9))).style('fill', c1).style('opacity', 0.12);
      g.append('path').datum(seg).attr('d', d3.area().x((r) => x(r.d)).y0((r) => y(r.l8)).y1((r) => y(r.h8))).style('fill', c1).style('opacity', 0.18);
      g.append('path').datum(seg).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.f))).style('fill', 'none').style('stroke', c1).style('stroke-width', 1.5).style('stroke-dasharray', '5 3');
    });
    apps.length && g.append('path').datum(apps).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.a))).style('fill', 'none').style('stroke', 'var(--cds-text-secondary)').style('stroke-width', 1);
    apps.length && g.append('path').datum(apps).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.b))).style('fill', 'none').style('stroke', 'var(--cds-text-secondary)').style('stroke-width', 1.5).style('stroke-dasharray', '1 3');
    g.append('path').datum(hist).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.v))).style('fill', 'none').style('stroke', c0).style('stroke-width', 2);
    g.append('g').selectAll('circle').data(act).join('circle').attr('cx', (r) => x(r.d)).attr('cy', (r) => y(r.v)).attr('r', 3.2)
      .style('fill', (r) => (r.partial ? 'var(--color-bg)' : c0)).style('stroke', c0).style('stroke-width', 1.5);
    g.append('line').attr('x1', x(LAUNCH)).attr('x2', x(LAUNCH)).attr('y1', -6).attr('y2', ih).style('stroke', 'var(--cds-chart-reference)').style('stroke-dasharray', '2 2');
    g.append('text').attr('class', 'hx-note').attr('x', x(LAUNCH) + 4).attr('y', ih - 6).text('GTA VI launch');
    const dec = fc.filter((r) => r.dec);
    if (dec.length && iw > 420) g.append('text').attr('class', 'hx-note').attr('x', x(dec[Math.floor(dec.length / 2)].d)).attr('y', y(d3.max(dec, (r) => r.h9)) - 6).attr('text-anchor', 'middle').text('December level, shape not modelled');
    const H = new Map(hist.map((r) => [+r.d, r])), A = new Map(apps.map((r) => [+r.d, r])), FC = new Map(fc.map((r) => [+r.d, r])), AC = new Map(act.map((r) => [+r.d, r]));
    const vf = adj ? f1 : fInt;
    hover(g, f, el, x, m, iw, ih, (d0) => {
      const d = snapDay(d0); if (d < DOMAIN[0] || d > DOMAIN[1]) return null;
      const h = H.get(+d), a = A.get(+d), fr = FC.get(+d), ac = AC.get(+d), lines = [];
      if (h) lines.push((adj ? 'Index: ' : 'Both apps: ') + vf(h.v));
      if (a) lines.push('Legacy ' + fInt(a.a) + ', Enhanced ' + fInt(a.b));
      if (ac) lines.push((ac.partial ? 'Partial day so far: ' : 'Actual: ') + vf(ac.v) + (ac.gap !== null ? ' (' + sPct(ac.gap) + ' vs forecast)' : ''));
      if (fr) lines.push('Forecast: ' + vf(fr.f) + ' (80% ' + vf(fr.l8) + ' to ' + vf(fr.h8) + ')');
      const notes = evNotes(ev, d);
      return lines.length || notes.length ? { d, title: fDayY(d), lines, notes } : null;
    });
  });

  // ---- search interest
  dash.draw('trends-chart', (el) => {
    const T = ok('trends'), E = ok('events');
    if (!T || !E) return blank(el);
    const rows = T.map((r) => ({ d: day(r.date), a: num(r.gta6_interest), b: num(r.gta5_interest), partial: +r.partial_period === 1 })).filter((r) => r.d >= DOMAIN[0]);
    const ev = eventsIn(E, DOMAIN);
    const f = frame(el, 200, 'Google Trends search interest for GTA 6 and GTA 5 since late August 2026');
    const y = d3.scaleLinear().domain([0, 100]);
    const m = { t: 32, r: 16, b: 28, l: leftMargin(f.svg, y, d3.format('d'), 4) }, iw = f.w - m.l - m.r, ih = f.h - m.t - m.b;
    const x = d3.scaleUtc().domain(DOMAIN).range([0, iw]); y.range([ih, 0]);
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    axes(g, x, y, iw, ih, d3.format('d'), fDay);
    drawEvents(g, x, ev.filter((e) => e.group !== 'gta5'), ih, -22);
    g.append('path').datum(rows).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.a))).style('fill', 'none').style('stroke', dash.colors[2]).style('stroke-width', 2);
    g.append('path').datum(rows).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.b))).style('fill', 'none').style('stroke', dash.colors[3]).style('stroke-width', 1.5).style('stroke-dasharray', '5 3');
    g.append('line').attr('x1', x(LAUNCH)).attr('x2', x(LAUNCH)).attr('y1', -6).attr('y2', ih).style('stroke', 'var(--cds-chart-reference)').style('stroke-dasharray', '2 2');
    const R = new Map(rows.map((r) => [+r.d, r]));
    hover(g, f, el, x, m, iw, ih, (d0) => {
      const d = snapDay(d0), r = R.get(+d), notes = evNotes(ev.filter((e) => e.group !== 'gta5'), d);
      if (!r && !notes.length) return null;
      return { d, title: fDayY(d), lines: r ? ['GTA 6: ' + r.a + (r.partial ? ' (partial day)' : ''), 'GTA 5: ' + r.b] : [], notes };
    });
  });

  // ---- monthly history
  dash.draw('monthly-chart', (el) => {
    const M = ok('players_monthly'), O = ok('outcomes'), U = ok('gtao_updates') || [];
    if (!M || !O) return blank(el);
    const rows = M.map((r) => ({ d: day(r.month), v: num(r.combined_avg), a: num(r.legacy_avg), b: num(r.enhanced_avg) }));
    const mKey = (d) => d.getUTCFullYear() * 12 + d.getUTCMonth();
    const R = state.mrange, end = day('2027-02-01'), first = rows[0].d;
    const start = R === '2013' ? day('2013-09-01') : R === '2015' ? first : day((2026 - +R) + '-11-01');
    const vis = rows.filter((r) => r.d >= start);
    const upd = U.map((u) => ({ d: day(u.date), name: u.name, major: u.tier === 'major' })).filter((u) => u.d >= start);
    const byMonth = d3.group(upd, (u) => mKey(u.d)), RM = new Map(rows.map((r) => [mKey(r.d), r]));
    const o = O.find((r) => r.key === 'GTAV|raw|O2'), fd = day('2026-12-01');
    const f = frame(el, 300, 'GTA V monthly average players on Steam since 2015 with the December 2026 forecast');
    const y = d3.scaleLinear().domain([0, d3.max(vis.map((r) => r.v).concat(o ? [num(o.hi90)] : [])) * 1.03]).nice();
    const m = { t: 26, r: 18, b: 28, l: leftMargin(f.svg, y, fSI, 5) }, iw = f.w - m.l - m.r, ih = f.h - m.t - m.b;
    const x = d3.scaleUtc().domain([start, end]).range([0, iw]); y.range([ih, 0]);
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    axes(g, x, y, iw, ih, fSI, +R && +R <= 3 ? d3.utcFormat("%b '%y") : d3.utcFormat('%Y'), +R && +R <= 3 ? 105 : 70);
    if (start < first) {
      g.append('rect').attr('x', 0).attr('width', x(first)).attr('y', 0).attr('height', ih).style('fill', 'var(--cds-chart-muted)').style('opacity', 0.1);
      g.append('text').attr('class', 'hx-note').attr('x', x(first) / 2).attr('y', ih / 2).attr('text-anchor', 'middle').text(x(first) > 150 ? 'Console only, no Steam data' : 'No Steam data');
    }
    g.append('g').selectAll('line').data(upd.filter((u) => u.major)).join('line')
      .attr('x1', (u) => x(u.d)).attr('x2', (u) => x(u.d)).attr('y1', 0).attr('y2', ih)
      .style('stroke', dash.colors[2]).style('opacity', 0.16);
    g.append('g').selectAll('path').data(upd).join('path')
      .attr('transform', (u) => `translate(${x(u.d)},-12)`)
      .attr('d', (u) => d3.symbol(d3.symbolTriangle, u.major ? 40 : 18)())
      .style('fill', (u) => (u.major ? dash.colors[2] : 'var(--color-bg)')).style('stroke', dash.colors[2]).style('stroke-width', 1.2);
    g.append('path').datum(vis).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.v))).style('fill', 'none').style('stroke', dash.colors[0]).style('stroke-width', 1.8);
    g.append('g').selectAll('circle').data(vis.filter((r) => r.d.getUTCMonth() === 11)).join('circle').attr('cx', (r) => x(r.d)).attr('cy', (r) => y(r.v)).attr('r', 3).style('fill', dash.colors[0]);
    if (o) {
      g.append('line').attr('x1', x(fd)).attr('x2', x(fd)).attr('y1', y(num(o.lo90))).attr('y2', y(num(o.hi90))).style('stroke', dash.colors[1]).style('stroke-width', 3).style('opacity', 0.45);
      g.append('circle').attr('cx', x(fd)).attr('cy', y(num(o.forecast))).attr('r', 4).style('fill', 'var(--color-bg)').style('stroke', dash.colors[1]).style('stroke-width', 2);
    }
    hover(g, f, el, x, m, iw, ih, (d0) => {
      if (o && d0 > day('2026-11-15')) return { d: fd, title: 'Dec 2026, forecast', lines: [fInt(num(o.forecast)) + ' average players', '90% range ' + fInt(num(o.lo90)) + ' to ' + fInt(num(o.hi90))] };
      if (d0 < first) {
        const mo = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth(), 1)), notes = (byMonth.get(mKey(mo)) || []).map((u) => 'GTA Online: ' + u.name + ' (' + fDay(u.d) + ')');
        return { d: mo, title: fMon(mo), lines: ['Console only, before the Steam release'], notes };
      }
      const i = d3.bisector((r) => r.d).center(vis, d0), r = vis[i]; if (!r) return null;
      const pr = RM.get(mKey(r.d) - 1), lines = [fInt(r.v) + ' average players'];
      if (r.b !== null) lines.push('Legacy ' + fInt(r.a) + ', Enhanced ' + fInt(r.b));
      if (pr && pr.v) lines.push(sPct(100 * (r.v / pr.v - 1)) + ' vs previous month');
      const notes = (byMonth.get(mKey(r.d)) || []).map((u) => 'GTA Online: ' + u.name + ' (' + fDay(u.d) + ')');
      return { d: r.d, title: fMon(r.d), lines, notes };
    });
  });

  // ---- backtest table
  dash.draw('bt-rows', (el) => {
    const B = ok('backtest'); el.replaceChildren(); if (!B) return;
    B.forEach((r) => {
      const tr = document.createElement('tr'); tr.setAttribute('data-key', r.key); if (r.selected === 'yes') tr.className = 'hx-sel';
      const cells = [[r.resolution === 'monthly' ? 'Monthly (December)' : 'Daily (fortnight)'], [TARGET[r.target] || r.target], [MODEL[r.model] || r.model],
        [num(r.mae_pct) === null ? '—' : f1(num(r.mae_pct)), 1], [num(r.dec_rmse_pct) === null ? '—' : f1(num(r.dec_rmse_pct)), 1],
        [r.eligible === 'no' ? 'No, uses Trends' : 'Yes'], [r.selected === 'yes' ? 'Selected' : '']];
      cells.forEach(([t, n]) => { const td = document.createElement('td'); td.textContent = t; if (n) td.className = 'hx-num'; tr.append(td); });
      el.append(tr);
    });
  });

  // ---- December backtests
  dash.draw('dec-chart', (el) => {
    const B = ok('backtest_december'); if (!B) return blank(el);
    const tg = state.view === 'adj' ? 'adjusted' : 'raw';
    const rows = B.filter((r) => r.target === tg).map((r) => ({ yr: String(r.year), fc: num(r.forecast_pct), ac: num(r.actual_pct) }));
    const f = frame(el, 220, 'Forecast and actual October to December change in GTA V players for each backtest year');
    const vals = rows.flatMap((r) => [r.fc, r.ac]).filter((v) => v !== null);
    const y = d3.scaleLinear().domain([Math.min(0, d3.min(vals)), d3.max(vals) * 1.08]).nice();
    const yfmt = (v) => sPct(v).replace('.0', '');
    const m = { t: 12, r: 12, b: 28, l: leftMargin(f.svg, y, yfmt, 5) }, iw = f.w - m.l - m.r, ih = f.h - m.t - m.b;
    const x = d3.scalePoint().domain(rows.map((r) => r.yr)).range([0, iw]).padding(0.5); y.range([ih, 0]);
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    g.append('g').attr('class', 'hx-grid').call(d3.axisLeft(y).ticks(5).tickSize(-iw).tickFormat(''));
    g.append('g').attr('class', 'hx-axis').call(d3.axisLeft(y).ticks(5).tickFormat(yfmt).tickSize(0).tickPadding(8)).call((a) => a.select('.domain').remove());
    g.append('g').attr('class', 'hx-axis').attr('transform', `translate(0,${ih})`).call(d3.axisBottom(x).tickSizeOuter(0).tickFormat((v) => (x.step() < 36 ? '\u2019' + v.slice(2) : v)));
    g.append('g').selectAll('line').data(rows.filter((r) => r.ac !== null)).join('line').attr('x1', (r) => x(r.yr)).attr('x2', (r) => x(r.yr)).attr('y1', (r) => y(r.fc)).attr('y2', (r) => y(r.ac)).style('stroke', 'var(--cds-chart-muted)').style('stroke-width', 2);
    g.append('g').selectAll('circle').data(rows).join('circle').attr('cx', (r) => x(r.yr)).attr('cy', (r) => y(r.fc)).attr('r', 4.5).style('fill', 'var(--color-bg)').style('stroke', dash.colors[1]).style('stroke-width', 2);
    g.append('g').selectAll('circle').data(rows.filter((r) => r.ac !== null)).join('circle').attr('cx', (r) => x(r.yr)).attr('cy', (r) => y(r.ac)).attr('r', 4.5).style('fill', dash.colors[0]);
    g.append('g').selectAll('rect').data(rows).join('rect').attr('x', (r) => x(r.yr) - x.step() / 2).attr('width', x.step()).attr('y', 0).attr('height', ih).style('fill', 'transparent')
      .on('pointermove', (evt, r) => showTip(f, el, m.l + x(r.yr), m.t + d3.pointer(evt)[1], 'Oct to Dec ' + r.yr, ['Forecast: ' + sPct(r.fc), r.ac === null ? 'Actual: not yet known' : 'Actual: ' + sPct(r.ac)]))
      .on('pointerleave', () => f.tip.style('display', 'none'));
  });

  // ---- outcome table (GTA V only)
  dash.draw('oc-rows', (el) => {
    const O = ok('outcomes'); el.replaceChildren(); if (!O) return;
    const ord = { adjusted: 0, raw: 1 }, oo = { O1: 0, O2: 1, O2_sensitivity_clim: 2 };
    O.filter((r) => r.unit === 'GTAV').sort((a, b) => ord[a.target] - ord[b.target] || oo[a.outcome] - oo[b.outcome]).forEach((r) => {
      const tr = document.createElement('tr'); tr.setAttribute('data-key', r.key);
      const nf = r.target === 'raw' ? fInt : f1, gap = num(r.gap_pct), rank = num(r.placebo_rank);
      const cells = [[OUTCOME[r.outcome] || r.outcome], [TARGET[r.target] || r.target], [MODEL[r.model] || r.model], [nf(num(r.forecast)), 1], [nf(num(r.lo90)), 1], [nf(num(r.hi90)), 1],
        [gap === null ? '—' : sPct(gap), 1], [rank === null ? '—' : String(rank), 1], [r.verdict || 'Awaiting data']];
      cells.forEach(([t, n]) => { const td = document.createElement('td'); td.textContent = t; if (n) td.className = 'hx-num'; tr.append(td); });
      el.append(tr);
    });
  });

  // ---- daily gap
  dash.draw('gap-chart', (el) => {
    const T = ok('tracker'); if (!T) return blank(el);
    const adj = state.view === 'adj';
    const rows = T.map((r) => ({ d: day(r.date), gap: num(adj ? r.adj_gap_pct : r.gap_pct), mean: num(adj ? r.adj_mean_gap_pct : r.mean_gap_pct), phase: r.phase })).filter((r) => r.gap !== null);
    if (!rows.length) return blank(el);
    const f = frame(el, 220, 'Daily percent gap between actual and forecast GTA V players since the freeze');
    const ext = d3.extent(rows.flatMap((r) => [r.gap, r.mean === null ? 0 : r.mean]).concat([0]));
    const y = d3.scaleLinear().domain([ext[0] - 1, ext[1] + 1]).nice();
    const yfmt = (v) => sPct(v).replace('.0', '');
    const m = { t: 12, r: 16, b: 28, l: leftMargin(f.svg, y, yfmt, 5) }, iw = f.w - m.l - m.r, ih = f.h - m.t - m.b;
    const x = d3.scaleUtc().domain([day('2026-11-15'), d3.utcDay.offset(d3.max(rows, (r) => r.d), 1)]).range([0, iw]); y.range([ih, 0]);
    const bw = Math.max(2, Math.min(18, iw / (d3.utcDay.count(x.domain()[0], x.domain()[1]) + 1) - 2));
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    axes(g, x, y, iw, ih, yfmt, fDay, 70);
    g.append('g').selectAll('rect').data(rows).join('rect').attr('x', (r) => x(r.d) - bw / 2).attr('width', bw).attr('y', (r) => y(Math.max(0, r.gap))).attr('height', (r) => Math.abs(y(r.gap) - y(0)))
      .style('fill', (r) => (r.phase === 'fortnight' ? dash.colors[0] : 'var(--cds-chart-muted)'));
    g.append('line').attr('x1', 0).attr('x2', iw).attr('y1', y(0)).attr('y2', y(0)).style('stroke', 'var(--cds-chart-axis)');
    const mr = rows.filter((r) => r.mean !== null);
    g.append('path').datum(mr).attr('d', d3.line().x((r) => x(r.d)).y((r) => y(r.mean))).style('fill', 'none').style('stroke', dash.colors[1]).style('stroke-width', 2);
    if (mr.length) g.append('text').attr('class', 'hx-note').attr('x', Math.min(iw - 4, x(mr[mr.length - 1].d) + 6)).attr('y', y(mr[mr.length - 1].mean) - 6).attr('text-anchor', x(mr[mr.length - 1].d) > iw - 150 ? 'end' : 'start').text('Running mean, fortnight');
    const R = new Map(rows.map((r) => [+r.d, r]));
    hover(g, f, el, x, m, iw, ih, (d0) => {
      const d = snapDay(d0), r = R.get(+d); if (!r) return null;
      const ph = { 'pre-launch': 'Before launch', fortnight: 'Launch fortnight', december: 'December, judged only as a full month' }[r.phase] || r.phase;
      return { d, title: fDayY(d), lines: ['Gap: ' + sPct(r.gap)].concat(r.mean !== null ? ['Running mean: ' + sPct(r.mean)] : []), notes: [ph] };
    });
  });

  // ---- placebo strip
  dash.draw('placebo-chart', (el) => {
    const O = ok('outcomes'); if (!O) return blank(el);
    const tg = state.view === 'adj' ? 'adjusted' : 'raw';
    const rows = O.filter((r) => r.target === tg && (r.outcome === 'O1' || r.outcome === 'O2') && r.role !== 'sibling' && num(r.z) !== null).map((r) => ({ o: r.outcome, z: num(r.z), name: r.name, me: r.unit === 'GTAV', gap: num(r.gap_pct) }));
    if (!rows.length) return blank(el);
    const os = ['O1', 'O2'].filter((o) => rows.some((r) => r.o === o));
    const f = frame(el, 60 + 56 * os.length, 'Standardized forecast gaps for GTA V and the 18 placebo games');
    const yb = d3.scaleBand().domain(os).range([0, 56 * os.length]).padding(0.3);
    const lab = (o) => OUTCOME[o];
    const probe = f.svg.append('text').attr('class', 'hx-note').text('Launch fortnight'); const lw = Math.ceil(probe.node().getComputedTextLength()) + 14; probe.remove();
    const m = { t: 12, r: 18, b: 36, l: lw }, iw = f.w - m.l - m.r, ih = 56 * os.length;
    const mx = Math.max(2, d3.max(rows, (r) => Math.abs(r.z))) * 1.08;
    const x = d3.scaleLinear().domain([-mx, mx]).range([0, iw]);
    const g = f.svg.append('g').attr('transform', `translate(${m.l},${m.t})`);
    g.append('g').attr('class', 'hx-axis').attr('transform', `translate(0,${ih})`).call(d3.axisBottom(x).ticks(Math.max(3, Math.floor(iw / 80))).tickSizeOuter(0));
    g.append('text').attr('class', 'hx-note').attr('x', iw / 2).attr('y', ih + 32).attr('text-anchor', 'middle').text('Gap divided by each game’s own typical forecast error');
    g.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', ih).style('stroke', 'var(--cds-chart-reference)');
    os.forEach((o) => g.append('text').attr('class', 'hx-note').attr('x', -10).attr('y', yb(o) + yb.bandwidth() / 2 + 4).attr('text-anchor', 'end').text(lab(o)));
    g.append('g').selectAll('circle').data(rows.slice().sort((a, b) => a.me - b.me)).join('circle').attr('cx', (r) => x(r.z)).attr('cy', (r) => yb(r.o) + yb.bandwidth() / 2).attr('r', (r) => (r.me ? 7 : 5))
      .style('fill', (r) => (r.me ? dash.colors[0] : 'var(--cds-chart-muted)')).style('opacity', (r) => (r.me ? 1 : 0.6))
      .on('pointermove', (evt, r) => showTip(f, el, m.l + x(r.z), m.t + yb(r.o), r.name, ['Standardized gap: ' + d3.format('+.2f')(r.z), 'Actual vs forecast: ' + sPct(r.gap)], [lab(r.o)]))
      .on('pointerleave', () => f.tip.style('display', 'none'));
  });
})();
