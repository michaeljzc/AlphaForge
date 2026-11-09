"""HTML report builder (self-contained, offline-capable)."""

from __future__ import annotations

import html as html_escape
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Template
from plotly.offline import get_plotlyjs

from alphaforge.config import Config
from alphaforge.utils import fmt_pct, read_json, write_json

BLUE = "#0969DA"
PURPLE = "#8250DF"
CYAN = "#06B6D4"
PINK = "#BF3989"
GREEN = "#1A7F37"
RED = "#CF222E"
GREY = "#8B949E"
GRID = "rgba(31,35,40,0.10)"


def _layout(fig: go.Figure, title: str = "", height: int = 340) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#1F2328"), x=0.01),
        height=height, margin=dict(l=44, r=16, t=44 if title else 16, b=36),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="-apple-system, PingFang SC, Microsoft YaHei, sans-serif", size=12,
                  color="#424A53"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=11)),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    return fig


def _div(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _fmt_pct(x: Any, digits: int = 1) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(v):
        return "-"
    return f"{v * 100:.{digits}f}%"


def _fmt_num(x: Any, digits: int = 3) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(v):
        return "-"
    return f"{v:.{digits}f}"


def _table(df: pd.DataFrame, formats: dict[str, Any], classes: str = "data-table",
           max_rows: int | None = None, index: bool = False) -> str:
    if df is None or df.empty:
        return '<p class="muted">暂无数据</p>'
    out = df.head(max_rows).copy() if max_rows else df.copy()
    for col, fn in formats.items():
        if col in out.columns:
            out[col] = out[col].map(fn)
    return out.to_html(index=index, classes=classes, escape=False, border=0)


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------
def fig_ic(report) -> str:
    ic = report.ic_series.get(report.primary_horizon)
    if ic is None or ic.empty:
        return '<p class="muted">暂无 IC 序列</p>'
    ic = ic.copy()
    ic.index = pd.to_datetime(ic.index)
    roll = ic.rolling(20).mean()
    fig = go.Figure()
    fig.add_bar(x=ic.index, y=ic.to_numpy(), name="IC", marker_color="rgba(9,105,218,0.25)")
    fig.add_scatter(x=roll.index, y=roll.to_numpy(), name="20 期均值", line=dict(color=BLUE, width=2))
    fig.add_hline(y=0, line_color=GREY, line_width=1)
    return _div(_layout(fig, f"IC 序列（{report.primary_horizon} 日）", 320))


def fig_quantile(report) -> str:
    if report.qret is None or report.qret.empty:
        return '<p class="muted">暂无分层数据</p>'
    means = report.qret.mean()
    fig = go.Figure(go.Bar(x=list(means.index), y=means.to_numpy(),
                           marker_color=[BLUE, CYAN, GREY, PURPLE, PINK]))
    fig.add_hline(y=0, line_color=GREY, line_width=1)
    fig.update_yaxes(tickformat=".2%")
    return _div(_layout(fig, "五分组平均收益（按因子排序）", 300))


def fig_curves(report) -> str:
    if report.q_curves is None or report.q_curves.empty:
        return '<p class="muted">暂无净值曲线</p>'
    fig = go.Figure()
    colors = [BLUE, CYAN, GREY, PURPLE, PINK]
    for i, col in enumerate(report.q_curves.columns):
        fig.add_scatter(x=report.q_curves.index, y=report.q_curves[col],
                        name=col, line=dict(color=colors[i % len(colors)], width=1.6))
    if report.ls_curve is not None:
        fig.add_scatter(x=report.ls_curve.index, y=report.ls_curve,
                        name="多空", line=dict(color=RED, width=2, dash="dot"))
    return _div(_layout(fig, "分层累计净值（非重叠持有期）", 340))


def fig_decay(report) -> str:
    hs = sorted(report.ic)
    vals = [report.ic[h].get("mean_monthly", report.ic[h].get("mean")) for h in hs]
    fig = go.Figure(go.Bar(x=[f"{h}D" for h in hs], y=vals, marker_color=BLUE))
    fig.add_hline(y=0, line_color=GREY, line_width=1)
    fig.update_yaxes(tickformat=".3f")
    return _div(_layout(fig, "IC 衰减（不同持有期）", 280))


def fig_corr(corr: pd.DataFrame) -> str:
    if corr is None or corr.empty:
        return '<p class="muted">暂无相关性</p>'
    labels = list(corr.index)
    fig = go.Figure(go.Heatmap(z=corr.to_numpy(), x=labels, y=labels,
                               colorscale=[[0, "#1A7F37"], [0.5, "#FFFFFF"], [1, "#CF222E"]],
                               zmin=-1, zmax=1, colorbar=dict(thickness=10)))
    fig.update_layout(height=max(360, 24 * len(labels)), margin=dict(l=120, b=100))
    return _div(_layout(fig, "因子截面相关性（平均 Rank 相关）", max(360, 24 * len(labels))))


def fig_backtest(equity: pd.Series, benchmark: pd.Series | None) -> str:
    fig = go.Figure()
    eq = equity / equity.iloc[0]
    fig.add_scatter(x=eq.index, y=eq, name="策略", line=dict(color=BLUE, width=2))
    if benchmark is not None and len(benchmark):
        b = benchmark / benchmark.iloc[0]
        fig.add_scatter(x=b.index, y=b, name="基准", line=dict(color=GREY, width=1.4))
    fig.update_yaxes(tickformat=".2f")
    return _div(_layout(fig, "组合净值（2024–2026 样本外）", 340))


def fig_drawdown(equity: pd.Series) -> str:
    rets = equity.pct_change().fillna(0)
    cum = (1 + rets).cumprod()
    dd = cum / cum.cummax() - 1
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy",
                               line=dict(color=RED, width=1), fillcolor="rgba(207,34,46,0.15)"))
    fig.update_yaxes(tickformat=".0%")
    return _div(_layout(fig, "回撤", 240))


def fig_event_tiers(summary: dict) -> str:
    tiers = summary.get("tiers", {})
    labels = ["strong", "weak", "negative"]
    cn = {"strong": "强正样本", "weak": "弱正样本", "negative": "负样本"}
    vals = [tiers.get(k, 0) for k in labels]
    fig = go.Figure(go.Bar(x=[cn[k] for k in labels], y=vals,
                           marker_color=[PINK, PURPLE, GREY],
                           text=vals, textposition="outside"))
    fig.update_yaxes(type="log", title="事件数（对数）")
    return _div(_layout(fig, "T0 事件三级标签分布", 280))


def fig_event_ic(ic: pd.DataFrame) -> str:
    if ic is None or ic.empty:
        return '<p class="muted">暂无事件 IC</p>'
    d = ic.head(12).iloc[::-1]
    colors = [GREEN if v >= 0 else RED for v in d["ic"]]
    fig = go.Figure(go.Bar(x=d["ic"], y=d["feature"], orientation="h", marker_color=colors))
    fig.add_vline(x=0, line_color=GREY, line_width=1)
    fig.update_xaxes(tickformat=".3f")
    return _div(_layout(fig, "事件截面 IC（Top 12）", 380))


def fig_event_equity(bt: dict) -> str:
    if not bt or "equity" not in bt:
        return '<p class="muted">暂无事件组合净值</p>'
    eq = pd.Series(bt["equity"], index=pd.to_datetime(bt["equity_dates"]))
    eq = eq / eq.iloc[0]
    fig = go.Figure(go.Scatter(x=eq.index, y=eq, line=dict(color=PURPLE, width=2)))
    fig.update_yaxes(tickformat=".2f")
    return _div(_layout(fig, "事件组合净值（等槽位，T0+1 开盘入场）", 320))


def fig_qlib_native(native: dict) -> str:
    bt = native.get("qlib_backtest", {}) if native else {}
    dates = bt.get("dates") or []
    eq = bt.get("equity") or []
    if not dates or not eq:
        return '<p class="muted">尚未运行 Qlib 原生回测</p>'
    idx = pd.to_datetime(dates)
    fig = go.Figure()
    fig.add_scatter(x=idx, y=eq, name="Qlib 原生组合", line=dict(color=PURPLE, width=2))
    bench = bt.get("benchmark_equity") or []
    if len(bench) == len(idx):
        fig.add_scatter(x=idx, y=bench, name="SH000300", line=dict(color=GREY, width=1.4))
    fig.update_yaxes(tickformat=".2f")
    return _div(_layout(fig, "Qlib 原生回测净值（TopkDropout + SimulatorExecutor）", 330))


def fig_gp(history: list[dict]) -> str:
    if not history:
        return '<p class="muted">未运行遗传规划</p>'
    df = pd.DataFrame(history)
    fig = go.Figure()
    fig.add_scatter(x=df["generation"], y=df["best_fitness"], name="最优适应度",
                    line=dict(color=PURPLE, width=2))
    fig.add_scatter(x=df["generation"], y=df["best_ic"].abs(), name="|IC|",
                    line=dict(color=BLUE, width=1.5, dash="dot"))
    fig.update_xaxes(title="generation")
    return _div(_layout(fig, "GP 进化曲线", 280))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def build_demo_report(result: dict[str, Any], cfg: Config, path: str | Path | None = None) -> Path:
    cfg = cfg
    path = Path(path) if path else cfg.paths.reports / "alphaforge_report.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    panel_info = result.get("panel", {})
    lb: pd.DataFrame = result.get("leaderboard", pd.DataFrame())
    reports = result.get("factor_reports", [])
    best_name = result.get("best_factor", "")
    best = next((r for r in reports if r.name == best_name), reports[0] if reports else None)
    bt = result.get("backtest")
    events = result.get("events", {})
    gp = result.get("gp") or {}
    audit = result.get("audit", {})
    qlib = result.get("qlib", {})

    # leaderboard table
    lb_display = lb.copy()
    if not lb_display.empty:
        lb_display = lb_display.rename(columns={
            "name": "因子", "category": "类别", "ic": "IC(月)", "icir": "ICIR(月)",
            "hit": "命中率", "mono": "单调性", "ls_ann": "多空年化",
            "net_ann": "扣费年化", "dir_net": "方向扣费年化", "turnover": "换手", "verdict": "闸门",
        })
        lb_display["多空年化"] = lb_display["多空年化"].map(lambda x: _fmt_pct(x))
        lb_display["扣费年化"] = lb_display["扣费年化"].map(lambda x: _fmt_pct(x))
        if "方向扣费年化" in lb_display.columns:
            lb_display["方向扣费年化"] = lb_display["方向扣费年化"].map(lambda x: _fmt_pct(x))
        for col in ("IC(月)", "ICIR(月)", "命中率", "单调性", "换手"):
            if col in lb_display.columns:
                lb_display[col] = lb_display[col].map(lambda x: _fmt_num(x, 3))
        for col in ("n", "n_months"):
            if col in lb_display.columns:
                lb_display[col] = lb_display[col].map(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
    lb_html = _table(lb_display, {}, max_rows=40)

    # WQ101 library snapshot (batch evaluation, if present)
    idx_doc = read_json(cfg.paths.reports / "artifacts" / "factors" / "index.json", {}) or {}
    wq = [x for x in idx_doc.get("factors", []) if x.get("category") == "wq101"]
    if wq:
        wq_rows = [{"因子": x.get("name"), "说明": x.get("description", ""),
                    "IC(月)": _fmt_num(x.get("ic"), 4),
                    "ICIR": _fmt_num(x.get("icir"), 2), "覆盖": _fmt_pct(x.get("coverage")),
                    "闸门": x.get("verdict")} for x in wq[:15]]
        wq_html = (f'<p class="muted">已批量评估 {len(wq)} / 101；'
                   f'PASS {sum(1 for x in wq if x.get("verdict") == "PASS")} 个，'
                   f'WATCH {sum(1 for x in wq if x.get("verdict") == "WATCH")} 个。'
                   f'下表按 |IC(月)| 排序，覆盖率为截面有效值占比。</p>'
                   + _table(pd.DataFrame(wq_rows), {}))
    else:
        wq_html = '<p class="muted">尚未批量评估。运行 <code>alphaforge factors batch --category wq101</code>。</p>'

    # factor detail
    detail_html = ""
    figs = {}
    if best is not None:
        p = best.ic.get(best.primary_horizon, {})
        gate = best.gate.get("checks", {})
        gate_rows = "".join(
            f"<tr><td>{v['label']}</td><td>{_fmt_num(v['value'], 3)}</td>"
            f"<td>{_fmt_num(v['threshold'], 3)}</td>"
            f"<td class='{'ok' if v['pass'] else 'bad'}'>{'通过' if v['pass'] else '未通过'}</td></tr>"
            for v in gate.values()
        )
        q = best.quantile.get("long_short", {})
        detail_html = f"""
        <div class="grid two">
          <div>
            <div class="stat-list">
              <div><span>表达式</span><code>{html_escape.escape(best.expression)}</code></div>
              <div><span>类别</span><b>{best.category or '-'}</b></div>
              <div><span>月度 IC / ICIR</span><b>{_fmt_num(p.get('mean_monthly'), 4)} / {_fmt_num(p.get('icir_monthly'), 2)}</b></div>
              <div><span>日度 IC / ICIR</span><b>{_fmt_num(p.get('mean'), 4)} / {_fmt_num(p.get('icir'), 2)}</b></div>
              <div><span>方向命中率（月）</span><b>{_fmt_pct(p.get('hit_rate_monthly'))}</b></div>
              <div><span>分层单调性</span><b>{_fmt_num(best.quantile.get('monotonicity'), 2)}</b></div>
              <div><span>多空年化 / 扣费后</span><b>{_fmt_pct(q.get('annualized'))} / {_fmt_pct(q.get('net_annualized'))}</b></div>
              <div><span>方向调整扣费年化</span><b>{_fmt_pct(q.get('directional_net_annualized'))}</b></div>
              <div><span>换手 / 覆盖率</span><b>{_fmt_num(best.turnover.get('mean'), 2)} / {_fmt_pct(best.coverage)}</b></div>
            </div>
          </div>
          <div>
            <table class="data-table compact"><thead><tr><th>闸门</th><th>值</th><th>阈值</th><th>结果</th></tr></thead>
            <tbody>{gate_rows}</tbody></table>
            <p class="muted">闸门结论：<b class="{ 'ok' if best.verdict == 'PASS' else 'bad' }">{best.verdict}</b>。阈值取绝对值（月度 |IC|&gt;0.03、|ICIR|&gt;0.5、|单调性|）；负 IC 因子在组合中会自动反向使用。</p>
          </div>
        </div>
        """
        figs["ic"] = fig_ic(best)
        figs["quantile"] = fig_quantile(best)
        figs["curves"] = fig_curves(best)
        figs["decay"] = fig_decay(best)
    figs["corr"] = fig_corr(result.get("correlation"))
    if bt is not None:
        figs["backtest"] = fig_backtest(bt.equity, bt.benchmark)
        figs["dd"] = fig_drawdown(bt.equity)

    ev_summary = events.get("summary", {})
    ev_ic = events.get("ic")
    ev_bt = events.get("backtest", {})
    audit_html = ""
    if audit:
        ok = audit.get("ok")
        audit_html = f"""
        <div class="callout {'ok' if ok else 'bad'}">
          <b>防泄露审计：{'通过' if ok else '未通过'}</b> ·
          截断重算最大差异 <code>{_fmt_num(audit.get('max_abs_diff'), 6)}</code> ·
          标签对齐 {'正常' if audit.get('label_alignment_ok') else '异常'} ·
          财务 PIT 最大差异 <code>{_fmt_num(audit.get('pit_max_diff'), 8)}</code> ·
          已检查 {audit.get('n_evaluated', 0)} 个特征点
        </div>
        """
    qlib_html = ""
    if qlib:
        qlib_html = f"""
        <div class="grid three">
          <div class="mini"><span>Qlib 二进制导出</span><b>{qlib.get('symbols', '-')} 只 / {qlib.get('dates', '-')} 日</b></div>
          <div class="mini"><span>Qlib 字段校验</span><b>max|diff| = {_fmt_num(qlib.get('max_abs_diff'), 8)}</b></div>
          <div class="mini"><span>Alpha158 表达式</span><b>{qlib.get('alpha158', 158)} 个已接入</b></div>
        </div>
        """

    native = result.get("qlib_native") or {}
    native_html = ""
    native_chart = ""
    if native:
        n_bt = native.get("qlib_backtest", {}) or {}
        n_af = native.get("alphaforge_backtest", {}) or {}
        n_ic = native.get("ic", {}) or {}
        n_ds = native.get("dataset", {}) or {}
        native_html = f"""
        <div class="grid three">
          <div class="mini"><span>Qlib DatasetH 兼容数据集</span><b>{n_ds.get('rows',0):,} 行 / {n_ds.get('symbols',0)} 只 / {n_ds.get('features',0)} 特征</b></div>
          <div class="mini"><span>Qlib LGBModel 月度 IC / ICIR</span><b>{_fmt_num(n_ic.get('monthly_mean'), 4)} / {_fmt_num(n_ic.get('monthly_icir'), 2)}</b></div>
          <div class="mini"><span>Qlib 原生回测年化 / IR</span><b>{_fmt_pct(n_bt.get('annualized_return'))} / {_fmt_num(n_bt.get('information_ratio'), 2)}</b></div>
        </div>
        <div class="grid two" style="margin-top:14px">
          <div class="panel">{_table(pd.DataFrame([
            {"指标": "Qlib 原生总收益", "值": _fmt_pct(n_bt.get('total_return'))},
            {"指标": "Qlib 原生年化 / 夏普", "值": f"{_fmt_pct(n_bt.get('annualized_return'))} / {_fmt_num(n_bt.get('sharpe'), 2)}"},
            {"指标": "Qlib 原生最大回撤", "值": _fmt_pct(n_bt.get('max_drawdown'))},
            {"指标": "Qlib 原生平均日换手", "值": _fmt_pct(n_bt.get('turnover'))},
            {"指标": "Qlib 原生累计成本", "值": _fmt_pct(n_bt.get('cost'))},
            {"指标": "AlphaForge A股撮合年化 / 夏普", "值": f"{_fmt_pct(n_af.get('cagr'))} / {_fmt_num(n_af.get('sharpe'), 2)}"},
            {"指标": "AlphaForge A股撮合最大回撤", "值": _fmt_pct(n_af.get('max_drawdown'))},
            {"指标": "AlphaForge 信息比率", "值": _fmt_num(n_af.get('information_ratio'), 2)},
          ]), {})}</div>
          <div class="chart">{fig_qlib_native(native)}</div>
        </div>
        <p class="muted" style="margin-top:10px">链路：Qlib <code>LGBModel</code> + <code>R</code> 记录器 +
          <code>TopkDropoutStrategy</code> + <code>SimulatorExecutor</code>；Alpha158 特征值由 AlphaForge
          向量化引擎计算后以 <code>DatasetH</code> 兼容对象提供给 Qlib（Qlib 原生 handler 在千只股票规模下过慢）。
          因此“模型/回测/记录”是 Qlib 的，“因子值计算/事件层/A股撮合”是 AlphaForge 的。
          Qlib 原生回测使用 <code>deal_price=close</code>（Qlib 默认口径），与 AlphaForge 的
          t+1 开盘撮合不完全可比，应以两套规则的相对表现而非绝对收益做结论。</p>
        """
        native_chart = ""
    else:
        native_html = '<div class="callout muted">尚未生成 Qlib 原生结果。运行 <code>alphaforge qlib native</code> 后重新生成报告。</div>'
    gp_html = ""
    if gp.get("evaluated"):
        rows = []
        for c in gp["evaluated"][:10]:
            rows.append(
                f"<tr><td><code>{html_escape.escape(c.get('expression','')[:90])}</code></td>"
                f"<td>{_fmt_num(c.get('train_ic'), 4)}</td>"
                f"<td>{_fmt_num(c.get('valid_ic'), 4)}</td>"
                f"<td>{_fmt_num(c.get('test_ic'), 4)}</td>"
                f"<td>{_fmt_num(c.get('size'), 0)}</td>"
                f"<td>{c.get('valid_verdict','-')}</td></tr>"
            )
        gp_html = (
            '<table class="data-table"><thead><tr><th>表达式</th><th>Train IC</th>'
            '<th>Valid IC</th><th>Test IC</th><th>节点</th><th>Valid 闸门</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>"
        )

    cards = [
        ("数据区间", f"{panel_info.get('start','-')} ~ {panel_info.get('end','-')}",
         f"{panel_info.get('n_dates',0)} 个交易日"),
        ("股票池", f"{panel_info.get('n_symbols',0)} 只", "CSI300 + CSI500 历史成分并集"),
        ("因子库", f"{result.get('n_factors', 0)} 个", "内置 + Qlib Alpha158"),
        ("T0 事件", f"{ev_summary.get('n_events',0):,} 个", "放量启动样本"),
        ("组合年化 / 夏普", f"{_fmt_pct(bt.metrics.get('cagr'))} / {_fmt_num(bt.metrics.get('sharpe'),2)}"
         if bt is not None else "-", "2024–2026 样本外"),
        ("防泄露审计", "通过" if audit.get("ok") else "待查", "截断重算 + 标签对齐"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
        for k, v, s in cards
    )

    template = Template((Path(__file__).parent / "template.html").read_text(encoding="utf-8"))
    html = template.render(
        title="AlphaForge · 因子挖掘 / 回测 / 组合构建平台",
        subtitle="基于 Microsoft Qlib 的 A 股量化研究平台 · T0 事件截面扩展",
        generated=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        plotly_js=get_plotlyjs(),
        cards=cards_html,
        leaderboard=lb_html,
        factor_detail=detail_html,
        wq_table=wq_html,
        fig_ic=figs.get("ic", ""),
        fig_quantile=figs.get("quantile", ""),
        fig_curves=figs.get("curves", ""),
        fig_decay=figs.get("decay", ""),
        fig_corr=figs.get("corr", ""),
        fig_backtest=figs.get("backtest", ""),
        fig_dd=figs.get("dd", ""),
        fig_event_tiers=fig_event_tiers(ev_summary),
        fig_event_ic=fig_event_ic(ev_ic),
        fig_event_equity=fig_event_equity(ev_bt),
        fig_gp=fig_gp(gp.get("history", [])),
        gp_table=gp_html,
        audit=audit_html,
        qlib=qlib_html,
        qlib_native=native_html,
        bt_metrics=_table(pd.DataFrame([
            {"指标": "总收益", "值": _fmt_pct(bt.metrics.get("total_return"))},
            {"指标": "年化收益", "值": _fmt_pct(bt.metrics.get("cagr"))},
            {"指标": "年化波动", "值": _fmt_pct(bt.metrics.get("volatility"))},
            {"指标": "夏普", "值": _fmt_num(bt.metrics.get("sharpe"), 2)},
            {"指标": "最大回撤", "值": _fmt_pct(bt.metrics.get("max_drawdown"))},
            {"指标": "年化换手", "值": _fmt_num(bt.metrics.get("turnover_annual"), 1)},
            {"指标": "超额收益", "值": _fmt_pct(bt.metrics.get("excess_return"))},
            {"指标": "信息比率", "值": _fmt_num(bt.metrics.get("information_ratio"), 2)},
            {"指标": "Beta", "值": _fmt_num(bt.metrics.get("beta"), 2)},
            {"指标": "月胜率", "值": _fmt_pct(bt.metrics.get("win_rate_monthly"))},
        ]), {}) if bt is not None else "",
        ev_metrics=_table(pd.DataFrame([
            {"指标": "事件数", "值": f"{ev_summary.get('n_events',0):,}"},
            {"指标": "强正样本", "值": f"{ev_summary.get('tiers',{}).get('strong',0):,}"},
            {"指标": "弱正样本", "值": f"{ev_summary.get('tiers',{}).get('weak',0):,}"},
            {"指标": "负样本", "值": f"{ev_summary.get('tiers',{}).get('negative',0):,}"},
            {"指标": "事件平均 60 日收益", "值": _fmt_pct(ev_summary.get("mean_label_ret"))},
            {"指标": "事件收益中位数", "值": _fmt_pct(ev_summary.get("median_label_ret"))},
            {"指标": "事件组合年化", "值": _fmt_pct(ev_bt.get("cagr"))},
            {"指标": "事件组合夏普", "值": _fmt_num(ev_bt.get("sharpe"), 2)},
            {"指标": "事件组合最大回撤", "值": _fmt_pct(ev_bt.get("max_drawdown"))},
            {"指标": "单笔平均收益", "值": _fmt_pct(ev_bt.get("avg_trade_ret"))},
        ]), {}),
        ev_ic_table=_table(
            ev_ic.head(12).rename(columns={"feature": "因子", "ic": "事件 IC", "icir": "事件 ICIR",
                                           "n_sections": "截面数", "hit_rate": "命中率",
                                           "positive_rate": "正 IC 占比", "t_stat": "t 值"})
            if ev_ic is not None and not ev_ic.empty else pd.DataFrame(),
            {"事件 IC": lambda x: _fmt_num(x, 4), "事件 ICIR": lambda x: _fmt_num(x, 2),
             "命中率": lambda x: _fmt_pct(x), "正 IC 占比": lambda x: _fmt_pct(x),
             "t 值": lambda x: _fmt_num(x, 2)},
        ),
        corr_note=f"跨 {panel_info.get('n_symbols',0)} 只股票、{panel_info.get('n_dates',0)} 个交易日。",
    )
    path.write_text(html, encoding="utf-8")
    write_json(path.with_suffix(".json"), {
        "generated_at": pd.Timestamp.now().isoformat(),
        "path": str(path), "leaderboard": lb.to_dict(orient="records") if not lb.empty else [],
        "backtest": bt.metrics if bt is not None else {},
        "events": ev_summary, "audit": audit,
    })
    return path
