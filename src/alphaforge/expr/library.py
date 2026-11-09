"""Curated factor library + Qlib Alpha158 bridge.

Factors are *expressions*, not scripts: every definition is a string that the
expression engine can evaluate, version and reproduce.  The T0 "launch" family
follows the research report's five dimensions (price-volume, money flow,
sentiment, fundamentals, environment).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from alphaforge.expr.parser import parse


@dataclass(frozen=True)
class FactorDef:
    name: str
    expression: str
    category: str
    direction: int = 1          # prior sign of IC
    description: str = ""
    source: str = "builtin"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expression": self.expression,
            "category": self.category,
            "direction": self.direction,
            "description": self.description,
            "source": self.source,
        }


FACTORS: dict[str, FactorDef] = {}


def register(name: str, expression: str, category: str, direction: int = 1,
             description: str = "", source: str = "builtin") -> FactorDef:
    node = parse(expression)
    definition = FactorDef(name=name, expression=node.to_string(), category=category,
                           direction=direction, description=description, source=source)
    FACTORS[name] = definition
    return definition


# --------------------------------------------------------------------------
# price / volume / momentum / reversal
# --------------------------------------------------------------------------
_PRICE = [
    ("ret_1", "ret", -1, "1 日收益（短期反转）"),
    ("ret_5", "close/delay(close, 5)-1", -1, "5 日收益"),
    ("ret_20", "close/delay(close, 20)-1", 1, "20 日动量"),
    ("ret_60", "close/delay(close, 60)-1", 1, "60 日动量"),
    ("ret_120", "close/delay(close, 120)-1", 1, "120 日动量"),
    ("mom_20_5", "delay(close, 5)/delay(close, 25)-1", 1, "剔除近 5 日的 20 日动量"),
    ("ma_ratio_5", "close/ts_mean(close, 5)-1", -1, "价格对 5 日均线偏离"),
    ("ma_ratio_20", "close/ts_mean(close, 20)-1", -1, "价格对 20 日均线偏离"),
    ("ma_ratio_60", "close/ts_mean(close, 60)-1", -1, "价格对 60 日均线偏离"),
    ("ma_cross_5_20", "ts_mean(close, 5)/ts_mean(close, 20)-1", 1, "5/20 均线交叉"),
    ("ma_cross_20_60", "ts_mean(close, 20)/ts_mean(close, 60)-1", 1, "20/60 均线交叉"),
    ("breakout_20", "close/ts_max(close, 20)-1", 1, "20 日新高突破"),
    ("breakout_60", "close/ts_max(close, 60)-1", 1, "60 日新高突破"),
    ("breakout_120", "close/ts_max(close, 120)-1", 1, "120 日新高突破"),
    ("breakout_250", "close/ts_max(close, 250)-1", 1, "250 日新高突破"),
    ("drawdown_60", "close/ts_max(close, 60)-1", -1, "距 60 日高点回撤"),
    ("drawdown_250", "close/ts_max(close, 250)-1", -1, "距 250 日高点回撤"),
    ("price_pos_60", "(close-ts_min(low, 60))/(ts_max(high, 60)-ts_min(low, 60)+1e-9)", 1, "60 日价格区间位置"),
    ("price_pos_250", "(close-ts_min(low, 250))/(ts_max(high, 250)-ts_min(low, 250)+1e-9)", 1, "250 日价格区间位置"),
    ("volatility_20", "ts_std(ret, 20)", -1, "20 日波动率"),
    ("volatility_60", "ts_std(ret, 60)", -1, "60 日波动率"),
    ("vol_ratio_5_60", "ts_std(ret, 5)/ts_std(ret, 60)", -1, "短长波动比（波动压缩）"),
    ("skew_20", "ts_skew(ret, 20)", -1, "20 日收益偏度"),
    ("kurt_20", "ts_kurt(ret, 20)", -1, "20 日收益峰度"),
    ("max_ret_20", "ts_max(ret, 20)", 1, "20 日最大单日涨幅"),
    ("min_ret_20", "ts_min(ret, 20)", -1, "20 日最大单日跌幅"),
    ("up_ratio_20", "ts_mean(gt(ret, 0), 20)", 1, "20 日上涨天数占比"),
    ("rsi_14", "ts_mean(max(ret, 0), 14)/(ts_mean(abs(ret), 14)+1e-9)", 1, "相对强弱指标 RSI(14)"),
    ("volume_ratio_5", "volume/ts_mean(volume, 5)", 1, "5 日量比"),
    ("volume_ratio_20", "volume/ts_mean(volume, 20)", 1, "20 日量比"),
    ("volume_ratio_60", "volume/ts_mean(volume, 60)", 1, "60 日量比"),
    ("volume_trend_5_60", "ts_mean(volume, 5)/ts_mean(volume, 60)", 1, "成交量放大趋势"),
    ("amount_ratio_20", "amount/ts_mean(amount, 20)", 1, "成交额放大"),
    ("turnover_mean_5", "ts_mean(turnover_f, 5)", 1, "5 日平均换手"),
    ("turnover_mean_20", "ts_mean(turnover_f, 20)", 1, "20 日平均换手"),
    ("turnover_rank_120", "ts_rank(turnover_f, 120)", 1, "换手率 120 日分位"),
    ("turnover_z_60", "(turnover_f-ts_mean(turnover_f, 60))/(ts_std(turnover_f, 60)+1e-12)", 1, "换手率 60 日 z 分数"),
    ("turnover_vol_20", "ts_std(turnover_f, 20)", 1, "换手率波动"),
    ("amihud_20", "ts_mean(abs(ret)/amount*1e9, 20)", 1, "Amihud 非流动性"),
    ("corr_pv_20", "ts_corr(close, volume, 20)", 1, "量价相关性"),
    ("corr_ret_vol_20", "ts_corr(ret, volume, 20)", 1, "收益-成交量相关性"),
    ("klen", "(high-low)/open", 1, "K 线长度"),
    ("close_location", "(close-low)/(high-low+1e-9)", 1, "收盘位置"),
    ("upper_shadow", "(high-max(open, close))/(high-low+1e-9)", -1, "上影线占比"),
    ("lower_shadow", "(min(open, close)-low)/(high-low+1e-9)", 1, "下影线占比"),
    ("gap", "open/delay(close, 1)-1", -1, "隔夜跳空"),
    ("vwap_dev", "close/vwap-1", -1, "收盘对 VWAP 偏离"),
    ("beta_60", "ts_corr(ret, mkt_ret, 60)", -1, "60 日市场 Beta"),
    ("idvol_60", "ts_std(ret-ts_corr(ret, mkt_ret, 60)*mkt_ret, 60)", -1, "60 日特质波动"),
    ("corr_mkt_60", "ts_corr(ret, mkt_ret, 60)", -1, "与市场相关性"),
]

_FLOW = [
    ("main_net_ratio", "main_net_ratio", 1, "主力资金净流入占比"),
    ("main_net_ratio_5", "ts_mean(main_net_ratio, 5)", 1, "5 日主力净流入"),
    ("main_net_ratio_20", "ts_mean(main_net_ratio, 20)", 1, "20 日主力净流入"),
    ("main_net_consistency_20", "ts_mean(gt(main_net, 0), 20)", 1, "主力净流入连续性"),
    ("main_net_vol_20", "ts_std(main_net_ratio, 20)", -1, "主力资金波动"),
    ("net_mf_ratio_5", "ts_mean(net_mf_ratio, 5)", 1, "5 日净流入占比"),
    ("money_flow_trend", "ts_mean(main_net_ratio, 5)-ts_mean(main_net_ratio, 20)", 1, "资金流入加速"),
    ("limit_up_ratio_20", "ts_mean(limit_up_flag, 20)", 1, "20 日涨停占比"),
    ("limit_up_sum_20", "ts_sum(limit_up_flag, 20)", 1, "20 日涨停次数"),
    ("limit_down_ratio_20", "ts_mean(limit_down_flag, 20)", -1, "20 日跌停占比"),
]

_VALUE = [
    ("ep", "earnings_yield", 1, "盈利收益率 E/P"),
    ("bp", "book_to_price", 1, "账面市值比 B/P"),
    ("sp", "sales_to_price", 1, "营收市值比 S/P"),
    ("dy", "dividend_yield", 1, "股息率"),
    ("log_mv", "log_mv", -1, "对数流通市值（小市值）"),
    ("log_total_mv", "log_total_mv", -1, "对数总市值"),
]

_QUALITY = [
    ("roe", "roe", 1, "净资产收益率 ROE（PIT 财务）"),
    ("netprofit_yoy", "netprofit_yoy", 1, "净利润同比"),
    ("or_yoy", "or_yoy", 1, "营收同比"),
    ("q_profit_yoy", "q_profit_yoy", 1, "单季净利润同比"),
    ("q_sales_yoy", "q_sales_yoy", 1, "单季营收同比"),
    ("grossprofit_margin", "grossprofit_margin", 1, "毛利率"),
    ("debt_to_assets", "debt_to_assets", -1, "资产负债率"),
    ("eps", "eps", 1, "每股收益"),
    ("bps", "bps", 1, "每股净资产"),
]

_LAUNCH = [
    ("launch_vol_surge_5", "volume/ts_mean(volume, 5)-1", 1, "5 日放量幅度"),
    ("launch_vol_surge_20", "volume/ts_mean(volume, 20)-1", 1, "20 日放量幅度"),
    ("launch_amount_surge_20", "amount/ts_mean(amount, 20)-1", 1, "成交额突增"),
    ("launch_turnover_surge_20", "turnover_f/ts_mean(turnover_f, 20)-1", 1, "换手突增"),
    ("launch_turnover_pct_120", "ts_rank(turnover_f, 120)", 1, "换手率历史分位"),
    ("launch_breakout_60", "close/ts_max(close, 60)-1", 1, "60 日突破幅度"),
    ("launch_breakout_120", "close/ts_max(close, 120)-1", 1, "120 日突破幅度"),
    ("launch_consolidation", "ts_std(ret, 20)/ts_std(ret, 60)", -1, "波动压缩（启动前蓄势）"),
    ("launch_range_expansion", "(high-low)/close/(ts_mean((high-low)/close, 20)+1e-9)", 1, "振幅扩张"),
    ("launch_close_strength", "(close-low)/(high-low+1e-9)", 1, "收盘强度"),
    ("launch_ma_stack", "ts_mean(close, 5)/ts_mean(close, 20)-1", 1, "短期均线上穿"),
    ("launch_vol_price_resonance", "ts_corr(ret, volume/ts_mean(volume, 20)-1, 20)", 1, "量价共振"),
    ("launch_pre_vol_ratio", "ts_mean(volume, 5)/ts_mean(volume, 60)", 1, "启动前成交量抬升"),
    ("launch_small_cap", "neg(log_mv)", 1, "小市值弹性"),
    ("launch_money_inflow_5", "ts_mean(main_net_ratio, 5)", 1, "启动前 5 日资金流入"),
    ("launch_flow_price_div", "cs_rank(close/delay(close, 20)-1)-cs_rank(ts_mean(main_net_ratio, 20))", 1, "资金与价格背离"),
    ("launch_high_52w", "close/ts_max(high, 250)-1", 1, "距 52 周高点"),
    ("launch_volume_contraction", "ts_std(volume, 20)/(ts_mean(volume, 20)+1e-9)", -1, "成交量收敛"),
    ("launch_price_compression", "ts_std(ret, 20)/ts_std(ret, 120)", -1, "价格波动收敛"),
    ("launch_limit_up_20", "ts_sum(limit_up_flag, 20)", 1, "近期涨停次数"),
    ("launch_flow_trend", "ts_mean(main_net_ratio, 5)-ts_mean(main_net_ratio, 20)", 1, "资金流入加速"),
]

for group, category in [
    (_PRICE, "price_volume"),
    (_FLOW, "money_flow"),
    (_VALUE, "value"),
    (_QUALITY, "quality_growth"),
    (_LAUNCH, "launch"),
]:
    for name, expr, direction, desc in group:
        register(name, expr, category, direction=direction, description=desc)


# --------------------------------------------------------------------------
# Qlib Alpha158 bridge
# --------------------------------------------------------------------------
_QLIB_FUNCS = {
    "Ref": "delay",
    "Mean": "ts_mean",
    "Std": "ts_std",
    "Var": "ts_var",
    "Skew": "ts_skew",
    "Kurt": "ts_kurt",
    "Max": "ts_max",
    "Min": "ts_min",
    "Rank": "ts_rank",
    "Quantile": "ts_quantile",
    "Sum": "ts_sum",
    "Corr": "ts_corr",
    "Cov": "ts_cov",
    "Delta": "delta",
    "EMA": "ts_ema",
    "WMA": "ts_wma",
    "Slope": "ts_slope",
    "Rsquare": "ts_rsquare",
    "Resi": "ts_resi",
    "ArgMax": "ts_argmax",
    "ArgMin": "ts_argmin",
    "IdxMax": "ts_idxmax",
    "IdxMin": "ts_idxmin",
    "Greater": "max",
    "Less": "min",
    "And": "and",
    "Or": "or",
    "Not": "not",
    "If": "where",
    "Abs": "abs",
    "Log": "log",
    "Sign": "sign",
    "Power": "pow",
    "Mad": "ts_mad",
    "Med": "ts_median",
    "Product": "ts_product",
    "Count": "ts_count",
    "CSRank": "cs_rank",
}

_FUNC_RE = re.compile(r"\b(" + "|".join(sorted(_QLIB_FUNCS, key=len, reverse=True)) + r")\s*\(")


def translate_qlib_expression(expr: str) -> str:
    """Convert a Qlib expression (``Ref($close, 5)``) to AlphaForge DSL."""
    text = expr.replace("$", "")
    text = _FUNC_RE.sub(lambda m: _QLIB_FUNCS[m.group(1)] + "(", text)
    return text



_ALPHA158_EXACT = {
    "KMID": "日内收益：(收盘-开盘)/开盘",
    "KLEN": "K线振幅：(最高-最低)/开盘",
    "KMID2": "实体占振幅比：(收盘-开盘)/(最高-最低)",
    "KUP": "上影线/开盘：(最高-max(开,收))/开盘",
    "KUP2": "上影线占振幅比",
    "KLOW": "下影线/开盘：(min(开,收)-最低)/开盘",
    "KLOW2": "下影线占振幅比",
    "KSFT": "收盘位置：(2×收-高-低)/开盘",
    "KSFT2": "收盘位置占振幅比",
    "OPEN0": "开盘价/收盘价",
    "HIGH0": "最高价/收盘价",
    "LOW0": "最低价/收盘价",
    "VWAP0": "VWAP/收盘价",
}
_ALPHA158_TPL = {
    "ROC": "{d}日收益率",
    "MA": "收盘价/{d}日均线",
    "STD": "{d}日收益波动率",
    "BETA": "{d}日收益对时间回归的斜率",
    "RSQR": "{d}日收益线性回归的R²",
    "RESI": "{d}日收益回归残差/收盘",
    "MAX": "{d}日最大单日收益",
    "MIN": "{d}日最小单日收益",
    "QTLU": "{d}日收益80%分位",
    "QTLD": "{d}日收益20%分位",
    "RANK": "当前收益在{d}日内的时序分位",
    "RSV": "收盘价在{d}日区间中的位置",
    "IMAX": "{d}日最高点距今天数",
    "IMIN": "{d}日最低点距今天数",
    "IMXD": "最高点与最低点的天数差",
    "CORR": "收盘价与log成交量的{d}日相关",
    "CORD": "收益与log成交量变化的{d}日相关",
    "CNTP": "{d}日上涨天数占比",
    "CNTN": "{d}日下跌天数占比",
    "CNTD": "{d}日涨跌天数差占比",
    "SUMP": "{d}日上涨收益之和",
    "SUMN": "{d}日下跌收益之和",
    "SUMD": "{d}日涨跌收益和之差",
    "VMA": "成交量/{d}日均量",
    "VSTD": "成交量{d}日波动",
    "WVMA": "成交量加权收益波动（{d}日）",
    "VSUMP": "{d}日放量上涨收益和",
    "VSUMN": "{d}日放量下跌收益和",
    "VSUMD": "{d}日放量涨跌收益差",
}


def alpha158_description(name: str) -> str:
    raw = name[5:] if name.lower().startswith("a158_") else name
    if raw in _ALPHA158_EXACT:
        return _ALPHA158_EXACT[raw]
    m = re.match(r"^([A-Z]+?)(\d+)$", raw)
    if m and m.group(1) in _ALPHA158_TPL:
        return _ALPHA158_TPL[m.group(1)].format(d=m.group(2))
    return f"Qlib Alpha158 特征 {raw}"


def alpha158_factors() -> list[FactorDef]:
    """Port Qlib's Alpha158 feature definitions into the AlphaForge DSL."""
    from qlib.contrib.data.loader import Alpha158DL

    fields, names = Alpha158DL.get_feature_config()
    out: list[FactorDef] = []
    for name, expr in zip(names, fields):
        translated = translate_qlib_expression(expr)
        try:
            parse(translated)
        except Exception:
            continue
        out.append(FactorDef(name=f"a158_{name}", expression=translated,
                             category="alpha158", direction=1,
                             description=alpha158_description(name), source="qlib"))
    return out


def alpha158_dict() -> dict[str, FactorDef]:
    return {d.name: d for d in alpha158_factors()}


# --------------------------------------------------------------------------
# public helpers
# --------------------------------------------------------------------------
def get_factor(name: str) -> FactorDef:
    if name in FACTORS:
        return FACTORS[name]
    a158 = alpha158_dict()
    if name in a158:
        return a158[name]
    raise KeyError(f"未知因子 {name}")


def list_factors(category: str | None = None) -> list[FactorDef]:
    items = list(FACTORS.values())
    if category:
        items = [x for x in items if x.category == category]
    return sorted(items, key=lambda x: (x.category, x.name))


def categories() -> dict[str, int]:
    out: dict[str, int] = {}
    for f in FACTORS.values():
        out[f.category] = out.get(f.category, 0) + 1
    return out


def factor_table() -> list[dict[str, Any]]:
    return [f.to_dict() for f in list_factors()]


def default_factor_names() -> list[str]:
    """A compact, low-redundancy set used by the demo pipeline."""
    return [
        "ret_1", "ret_5", "ret_20", "ret_60",
        "ma_ratio_20", "ma_cross_5_20", "breakout_60", "drawdown_60",
        "volatility_20", "vol_ratio_5_60", "turnover_rank_120", "amihud_20",
        "corr_pv_20", "close_location", "vwap_dev",
        "main_net_ratio_5", "main_net_ratio_20", "main_net_consistency_20",
        "ep", "bp", "log_mv", "roe", "netprofit_yoy", "grossprofit_margin",
        "launch_vol_surge_20", "launch_turnover_surge_20", "launch_breakout_60",
        "launch_consolidation", "launch_vol_price_resonance", "launch_money_inflow_5",
    ]


# --------------------------------------------------------------------------
# WorldQuant 101 Formulaic Alphas
# --------------------------------------------------------------------------
try:
    from alphaforge.expr.wq101 import wq101_defs as _wq101_defs

    for _f in _wq101_defs():
        FACTORS[_f.name] = _f
except Exception as _exc:  # pragma: no cover - defensive
    print(f"[wq101] load failed: {_exc}")


if __name__ == "__main__":
    print(f"builtin factors: {len(FACTORS)}  categories: {categories()}")
    try:
        a158 = alpha158_factors()
        print(f"Alpha158 imported: {len(a158)}")
        for d in a158[:5]:
            print(" ", d.name, "=", d.expression)
    except Exception as exc:
        print("Alpha158 import failed:", exc)
