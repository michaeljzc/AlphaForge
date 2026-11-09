/* AlphaForge local console — vanilla JS + ECharts */
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));

const VIEW_META = {
  overview: ['总览', '数据底座 → 因子闸门 → 组合构建 → A 股回测 → 事件截面'],
  factors: ['因子库', '表达式即代码 · 月度 IC 闸门 · 点击任意因子查看完整画像'],
  backtest: ['组合回测', 'IC 定向加权 · Top-N · 行业中性 · A 股约束撮合'],
  events: ['T0 事件', '放量启动样本 · 事件截面 IC · 60 日路径标签'],
  mining: ['GP 挖掘', '遗传规划搜索 · 风格中性化适应度 · Train/Valid/Test 衰减'],
  qlib: ['Qlib 原生', 'LGBModel · R 记录器 · TopkDropout · SimulatorExecutor'],
  sources: ['数据源', 'Tushare / 同花顺 iFinD / 通联 DataYes 状态与探活'],
};
const state = { overview: null, factors: [], library: null, loaded: {}, chartIds: new Set() };

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isNum = (x) => x !== null && x !== undefined && !Number.isNaN(Number(x));
const fmtPct = (x, d = 1) => isNum(x) ? (Number(x) * 100).toFixed(d) + '%' : '—';
const fmtNum = (x, d = 3) => isNum(x) ? Number(x).toFixed(d) : '—';
const clsNum = (x) => !isNum(x) ? '' : Number(x) > 0 ? 'pos' : Number(x) < 0 ? 'neg' : '';
const badge = (v) => `<span class="badge ${v === 'PASS' ? 'pass' : v === 'WATCH' ? 'watch' : 'reject'}">${esc(v || '—')}</span>`;

function toast(msg, ms = 2600) {
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('show'), ms);
}
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) {
    let detail = r.statusText;
    try { const j = await r.json(); detail = j.detail || j.error || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}
function kpis(el, items) {
  el.innerHTML = items.map(([k, v, s]) => `<div class="kpi"><div class="k">${esc(k)}</div><div class="v">${v}</div><div class="s">${esc(s || '')}</div></div>`).join('');
}
function empty(el, text = '暂无数据，请先运行 alphaforge demo') {
  el.innerHTML = `<div class="empty">${esc(text)}</div>`;
}

/* ---------------- echarts ---------------- */
function ec(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (!echarts.getInstanceByDom(el)) echarts.init(el, null, { renderer: 'canvas' });
  state.chartIds.add(id);
  return echarts.getInstanceByDom(el);
}
function resizeAll() { state.chartIds.forEach((id) => { const c = echarts.getInstanceByDom(document.getElementById(id)); if (c) c.resize(); }); }
window.addEventListener('resize', resizeAll);

function lineOpt(dates, series, opt = {}) {
  return {
    animationDuration: 350,
    grid: { left: 52, right: 18, top: 34, bottom: 32 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' }, valueFormatter: (v) => isNum(v) ? Number(v).toFixed(3) : v },
    legend: { top: 0, right: 6, itemWidth: 10, itemHeight: 8, textStyle: { fontSize: 11, color: '#5B6675' } },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLine: { lineStyle: { color: '#D8E0E9' } }, axisLabel: { color: '#6B7280', fontSize: 10, formatter: (v) => String(v).slice(2, 7) }, axisTick: { show: false } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#6B7280', fontSize: 10, formatter: opt.pct ? (v) => (v * 100).toFixed(0) + '%' : undefined }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
    series: series.map((s) => ({
      name: s.name, type: 'line', data: s.data, showSymbol: false, smooth: !!s.smooth,
      lineStyle: { width: s.width || 2, color: s.color, type: s.dash ? 'dashed' : 'solid' },
      itemStyle: { color: s.color }, areaStyle: s.area ? { color: s.area } : undefined,
    })),
  };
}
function barOpt(labels, values, opt = {}) {
  return {
    animationDuration: 300,
    grid: { left: 52, right: 16, top: 22, bottom: 34 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => opt.pct ? fmtPct(v, 2) : fmtNum(v, 4) },
    xAxis: { type: 'category', data: labels, axisLabel: { color: '#6B7280', fontSize: 10, interval: labels.length > 16 ? 1 : 0, rotate: opt.rotate || 0 }, axisLine: { lineStyle: { color: '#D8E0E9' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#6B7280', fontSize: 10, formatter: opt.pct ? (v) => (v * 100).toFixed(2) + '%' : undefined }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
    series: [{ type: 'bar', data: values.map((v) => ({ value: v, itemStyle: { color: !isNum(v) ? '#CBD5E1' : v >= 0 ? (opt.color || '#0969DA') : '#CF222E', borderRadius: [3, 3, 0, 0] } })), barMaxWidth: 26 }],
  };
}

/* ---------------- overview ---------------- */
async function loadOverview() {
  const [d, bt] = await Promise.all([api('/api/overview'), api('/api/backtest').catch(() => null)]);
  state.overview = d;
  const p = d.panel || {};
  const m = d.backtest_metrics || {};
  const ev = d.events?.summary || {};
  const audit = d.events?.audit || {};
  kpis($('#kpi'), [
    ['数据区间', `${(p.start || '—').slice(2)} ~ ${(p.end || '—').slice(2)}`, `${p.n_dates || '—'} 个交易日`],
    ['股票池', `${p.n_symbols || '—'} 只`, 'CSI300 + CSI500 历史成分'],
    ['因子库', `${d.demo?.factor_library ?? d.artifacts?.factors ?? '—'} 个`, '内置 + Alpha158'],
    ['T0 事件', `${ev.n_events ?? '—'}`, '放量启动样本'],
    ['组合年化 / 夏普', `${fmtPct(m.cagr)} / ${fmtNum(m.sharpe, 2)}`, '2024–2026 样本外'],
    ['防泄露审计', audit.ok ? '通过' : '待查', audit.ok ? `max diff ${fmtNum(audit.max_abs_diff, 6)}` : '截断重算 + 标签对齐'],
  ]);

  if (bt?.dates?.length) {
    const eq = bt.equity || []; const bench = bt.benchmark || [];
    const base = eq[0] || 1; const bbase = bench[0] || 1;
    const series = [{ name: '策略', color: '#0969DA', width: 2, data: eq.map((v) => v / base) }];
    if (bench.length) series.push({ name: '沪深300', color: '#8B949E', width: 1.3, data: bench.map((v) => v / bbase) });
    ec('chart-overview-equity')?.setOption(lineOpt(bt.dates, series), true);
  } else empty($('#chart-overview-equity'));

  const tiers = ev.tiers || {};
  ec('chart-overview-events')?.setOption({
    grid: { left: 48, right: 12, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['强正', '弱正', '负样本'], axisLabel: { fontSize: 11, color: '#6B7280' }, axisLine: { lineStyle: { color: '#D8E0E9' } }, axisTick: { show: false } },
    yAxis: { type: 'log', axisLabel: { fontSize: 10, color: '#6B7280' }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
    series: [{ type: 'bar', barMaxWidth: 38, data: [
      { value: tiers.strong || 0, itemStyle: { color: '#BF3989', borderRadius: [4, 4, 0, 0] } },
      { value: tiers.weak || 0, itemStyle: { color: '#8250DF', borderRadius: [4, 4, 0, 0] } },
      { value: tiers.negative || 0, itemStyle: { color: '#94A3B8', borderRadius: [4, 4, 0, 0] } }],
      label: { show: true, position: 'top', fontSize: 11, color: '#374151' } }],
  }, true);
  const note = $('#overview-note');
  note.innerHTML = `最佳因子 <b>${esc(state.overview?.demo?.best_factor || '—')}</b>` +
    ` · 当前数据 <b>${p.n_symbols || '—'}</b> 只 / <b>${p.n_dates || '—'}</b> 个交易日` +
    ` · 事件组合 <b>${fmtPct(d.events?.summary?.mean_label_ret)}</b> 平均 60 日收益` +
    ` · 运行 <code>alphaforge demo</code> 可刷新全部指标。`;

  const rows = (d.factors || []).filter((f) => (f.coverage ?? 1) >= 0.5).slice(0, 8);
  $('#overview-factors').innerHTML = rows.length ? rows.map((f) => `
    <div class="mini-row" data-factor="${esc(f.name)}">
      <div class="nm" title="${esc(f.description || '')}">${esc(f.name)}</div>
      <div class="${clsNum(f.ic)}">IC ${fmtNum(f.ic, 3)}</div>
      <div class="${clsNum(f.dir_net ?? f.net_ann)}">${fmtPct(f.dir_net ?? f.net_ann)}</div>
      <div>${badge(f.verdict)}</div>
    </div>`).join('') : '<div class="placeholder">暂无因子快照</div>';
  $$('#overview-factors .mini-row').forEach((el) => el.onclick = () => openFactor(el.dataset.factor));
}

/* ---------------- factors ---------------- */
function factorRows(list) {
  return list.map((f) => `<tr class="clickable" data-factor="${esc(f.name)}">
    <td><b>${esc(f.name)}</b><div class="factor-desc" title="${esc(f.description || '')}">${esc(f.description || '')}</div></td>
    <td><span class="badge blue">${esc(f.category || '—')}</span></td>
    <td class="num ${clsNum(f.ic)}">${fmtNum(f.ic, 3)}</td>
    <td class="num ${clsNum(f.icir)}">${fmtNum(f.icir, 2)}</td>
    <td class="num">${fmtPct(f.hit, 0)}</td>
    <td class="num ${clsNum(f.mono)}">${fmtNum(f.mono, 2)}</td>
    <td class="num ${clsNum(f.ls_ann)}">${fmtPct(f.ls_ann)}</td>
    <td class="num ${clsNum(f.dir_net)}">${fmtPct(f.dir_net)}</td>
    <td class="num">${fmtNum(f.turnover, 2)}</td>
    <td class="num">${fmtPct(f.coverage)}</td>
    <td>${badge(f.verdict)}</td>
  </tr>`).join('');
}
function renderFactorTable() {
  const scope = $('#factor-scope')?.value || 'evaluated';
  const q = ($('#factor-search')?.value || '').toLowerCase();
  const cat = $('#factor-category')?.value || '';
  if (scope === 'library') {
    const lib = state.library || [];
    const list = lib.filter((f) => (!cat || f.category === cat) &&
      (!q || `${f.name} ${f.description || ''} ${f.expression || ''}`.toLowerCase().includes(q)));
    $('#factor-table').innerHTML = list.length ? `<table><thead><tr>
      <th>因子</th><th>类别</th><th>说明</th><th>表达式</th><th>状态</th>
    </tr></thead><tbody>${list.map((f) => `<tr class="clickable" data-lib="${esc(f.name)}">
      <td><b>${esc(f.name)}</b></td>
      <td><span class="badge blue">${esc(f.category || '—')}</span></td>
      <td><div class="lib-desc" title="${esc(f.description || '')}">${esc(f.description || '—')}</div></td>
      <td><code style="font-size:11px;display:inline-block;max-width:330px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom">${esc((f.expression || '').slice(0, 90))}</code></td>
      <td>${f.evaluated ? '<span class="badge pass">已评估</span>' : '<span class="badge">评估</span>'}</td>
    </tr>`).join('')}</tbody></table>` : '<div class="placeholder">没有匹配的因子</div>';
    $$('#factor-table tr[data-lib]').forEach((el) => el.onclick = () => openLibraryItem(el.dataset.lib));
    return;
  }
  const list = state.factors.filter((f) => (!cat || f.category === cat) &&
    (!q || `${f.name} ${f.description || ''} ${f.expression || ''}`.toLowerCase().includes(q)));
  $('#factor-table').innerHTML = list.length ? `<table><thead><tr>
    <th>因子</th><th>类别</th><th>IC(月)</th><th>ICIR</th><th>命中</th><th>单调</th><th>多空</th><th>方向扣费</th><th>换手</th><th>覆盖</th><th>闸门</th>
  </tr></thead><tbody>${factorRows(list)}</tbody></table>` : '<div class="placeholder">没有匹配的因子</div>';
  $$('#factor-table tr[data-factor]').forEach((el) => el.onclick = () => openFactor(el.dataset.factor));
}

async function loadLibrary() {
  if (!state.library) {
    const d = await api('/api/library');
    state.library = d.factors || [];
  }
  const cats = [...new Set(state.library.map((f) => f.category).filter(Boolean))].sort();
  $('#factor-category').innerHTML = '<option value="">全部类别</option>' + cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  renderFactorTable();
}

function openLibraryItem(name) {
  const item = (state.library || []).find((f) => f.name === name);
  if (!item) return;
  const body = $('#drawer-body');
  $('#drawer-title').textContent = item.name;
  $('#drawer-sub').textContent = item.description || item.expression;
  body.innerHTML = `<div class="placeholder">正在评估 ${esc(item.name)} …</div>`;
  document.body.classList.add('drawer-open');
  api('/api/factors/evaluate', {
    method: 'POST',
    body: JSON.stringify({ expression: item.expression, name: item.name,
                           description: item.description || '', start: '2021-01-01' }),
  }).then((r) => {
    if (!r.ok) throw new Error(r.error || '评估失败');
    renderFactor(r.factor);
  }).catch((e) => { body.innerHTML = `<div class="placeholder">${esc(e.message)}</div>`; });
}

async function loadFactors() {
  const d = await api('/api/factors');
  state.factors = d.factors || [];
  const sel = $('#factor-category');
  sel.innerHTML = '<option value="">全部类别</option>' + (d.categories || []).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
  renderFactorTable();
}
function openFactor(name) {
  const body = $('#drawer-body');
  $('#drawer-title').textContent = name;
  $('#drawer-sub').textContent = '加载中…';
  body.innerHTML = '<div class="placeholder">加载因子快照…</div>';
  document.body.classList.add('drawer-open');
  api(`/api/factors/${encodeURIComponent(name)}`).then((p) => renderFactor(p)).catch((e) => {
    body.innerHTML = `<div class="placeholder">${esc(e.message)}</div>`;
  });
}
function renderFactor(p) {
  const h = p.primary_horizon || 5;
  const ic = p.ic?.[String(h)] || {};
  const q = p.quantile?.long_short || {};
  $('#drawer-title').textContent = p.name;
  $('#drawer-sub').textContent = p.expression;
  const gateRows = Object.values(p.gate?.checks || {}).map((c) => `<tr>
    <td>${esc(c.label)}</td><td class="num">${fmtNum(c.value, 4)}</td><td class="num">${fmtNum(c.threshold, 4)}</td>
    <td>${c.pass ? '<span class="badge pass">通过</span>' : '<span class="badge reject">未通过</span>'}</td></tr>`).join('');
  $('#drawer-body').innerHTML = `
    <div class="chips">${badge(p.verdict)}<span class="badge blue">${esc(p.category || '—')}</span>
      <span class="badge">${esc(p.period?.start || '')} ~ ${esc(p.period?.end || '')}</span>
      <span class="badge">${p.neutralized ? '行业+市值中性' : '未中性化'}</span></div>
    ${p.description ? `<p class="desc-line">${esc(p.description)}</p>` : ""}
    <div class="detail-hero">
      <div><span>月度 IC</span><b class="${clsNum(ic.mean_monthly)}">${fmtNum(ic.mean_monthly, 4)}</b></div>
      <div><span>月度 ICIR</span><b class="${clsNum(ic.icir_monthly)}">${fmtNum(ic.icir_monthly, 2)}</b></div>
      <div><span>方向命中率</span><b>${fmtPct(ic.hit_rate_monthly)}</b></div>
      <div><span>分层单调性</span><b class="${clsNum(p.quantile?.monotonicity)}">${fmtNum(p.quantile?.monotonicity, 2)}</b></div>
      <div><span>多空年化</span><b class="${clsNum(q.annualized)}">${fmtPct(q.annualized)}</b></div>
      <div><span>方向扣费年化</span><b class="${clsNum(q.directional_net_annualized)}">${fmtPct(q.directional_net_annualized)}</b></div>
      <div><span>换手</span><b>${fmtNum(p.turnover?.mean, 2)}</b></div>
      <div><span>覆盖率</span><b>${fmtPct(p.coverage)}</b></div>
    </div>
    <div class="section-title">IC 序列（${h} 日）</div><div class="echarts" id="f-ic"></div>
    <div class="section-title">五分组平均收益</div><div class="echarts" id="f-qbar"></div>
    <div class="section-title">分层净值</div><div class="echarts" id="f-curves"></div>
    <div class="section-title">闸门检查</div>
    <table><thead><tr><th>检查</th><th>值</th><th>阈值</th><th>结果</th></tr></thead><tbody>${gateRows}</tbody></table>
    <div class="section-title">表达式</div><pre class="codeblock">${esc(p.expression)}</pre>`;
  setTimeout(() => {
    const icc = p.ic_curves?.[String(h)] || { dates: [], values: [] };
    ec('f-ic')?.setOption(lineOpt(icc.dates, [{ name: 'IC', color: '#0969DA', data: icc.values }]), true);
    const qm = p.quantile_mean || {};
    ec('f-qbar')?.setOption(barOpt(Object.keys(qm), Object.values(qm), { pct: true, color: '#0969DA' }), true);
    const cd = p.curves?.q?.dates || [];
    const cols = Object.keys(p.curves?.q?.series || {});
    const colors = ['#0969DA', '#06B6D4', '#94A3B8', '#8250DF', '#BF3989'];
    const series = cols.map((c, i) => ({ name: c, color: colors[i % colors.length], width: 1.5, data: p.curves.q.series[c] }));
    if (p.curves?.ls?.values?.length) series.push({ name: '多空', color: '#CF222E', width: 2, dash: true, data: p.curves.ls.values });
    ec('f-curves')?.setOption(lineOpt(cd, series), true);
  }, 30);
}

/* ---------------- backtest ---------------- */
async function loadBacktest() {
  const d = await api('/api/backtest');
  const m = d.metrics || {};
  kpis($('#bt-kpi'), [
    ['总收益', `<span class="${clsNum(m.total_return)}">${fmtPct(m.total_return)}</span>`, '样本外'],
    ['年化收益', `<span class="${clsNum(m.cagr)}">${fmtPct(m.cagr)}</span>`, `夏普 ${fmtNum(m.sharpe, 2)}`],
    ['最大回撤', `<span class="neg">${fmtPct(m.max_drawdown)}</span>`, `Calmar ${fmtNum(m.calmar, 2)}`],
    ['超额 / IR', `<span class="${clsNum(m.excess_return)}">${fmtPct(m.excess_return)}</span>`, `IR ${fmtNum(m.information_ratio, 2)}`],
  ]);
  $('#bt-period').textContent = `${String(d.start || '').slice(0, 10)} ~ ${String(d.end || '').slice(0, 10)}`;
  const eq = d.equity || [], bench = d.benchmark || [], dates = d.dates || [];
  if (eq.length) {
    const base = eq[0] || 1, bbase = bench[0] || 1;
    const series = [{ name: '策略', color: '#0969DA', width: 2, data: eq.map((v) => v / base) }];
    if (bench.length) series.push({ name: '沪深300', color: '#8B949E', width: 1.3, data: bench.map((v) => v / bbase) });
    ec('chart-bt-equity')?.setOption(lineOpt(dates, series), true);
    let peak = -Infinity; const dd = eq.map((v) => { peak = Math.max(peak, v); return v / peak - 1; });
    ec('chart-bt-dd')?.setOption(lineOpt(dates, [{ name: '回撤', color: '#CF222E', width: 1.2, area: 'rgba(207,34,46,.12)', data: dd }], { pct: true }), true);
  } else { empty($('#chart-bt-equity')); empty($('#chart-bt-dd')); }
  const monthly = m.monthly_returns || {};
  const keys = Object.keys(monthly).sort();
  ec('chart-bt-monthly')?.setOption(barOpt(keys.map((k) => k.slice(2, 7)), keys.map((k) => monthly[k]), { pct: true, rotate: 45 }), true);
}

/* ---------------- events ---------------- */
async function loadEvents() {
  const d = await api('/api/events');
  const s = d.summary || {}, a = d.audit || {}, bt = d.backtest || {};
  kpis($('#ev-kpi'), [
    ['事件数', `${s.n_events ?? '—'}`, `${s.codes ?? '—'} 只股票`],
    ['强正样本', `${s.tiers?.strong ?? 0}`, `占比 ${fmtPct(s.strong_rate, 2)}`],
    ['弱正样本', `${s.tiers?.weak ?? 0}`, `占比 ${fmtPct(s.weak_rate, 1)}`],
    ['事件组合年化', `<span class="${clsNum(bt.cagr)}">${fmtPct(bt.cagr)}</span>`, `最大回撤 ${fmtPct(bt.max_drawdown)}`],
  ]);
  const tiers = s.tiers || {};
  ec('chart-ev-tiers')?.setOption(barOpt(['强正', '弱正', '负样本'], [tiers.strong || 0, tiers.weak || 0, tiers.negative || 0], { color: '#8250DF' }), true);
  const ic = (d.ic || []).slice(0, 10);
  if (ic.length) {
    ec('chart-ev-ic')?.setOption({
      grid: { left: 120, right: 24, top: 12, bottom: 28 },
      tooltip: { trigger: 'axis', valueFormatter: (v) => fmtNum(v, 4) },
      xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#6B7280' }, splitLine: { lineStyle: { color: '#EEF2F6' } } },
      yAxis: { type: 'category', data: ic.map((x) => x.feature), axisLabel: { fontSize: 10, color: '#4B5563' }, axisLine: { show: false }, axisTick: { show: false } },
      series: [{ type: 'bar', data: ic.map((x) => ({ value: x.ic, itemStyle: { color: x.ic >= 0 ? '#1A7F37' : '#CF222E', borderRadius: 2 } })), barMaxWidth: 16 }],
    }, true);
  } else empty($('#chart-ev-ic'));
  if (bt.equity?.length) {
    const base = bt.equity[0] || 1;
    ec('chart-ev-equity')?.setOption(lineOpt(bt.equity_dates, [{ name: '事件组合', color: '#8250DF', width: 2, data: bt.equity.map((v) => v / base) }]), true);
  } else empty($('#chart-ev-equity'));
  $('#ev-table').innerHTML = ic.length ? `<table><thead><tr><th>因子</th><th>事件 IC</th><th>事件 ICIR</th><th>截面数</th><th>命中率</th><th>t 值</th></tr></thead><tbody>${
    ic.map((x) => `<tr><td>${esc(x.feature)}</td><td class="num ${clsNum(x.ic)}">${fmtNum(x.ic, 4)}</td><td class="num">${fmtNum(x.icir, 2)}</td><td class="num">${x.n_sections ?? '—'}</td><td class="num">${fmtPct(x.hit_rate)}</td><td class="num">${fmtNum(x.t_stat, 2)}</td></tr>`).join('')
  }</tbody></table>` : '<div class="placeholder">暂无事件 IC</div>';
  const audit = $('#ev-audit');
  audit.className = 'audit' + (a.ok ? '' : ' bad');
  audit.innerHTML = `<b>防泄露审计：${a.ok ? '通过' : '未通过'}</b> · 截断重算最大差异 <code>${fmtNum(a.max_abs_diff, 6)}</code> · 财务 PIT 差异 <code>${fmtNum(a.pit_max_diff, 8)}</code> · 标签对齐 ${a.label_alignment_ok ? '正常' : '异常'} · 已检查 ${a.n_evaluated || 0} 个特征点`;
}

/* ---------------- mining ---------------- */
async function loadMining() {
  const d = await api('/api/gp');
  const hist = d.history || [];
  $('#gp-evals').textContent = `${d.evaluations ?? '—'} 次评估 · ${d.elapsed_sec ?? '—'}s`;
  if (hist.length) {
    ec('chart-gp')?.setOption(lineOpt(hist.map((x) => `G${x.generation}`), [
      { name: '最优适应度', color: '#8250DF', width: 2, data: hist.map((x) => x.best_fitness) },
      { name: '|IC|', color: '#0969DA', width: 1.4, dash: true, data: hist.map((x) => Math.abs(x.best_ic || 0)) },
    ]), true);
  } else empty($('#chart-gp'), '尚未运行 GP');
  const rows = d.evaluated || d.hall_of_fame || [];
  $('#gp-table').innerHTML = rows.length ? `<table><thead><tr><th>表达式</th><th>Train IC</th><th>Valid IC</th><th>Test IC</th><th>节点</th><th>Valid 闸门</th></tr></thead><tbody>${
    rows.map((x) => `<tr><td class="mono" style="white-space:normal;max-width:520px">${esc(x.expression)}</td><td class="num ${clsNum(x.train_ic)}">${fmtNum(x.train_ic, 4)}</td><td class="num ${clsNum(x.valid_ic)}">${fmtNum(x.valid_ic, 4)}</td><td class="num ${clsNum(x.test_ic)}">${fmtNum(x.test_ic, 4)}</td><td class="num">${x.size ?? '—'}</td><td>${badge(x.valid_verdict || 'REJECT')}</td></tr>`).join('')
  }</tbody></table>` : '<div class="placeholder">尚无候选因子</div>';
}

/* ---------------- qlib ---------------- */
async function loadQlib() {
  const d = await api('/api/qlib');
  const data = d.data || {}, n = d.native || {};
  const ic = n.ic || {}, nb = n.qlib_backtest || {}, af = n.alphaforge_backtest || {};
  kpis($('#qlib-kpi'), [
    ['Qlib 数据', `${data.symbols ?? '—'} 只`, `${data.dates ?? '—'} 个交易日`],
    ['字段校验', fmtNum(data.max_abs_diff, 8), 'max |diff|'],
    ['Alpha158', `${data.alpha158 ?? '—'} 个`, '表达式已接入'],
    ['原生回测年化', `<span class="${clsNum(nb.annualized_return)}">${fmtPct(nb.annualized_return)}</span>`, `IR ${fmtNum(nb.information_ratio, 2)}`],
  ]);
  $('#qlib-parity').innerHTML = [
    ['导出股票', `${data.symbols ?? '—'} 只`], ['交易日', `${data.dates ?? '—'}`],
    ['基准', (data.benchmarks || []).join(', ') || 'SH000300'], ['max|diff|', fmtNum(data.max_abs_diff, 8)],
  ].map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  if (nb.equity?.length) {
    const series = [{ name: 'Qlib 原生', color: '#8250DF', width: 2, data: nb.equity }];
    if (nb.benchmark_equity?.length) series.push({ name: 'SH000300', color: '#8B949E', width: 1.3, data: nb.benchmark_equity });
    ec('chart-qlib-equity')?.setOption(lineOpt(nb.dates, series), true);
  } else empty($('#chart-qlib-equity'), '运行 alphaforge qlib native 生成');
  const rows = [
    ['Qlib DatasetH 兼容数据集', `${n.dataset?.rows ?? '—'} 行 / ${n.dataset?.symbols ?? '—'} 只 / ${n.dataset?.features ?? '—'} 特征`],
    ['LGBModel 月度 IC / ICIR', `${fmtNum(ic.monthly_mean, 4)} / ${fmtNum(ic.monthly_icir, 2)}`],
    ['Qlib 原生总收益', fmtPct(nb.total_return)],
    ['Qlib 原生年化 / 夏普', `${fmtPct(nb.annualized_return)} / ${fmtNum(nb.sharpe, 2)}`],
    ['Qlib 原生最大回撤', fmtPct(nb.max_drawdown)],
    ['Qlib 原生平均日换手', fmtPct(nb.turnover)],
    ['Qlib 原生累计成本', fmtPct(nb.cost)],
    ['AlphaForge A 股撮合年化 / 夏普', `${fmtPct(af.cagr)} / ${fmtNum(af.sharpe, 2)}`],
    ['AlphaForge 最大回撤 / IR', `${fmtPct(af.max_drawdown)} / ${fmtNum(af.information_ratio, 2)}`],
  ];
  $('#qlib-table').innerHTML = `<table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${esc(v)}</td></tr>`).join('')}</tbody></table>`;
}

/* ---------------- sources ---------------- */
function sourceCard(s) {
  const probe = s.probe ? `<div class="probe ${s.probe.ok ? 'ok' : 'bad'}">${s.probe.ok ? '✓ ' : '✕ '}${esc(s.probe.message)} · ${s.probe.latency_ms}ms</div>` : '';
  return `<div class="source" data-source="${esc(s.id)}">
    <div class="top"><h4>${esc(s.name)}</h4><span class="badge ${s.configured ? 'pass' : 'reject'}">${s.configured ? '已配置' : '未配置'}</span></div>
    <div class="role">${esc(s.role)}</div>
    <div class="meta"><span>Token：${esc(s.token || '—')}</span><button class="btn small probe-btn" data-probe="${esc(s.id)}" ${s.configured ? '' : 'disabled'}>测试连接</button></div>
    <div class="chips" style="margin:9px 0 0">${(s.capabilities || []).slice(0, 5).map((c) => `<span class="badge">${esc(c)}</span>`).join('')}</div>
    ${probe}
  </div>`;
}
function bindProbe() {
  $$('.probe-btn').forEach((btn) => {
    if (btn.disabled) return;
    btn.onclick = async () => {
      const id = btn.dataset.probe; btn.disabled = true; btn.textContent = '测试中…';
      try {
        const r = await api(`/api/sources/${id}/probe`, { method: 'POST' });
        toast(`${id}: ${r.ok ? '连接成功' : '连接失败'} · ${r.latency_ms}ms`);
      } catch (e) { toast(`${id}: ${e.message}`); }
      const s2 = await api('/api/sources');
      $('#source-cards').innerHTML = (s2.sources || []).map(sourceCard).join('');
      bindProbe();
    };
  });
}
async function loadSources() {
  const [s, d] = await Promise.all([api('/api/sources'), api('/api/data/summary').catch(() => null)]);
  $('#source-cards').innerHTML = (s.sources || []).map(sourceCard).join('');
  bindProbe();
  if (d?.counts) {
    $('#data-counts').innerHTML = `<table><thead><tr><th>表</th><th>行数</th></tr></thead><tbody>${
      Object.entries(d.counts).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v === null ? '—' : Number(v).toLocaleString()}</td></tr>`).join('')
    }</tbody></table>`;
  } else empty($('#data-counts'));
}

/* ---------------- navigation ---------------- */
const LOADERS = { overview: loadOverview, factors: loadFactors, backtest: loadBacktest, events: loadEvents, mining: loadMining, qlib: loadQlib, sources: loadSources };
async function switchView(view, push = true) {
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${view}`));
  const [title, sub] = VIEW_META[view] || ['', ''];
  $('#page-title').textContent = title; $('#page-sub').textContent = sub;
  if (!state.loaded[view]) {
    try { await LOADERS[view]?.(); state.loaded[view] = true; }
    catch (e) { toast(`${title}: ${e.message}`); }
  }
  if (push && location.hash !== `#${view}`) history.replaceState(null, '', `#${view}`);
  setTimeout(resizeAll, 40);
}
function refreshCurrent() {
  const active = $('.nav-item.active')?.dataset.view || 'overview';
  state.loaded = {}; state.library = null; LOADERS[active]?.().catch((e) => toast(e.message));
  toast('已刷新');
}

/* ---------------- drawer / init ---------------- */
function closeDrawer() { document.body.classList.remove('drawer-open'); }
$('#drawer-close').onclick = closeDrawer;
$('#drawer-mask').onclick = closeDrawer;
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });

$$('.nav-item').forEach((b) => b.onclick = () => switchView(b.dataset.view));
$$('[data-goto]').forEach((a) => a.onclick = () => switchView(a.dataset.goto));
$('#refresh').onclick = refreshCurrent;
$('#factor-search').oninput = renderFactorTable;
$('#factor-category').onchange = renderFactorTable;
$('#factor-scope').onchange = async (e) => {
  $('#factor-search').value = '';
  $('#factor-category').innerHTML = '<option value="">全部类别</option>';
  try {
    if (e.target.value === 'library') await loadLibrary();
    else await loadFactors();
  } catch (err) { toast(err.message); }
};
$('#eval-btn').onclick = async () => {
  const expr = $('#factor-expr').value.trim();
  if (!expr) { toast('请输入表达式'); return; }
  const btn = $('#eval-btn'); btn.disabled = true; btn.textContent = '评估中…';
  try {
    const r = await api('/api/factors/evaluate', { method: 'POST', body: JSON.stringify({ expression: expr }) });
    if (!r.ok) throw new Error(r.error || '评估失败');
    renderFactor(r.factor); document.body.classList.add('drawer-open');
    toast(`评估完成：${r.factor.name}`);
  } catch (e) { toast(e.message); }
  btn.disabled = false; btn.textContent = '在线评估';
};

(async function init() {
  try {
    await api('/api/health');
    $('#side-status').textContent = '服务在线 · 本地数据';
    $('#side-dot').style.background = '#3FB950';
    $('#asof').textContent = '更新 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const initial = (location.hash || '').replace('#', '');
    await switchView(VIEW_META[initial] ? initial : 'overview');
    const params = new URLSearchParams(location.search);
    if (params.get('scope') === 'library') {
      $('#factor-scope').value = 'library';
      await loadLibrary();
      const cat = params.get('category');
      if (cat) { $('#factor-category').value = cat; renderFactorTable(); }
    }
    const focus = params.get('factor');
    if (focus) setTimeout(() => openFactor(focus), 700);
  } catch (e) {
    $('#side-status').textContent = '无法连接后端';
    $('#side-dot').style.background = '#F85149';
    toast('后端未启动：alphaforge web --port 8787');
  }
})();
