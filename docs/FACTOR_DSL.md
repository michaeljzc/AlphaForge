# 因子表达式 DSL

## 1. 语法

```text
expr     := additive (('>' | '<' | '>=' | '<=' | '==' | '!=') additive)*
additive := term (('+' | '-') term)*
term     := unary (('*' | '/') unary)*
unary    := ('+' | '-') unary | power
power    := atom ('^' unary)?
atom     := NUMBER | FIELD | FUNC '(' args ')' | '(' expr ')'
```

- 字段名可带 `$` 前缀（Qlib 兼容）：`$close` 等价 `close`；
- 比较运算返回 0/1；
- `^` 右结合：`2^3^2 = 512`；
- 函数名大小写不敏感；未知函数/字段在编译或求值时抛出明确错误。

## 2. 字段

价格（前复权）：`open high low close vwap pre_close`
原始价：`open_raw high_raw low_raw close_raw pre_close_raw`
量额：`volume amount turnover_f free_turnover volume_ratio`
收益：`ret log_ret mkt_ret`
估值/规模：`pe_ttm pb ps_ttm dv_ttm total_mv circ_mv log_mv log_total_mv earnings_yield book_to_price sales_to_price dividend_yield`
资金：`main_net main_net_ratio net_mf net_mf_ratio buy_elg sell_elg buy_lg sell_lg`
交易约束：`up_limit down_limit limit_up_flag limit_down_flag limit_pct suspended`
PIT 财务：`roe netprofit_yoy or_yoy debt_to_assets grossprofit_margin eps bps ocfps q_roe q_profit_yoy q_sales_yoy`
其他：`listed_days is_st adj_factor`

> 因子默认使用复权价字段；`*_raw` 仅用于撮合/涨跌停研究。

## 3. 算子

### 算术 / 逐元素

| 算子 | 说明 |
|---|---|
| `+ - * / ^` | 四则与幂；除零/非法值转 NaN |
| `abs sign log log1p exp sqrt` | 数学函数 |
| `signed_log(x)` | `sign(x)·log1p(|x|)` |
| `clip(x, lo, hi)` | 截断 |
| `min(a,b) max(a,b)` | 逐元素（忽略 NaN） |
| `where(cond, x, y)` | 条件选择 |
| `gt lt ge le eq ne` | 比较，返回 0/1 |
| `and or not` | 布尔 |
| `isnan isfinite` | 缺失判断 |

### 时序（按股票，因果）

| 算子 | 说明 |
|---|---|
| `delay(x,n)` / `ref` | 滞后 n 期 |
| `delta(x,n)` | `x - delay(x,n)` |
| `pct_change(x,n)` | `x/delay(x,n)-1` |
| `ts_mean(x,w)` | 滚动均值 |
| `ts_sum ts_std ts_var` | 滚动和/标准差/方差 |
| `ts_min ts_max ts_median` | 滚动极值/中位数 |
| `ts_rank(x,w)` | 当前值在窗口内的百分位 |
| `ts_argmax ts_argmin` | 极值位置（0=窗口最早） |
| `ts_corr(x,y,w)` / `ts_cov` | 滚动相关/协方差 |
| `ts_quantile(x,w,q)` | 滚动分位数 |
| `ts_decay_linear(x,w)` / `ts_wma` | 线性衰减加权均值 |
| `ts_ema(x,span)` | 指数移动平均 |
| `ts_ir(x,w)` | 滚动 mean/std |
| `ts_zscore(x,w)` | 滚动 z 分数 |
| `ts_skew ts_kurt` | 偏度/峰度 |
| `ts_slope ts_rsquare ts_resi` | 对时间线性回归的斜率/R²/末端残差 |
| `ts_maxdiff ts_mindiff` | 相对滚动极值的差 |
| `ts_mad ts_product ts_count` | 滚动 MAD/乘积/有效样本数 |

### 截面（按日期）

| 算子 | 说明 |
|---|---|
| `cs_rank(x)` / `rank` | 百分位排名（0–1） |
| `cs_zscore(x)` / `zscore` | 截面标准化 |
| `cs_demean(x)` | 截面去均值 |
| `cs_scale(x)` | 除以绝对值和 |
| `cs_winsorize(x,k)` | 截面 MAD 去极值 |
| `cs_quantile(x,q)` | 截面分位阈值（广播） |
| `cs_corr(x,y)` | 截面相关 |
| `cs_indneutralize(x)` | 按 `Panel.industry_id` 行业内去均值 |
| `signed_power(x,a)` | `sign(x)·|x|^a` |

> 截面算子自动应用 universe 掩码；时序算子不掩码（需要完整历史）。

## 4. 示例

```text
# 量价
close / ts_mean(close, 20) - 1
ts_std(ret, 20) / ts_std(ret, 60)
ts_corr(close, volume, 20)
(close - ts_min(low, 60)) / (ts_max(high, 60) - ts_min(low, 60) + 1e-9)

# 资金
ts_mean(main_net_ratio, 5) - ts_mean(main_net_ratio, 20)
cs_rank(ts_mean(main_net_ratio, 20)) - cs_rank(close / delay(close, 20) - 1)

# 条件/非线性
where(gt(ret, 0), ret, 0)
abs(log(amount))
-signed_log(ts_zscore(turnover_f, 60))

# Alpha158 风格（翻译后）
(high - max(open, close)) / open
ts_rank(close, 20) / 20
ts_corr(close, log(volume + 1), 10)
```

## 5. 遗传规划

- 终端：28 个字段 + 常数 `{0.5,1,2,5,10}`；
- 函数：`+ - * /`、`neg abs log sign`、时序算子（窗口 5/10/20/60）、`cs_rank/cs_zscore`；
- 约束：深度 ≤4、节点 ≤28；
- 适应度：训练期截面 RankIC 绝对值 + 0.05×|ICIR| − 0.0002×节点数；
  其中 IC 在“对市值/价格/换手做快速中性化”后的因子上计算；
- 选择：3 元锦标赛；交叉 0.6；变异 0.3；精英 10%；
- 去重：按表达式字符串；Hall of Fame 按值相关性 >0.7 过滤；
- 复核：Top 候选在 Train/Valid/Test 三段跑完整预处理 + 月度闸门。

## 6. 扩展算子

在 `src/alphaforge/expr/ops.py` 中：

```python
@register("my_op", 2, "ts", "说明")
def _my_op(ctx, x, window):
    a = np.asarray(x, dtype=np.float32)
    w = _window_int(window)
    ...
    return _clean(out, ctx)
```

注册后自动对 parser、GP、报告生效；需补充单测并确保因果性。
