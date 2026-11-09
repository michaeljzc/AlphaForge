"""WorldQuant "101 Formulaic Alphas" (Kakushadze, 2015).

The formula strings are extracted verbatim from Appendix A of
``101factors.pdf`` (the user's local copy) and translated into the
AlphaForge expression DSL:

    rank            -> cs_rank
    correlation     -> ts_corr
    covariance      -> ts_cov
    stddev          -> ts_std
    sum/product     -> ts_sum/ts_product
    decay_linear    -> ts_decay_linear
    signedpower     -> signed_power
    indneutralize   -> cs_indneutralize  (group argument dropped; group is
                       resolved by Panel.industry_id)
    adv{d}          -> ts_mean(amount, d)  (dollar volume)
    cap             -> circ_mv
    returns         -> ret
    min/max(x, d)   -> ts_min/ts_max(x, d) when the second argument is numeric
    min/max(a, b)   -> elementwise min/max otherwise

The paper says non-integer window sizes are floored; the DSL's window helper
does the same.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable

from alphaforge.expr.ast import Node
from alphaforge.expr.parser import parse

_FORMULAS = json.loads((Path(__file__).parent / "wq101_formulas.json").read_text(encoding="utf-8"))

_MAP = {
    "rank": "cs_rank",
    "correlation": "ts_corr",
    "covariance": "ts_cov",
    "stddev": "ts_std",
    "sum": "ts_sum",
    "product": "ts_product",
    "decay_linear": "ts_decay_linear",
    "signedpower": "signed_power",
    "indneutralize": "cs_indneutralize",
}
# Chinese descriptions for the 101 alphas.  They describe the economic /
# formulaic intent, not a guarantee of predictive power.
_DESCRIPTIONS = {
    1: "收益为负时用20日波动率替代价格，平方后取5日最高点位置并截面排名，捕捉下行波动中的反转。",
    2: "成交量对数2日变化与开收盘收益的秩相关（6日），取负向，衡量量价配合的反转。",
    3: "开盘价与成交量的10日秩相关，取负向，衡量开盘放量后的反转。",
    4: "低价截面排名的9日时序排名，取负向，短期反转因子。",
    5: "开盘价对10日VWAP均值的偏离，乘以收盘对VWAP偏离的负绝对值，衡量价格与均价背离。",
    6: "开盘价与成交量的10日相关，取负向。",
    7: "放量（volume>adv20）时，7日价格变化绝对值的60日时序排名乘以变化方向，取负向。",
    8: "5日开盘和与5日收益和乘积的10日变化，取负向，量价配合反转。",
    9: "5日价格变化的最小值>0 取变化，最大值<0 取变化，否则反向，趋势确认。",
    10: "同Alpha#9，使用4日窗口并在外层做截面排名。",
    11: "3日VWAP与收盘价差的极值排名，乘以3日成交量变化排名。",
    12: "成交量变化方向乘以价格变化的负向，量价背离。",
    13: "收盘价与成交量秩的5日协方差排名，取负向。",
    14: "3日收益变化排名乘以开盘价与成交量的10日相关，取负向。",
    15: "高价与成交量3日秩相关，3日求和后排名，取负向。",
    16: "高价与成交量5日秩协方差排名，取负向。",
    17: "收盘10日时序排名、价格二阶差分排名、量比5日时序排名三者相乘。",
    18: "5日绝对日内收益波动、日内收益、开收盘10日相关之和，排名取负向。",
    19: "7日价格趋势方向乘以(1+250日收益排名)，取负向。",
    20: "开盘价相对昨日高/收/低偏离的排名乘积。",
    21: "8日/2日均线、波动带与量比条件的多状态信号（-1/1）。",
    22: "高价与成交量5日相关的变化，乘以20日收盘波动排名，取负向。",
    23: "20日高价均线低于现价时做2日高价变化，否则为0。",
    24: "100日均线100日变化<0.05时做100日区间下沿反转，否则做3日反转。",
    25: "收益、adv20、VWAP、上影线的组合，取负向。",
    26: "成交量与高价5日时序排名的相关，3日最大值，取负向。",
    27: "成交量与VWAP6日秩相关2日均值>0.5时取-1，否则1。",
    28: "adv20与低价的5日相关加中间价减收盘，截面scale。",
    29: "价格秩的复杂嵌套加6日延迟收益，取极小值组合。",
    30: "价格变化符号和，乘以5日/20日成交量。",
    31: "10日价格变化秩的10日线性衰减，加3日变化和adv20/低价12日相关。",
    32: "7日均线偏离，加20倍VWAP与5日前收盘的230日相关。",
    33: "开盘/收盘比值的负一次方排名。",
    34: "2日/5日波动比加1日变化排名。",
    35: "32日成交量时序排名×(1-16日价格区间时序排名)×(1-32日收益时序排名)。",
    36: "5个子信号加权：开收盘、开收盘排名、延迟收益、VWAP/adv20、200日均线。",
    37: "开收盘1日延迟与收盘的200日相关，加开收盘。",
    38: "收盘10日时序排名乘以收盘/开盘。",
    39: "7日价格变化×(1-量比9日衰减排名)×(1+250日收益排名)。",
    40: "高价10日波动排名×高价与成交量10日相关，取负向。",
    41: "最高价与最低价的几何均值减VWAP。",
    42: "VWAP-收盘与VWAP+收盘的秩比。",
    43: "量比20日时序排名×负7日价格变化8日时序排名。",
    44: "高价与成交量秩的5日相关，取负向。",
    45: "5日前收盘20日均值排名×收盘与成交量2日相关×5日/20日收盘和2日相关，取负向。",
    46: "20/10/现价的20日、10日趋势状态，负向时反向。",
    47: "1/收盘排名×量/adv20×上影线/5日均高，再减VWAP变化排名。",
    48: "250日价格变化与收益变化的相关×价格变化/收盘，行业中性后除以250日平方收益和。",
    49: "同Alpha#46，阈值改为-0.1。",
    50: "成交量与VWAP5日秩相关，5日最大值后排名，取负向。",
    51: "同Alpha#46，阈值改为-0.05。",
    52: "5日最低价变化×240/20日收益差排名×5日成交量排名。",
    53: "收盘-低-(高-收盘) / (收盘-低) 的9日变化，取负向。",
    54: "(低-收)×开^5 / ((低-高)×收^5)，取负向。",
    55: "12日价格区间位置排名×成交量排名6日相关，取负向。",
    56: "10日收益和/2日收益和3日滚动×收益×市值排名，取负向。",
    57: "(收盘-VWAP)/2日衰减的30日最高价位置排名，取负向。",
    58: "VWAP行业中性后与成交量3.9日相关，7.9日衰减后5.5日时序排名，取负向。",
    59: "混合VWAP行业中性后与成交量4.25日相关，16.2日衰减后8.2日时序排名，取负向。",
    60: "2×scale(区间位置×成交量排名)-scale(10日最高价位置排名)。",
    61: "VWAP距16日低点排名 < VWAP与adv180的17.9日相关排名。",
    62: "VWAP与adv20的和9.9日相关排名 < 开盘/中间价/高价秩和，取负向。",
    63: "行业中性收盘2.25日变化8.22日衰减排名 - 混合价与adv180和13.56日相关12.29日衰减排名，取负向。",
    64: "混合开低12.7日均值与adv120和16.6日相关排名 < 中间价/VWAP3.7日变化排名，取负向。",
    65: "混合开VWAP与adv60的6.4日相关排名 < 开盘距13.6日低点排名，取负向。",
    66: "VWAP3.5日变化7.2日衰减排名 + 低价与中间价差/开盘-中间价11.4日衰减6.7日时序排名，取负向。",
    67: "高价距2.15日低点排名 ^ 行业中性VWAP与行业中性adv20的6.03日相关排名，取负向。",
    68: "高价与adv15秩8.9日相关13.9日时序排名 < 混合收盘低价1.06日变化排名，取负向。",
    69: "行业中性VWAP2.72日变化4.79日最大排名 ^ 混合价与adv20的4.92日相关9.06日时序排名，取负向。",
    70: "VWAP1.29日变化排名 ^ 行业中性收盘与adv50的17.8日相关17.9日时序排名，取负向。",
    71: "两个衰减相关时序排名的较大者：收盘3.44日/adv18012.06日，低价+开盘-2VWAP平方16.47日。",
    72: "中间价/adv40的8.93日相关10.15日衰减排名 / VWAP与成交量3.72/18.52日时序相关6.87日衰减排名。",
    73: "max(VWAP4.73日变化2.92日衰减排名, 混合开低2.04日变化3.34日衰减16.74日时序排名)，取负向。",
    74: "收盘与adv30和15.14日相关排名 < 混合高价VWAP/成交量11.48日相关排名，取负向。",
    75: "VWAP与成交量4.24日相关排名 < 低价/adv50的12.44日相关排名。",
    76: "max(VWAP1.24日变化11.83日衰减排名, 行业中性低价/adv81的8.15日相关19.57日时序衰减19.38日时序排名)，取负向。",
    77: "min(中间价+高-2VWAP的20.05日衰减排名, 中间价/adv40的3.16日相关5.64日衰减排名)。",
    78: "混合低价VWAP19.74日与adv40和6.83日相关排名 ^ VWAP/成交量5.77日秩相关排名。",
    79: "行业中性混合收盘开盘1.23日变化排名 < VWAP3.61日/adv1509.19日时序相关14.66日时序排名。",
    80: "行业中性混合开高4.05日变化符号排名 ^ 高价adv10的5.11日相关5.54日时序排名，取负向。",
    81: "log(product(rank(rank(VWAP/adv10的8.48日相关^4)),14.97))排名 < VWAP/成交量5.08日秩相关排名，取负向。",
    82: "min(开盘1.46日变化14.87日衰减排名, 行业中性成交量与混合开盘17.48日相关6.92日衰减13.43日时序排名)，取负向。",
    83: "2日延迟的区间/5日均收 × 成交量排名² / (区间/5日均收/(VWAP-收盘))。",
    84: "SignedPower(20日VWAP距15.32日高点时序排名, 4.97日收盘变化)。",
    85: "混合高收/adv30的9.61日相关排名 ^ 中间价3.71日/成交量10.16日时序相关7.11日时序排名。",
    86: "收盘/adv20和14.74日相关6日时序排名 < 开盘+收盘-VWAP-开盘排名，取负向。",
    87: "max(混合收盘VWAP1.91日变化2.65日衰减排名, 行业中性adv81与收盘13.41日相关绝对4.90日衰减14.45日时序排名)，取负向。",
    88: "min(开低高收秩组合8.07日衰减排名, 收盘8.45日/adv60 20.70日时序相关6.65日衰减2.62日时序排名)。",
    89: "低价/adv10的6.94日相关5.52日衰减3.80日时序排名 - 行业中性VWAP3.48日变化10.15日衰减15.30日时序排名。",
    90: "收盘距4.67日高点排名 ^ 行业中性adv40与低价5.38日相关3.22日时序排名，取负向。",
    91: "行业中性收盘/成交量9.75日相关16.40日衰减3.83日衰减4.87日时序排名 - VWAP/adv30的4.01日相关2.68日衰减排名，取负向。",
    92: "min(中间价+收盘<低+开盘的14.72日衰减18.87日时序排名, 低价/adv30的7.59日相关6.94日衰减6.81日时序排名)。",
    93: "行业中性VWAP/adv81的17.42日相关19.85日衰减7.54日时序排名 / 混合收盘VWAP2.77日变化16.27日衰减排名。",
    94: "VWAP距11.58日低点排名 ^ VWAP19.65日/adv60 4.03日时序相关18.09日时序相关2.71日时序排名，取负向。",
    95: "开盘距12.41日低点排名 < (中间价/adv40的12.87日相关排名^5)的11.76日时序排名。",
    96: "max(VWAP/成交量3.84日秩相关4.17日衰减8.38日时序排名, 30日相关12.66日时序最大14.04日衰减13.41日时序排名)，取负向。",
    97: "行业中性混合低VWAP3.37日变化20.45日衰减排名 - 低价7.88日/adv60 17.26日时序相关4.98日时序18.59日衰减15.72日时序6.72日时序排名，取负向。",
    98: "VWAP/adv5和26.47日相关7.18日衰减排名 - 开盘/adv15的20.82日秩相关8.63日时序6.96日时序8.07日衰减排名。",
    99: "中间价19.90日和/adv60 19.90日和8.81日相关排名 < 低价与成交量6.28日相关排名，取负向。",
    100: "1.5×行业中性(区间位置×成交量秩) - 行业中性(收盘/adv20 5日相关 - 30日最低价位置排名)，再乘量比。",
    101: "(收盘-开盘)/(最高-最低+0.001)，日内收益相对振幅。",
}

_NUM = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?$")


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(text[start:i].strip())
            start = i + 1
    tail = text[start:].strip()
    if tail:
        args.append(tail)
    return args


def _matching(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced parentheses")


def _apply(name: str, args: list[str]) -> str:
    n = name.lower()
    if n in ("min", "max"):
        if len(args) == 2 and _NUM.match(args[1]):
            w = int(math.floor(float(args[1])))
            return f"ts_{n}({args[0]}, {w})"
        return f"{n}({', '.join(args)})"
    if n == "scale":
        if len(args) == 1:
            return f"cs_scale({args[0]})"
        return f"(cs_scale({args[0]}) * {args[1]})"
    if n == "indneutralize":
        return f"cs_indneutralize({args[0]})"
    if n in _MAP:
        return f"{_MAP[n]}({', '.join(args)})"
    return f"{n}({', '.join(args)})" if args else n


def _rewrite(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            name = text[i:j]
            if j < len(text) and text[j] == "(":
                k = _matching(text, j)
                args = [_rewrite(a) for a in _split_args(text[j + 1:k])]
                out.append(_apply(name, args))
                i = k + 1
            else:
                out.append(name)
                i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def translate_wq101(formula: str) -> str:
    text = _rewrite(formula)
    text = re.sub(r"\badv(\d+)\b", r"ts_mean(amount, \1)", text, flags=re.I)
    text = re.sub(r"\bcap\b", "circ_mv", text, flags=re.I)
    text = re.sub(r"\breturns\b", "ret", text, flags=re.I)
    text = re.sub(r"\bIndClass\.\w+\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def translate_all() -> dict[int, str]:
    return {int(k): translate_wq101(v) for k, v in sorted(_FORMULAS.items(), key=lambda kv: int(kv[0]))}


def wq101_defs():
    from alphaforge.expr.library import FactorDef

    out = []
    for n, raw in sorted(_FORMULAS.items(), key=lambda kv: int(kv[0])):
        num = int(n)
        expr = translate_wq101(raw)
        try:
            node = parse(expr)
        except Exception:
            continue
        out.append(FactorDef(
            name=f"wq{num:03d}", expression=node.to_string(), category="wq101",
            direction=1, description=_DESCRIPTIONS.get(num, f"WorldQuant Alpha#{num}"),
            source="101formulaic",
        ))
    return out


if __name__ == "__main__":
    ok = bad = 0
    for n, expr in translate_all().items():
        try:
            parse(expr); ok += 1
        except Exception as exc:
            bad += 1
            print(f"FAIL alpha#{n}: {expr[:160]} -> {exc}")
    print(f"parsed ok={ok} bad={bad}")
