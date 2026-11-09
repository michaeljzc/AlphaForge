# 因子字典（中文说明）

共 **355** 个因子：内置 96 + WQ101 101 + Alpha158 158。

说明来自 `FactorDef.description`，Web「全部因子字典」、`alphaforge factors list --category all` 与 `/api/library` 使用同一份数据。

## 内置因子（不含 WQ101）（96）

| 因子 | 类别 | 中文说明 | 表达式 |
|---|---|---|---|
| `ret_1` | price_volume | 1 日收益（短期反转） | `ret` |
| `ret_5` | price_volume | 5 日收益 | `close / delay(close, 5) - 1` |
| `ret_20` | price_volume | 20 日动量 | `close / delay(close, 20) - 1` |
| `ret_60` | price_volume | 60 日动量 | `close / delay(close, 60) - 1` |
| `ret_120` | price_volume | 120 日动量 | `close / delay(close, 120) - 1` |
| `mom_20_5` | price_volume | 剔除近 5 日的 20 日动量 | `delay(close, 5) / delay(close, 25) - 1` |
| `ma_ratio_5` | price_volume | 价格对 5 日均线偏离 | `close / ts_mean(close, 5) - 1` |
| `ma_ratio_20` | price_volume | 价格对 20 日均线偏离 | `close / ts_mean(close, 20) - 1` |
| `ma_ratio_60` | price_volume | 价格对 60 日均线偏离 | `close / ts_mean(close, 60) - 1` |
| `ma_cross_5_20` | price_volume | 5/20 均线交叉 | `ts_mean(close, 5) / ts_mean(close, 20) - 1` |
| `ma_cross_20_60` | price_volume | 20/60 均线交叉 | `ts_mean(close, 20) / ts_mean(close, 60) - 1` |
| `breakout_20` | price_volume | 20 日新高突破 | `close / ts_max(close, 20) - 1` |
| `breakout_60` | price_volume | 60 日新高突破 | `close / ts_max(close, 60) - 1` |
| `breakout_120` | price_volume | 120 日新高突破 | `close / ts_max(close, 120) - 1` |
| `breakout_250` | price_volume | 250 日新高突破 | `close / ts_max(close, 250) - 1` |
| `drawdown_60` | price_volume | 距 60 日高点回撤 | `close / ts_max(close, 60) - 1` |
| `drawdown_250` | price_volume | 距 250 日高点回撤 | `close / ts_max(close, 250) - 1` |
| `price_pos_60` | price_volume | 60 日价格区间位置 | `(close - ts_min(low, 60)) / (ts_max(high, 60) - ts_min(low, 60) + 1e-09)` |
| `price_pos_250` | price_volume | 250 日价格区间位置 | `(close - ts_min(low, 250)) / (ts_max(high, 250) - ts_min(low, 250) + 1e-09)` |
| `volatility_20` | price_volume | 20 日波动率 | `ts_std(ret, 20)` |
| `volatility_60` | price_volume | 60 日波动率 | `ts_std(ret, 60)` |
| `vol_ratio_5_60` | price_volume | 短长波动比（波动压缩） | `ts_std(ret, 5) / ts_std(ret, 60)` |
| `skew_20` | price_volume | 20 日收益偏度 | `ts_skew(ret, 20)` |
| `kurt_20` | price_volume | 20 日收益峰度 | `ts_kurt(ret, 20)` |
| `max_ret_20` | price_volume | 20 日最大单日涨幅 | `ts_max(ret, 20)` |
| `min_ret_20` | price_volume | 20 日最大单日跌幅 | `ts_min(ret, 20)` |
| `up_ratio_20` | price_volume | 20 日上涨天数占比 | `ts_mean(gt(ret, 0), 20)` |
| `rsi_14` | price_volume | 相对强弱指标 RSI(14) | `ts_mean(max(ret, 0), 14) / (ts_mean(abs(ret), 14) + 1e-09)` |
| `volume_ratio_5` | price_volume | 5 日量比 | `volume / ts_mean(volume, 5)` |
| `volume_ratio_20` | price_volume | 20 日量比 | `volume / ts_mean(volume, 20)` |
| `volume_ratio_60` | price_volume | 60 日量比 | `volume / ts_mean(volume, 60)` |
| `volume_trend_5_60` | price_volume | 成交量放大趋势 | `ts_mean(volume, 5) / ts_mean(volume, 60)` |
| `amount_ratio_20` | price_volume | 成交额放大 | `amount / ts_mean(amount, 20)` |
| `turnover_mean_5` | price_volume | 5 日平均换手 | `ts_mean(turnover_f, 5)` |
| `turnover_mean_20` | price_volume | 20 日平均换手 | `ts_mean(turnover_f, 20)` |
| `turnover_rank_120` | price_volume | 换手率 120 日分位 | `ts_rank(turnover_f, 120)` |
| `turnover_z_60` | price_volume | 换手率 60 日 z 分数 | `(turnover_f - ts_mean(turnover_f, 60)) / (ts_std(turnover_f, 60) + 1e-12)` |
| `turnover_vol_20` | price_volume | 换手率波动 | `ts_std(turnover_f, 20)` |
| `amihud_20` | price_volume | Amihud 非流动性 | `ts_mean(abs(ret) / amount * 1000000000, 20)` |
| `corr_pv_20` | price_volume | 量价相关性 | `ts_corr(close, volume, 20)` |
| `corr_ret_vol_20` | price_volume | 收益-成交量相关性 | `ts_corr(ret, volume, 20)` |
| `klen` | price_volume | K 线长度 | `(high - low) / open` |
| `close_location` | price_volume | 收盘位置 | `(close - low) / (high - low + 1e-09)` |
| `upper_shadow` | price_volume | 上影线占比 | `(high - max(open, close)) / (high - low + 1e-09)` |
| `lower_shadow` | price_volume | 下影线占比 | `(min(open, close) - low) / (high - low + 1e-09)` |
| `gap` | price_volume | 隔夜跳空 | `open / delay(close, 1) - 1` |
| `vwap_dev` | price_volume | 收盘对 VWAP 偏离 | `close / vwap - 1` |
| `beta_60` | price_volume | 60 日市场 Beta | `ts_corr(ret, mkt_ret, 60)` |
| `idvol_60` | price_volume | 60 日特质波动 | `ts_std(ret - ts_corr(ret, mkt_ret, 60) * mkt_ret, 60)` |
| `corr_mkt_60` | price_volume | 与市场相关性 | `ts_corr(ret, mkt_ret, 60)` |
| `main_net_ratio` | money_flow | 主力资金净流入占比 | `main_net_ratio` |
| `main_net_ratio_5` | money_flow | 5 日主力净流入 | `ts_mean(main_net_ratio, 5)` |
| `main_net_ratio_20` | money_flow | 20 日主力净流入 | `ts_mean(main_net_ratio, 20)` |
| `main_net_consistency_20` | money_flow | 主力净流入连续性 | `ts_mean(gt(main_net, 0), 20)` |
| `main_net_vol_20` | money_flow | 主力资金波动 | `ts_std(main_net_ratio, 20)` |
| `net_mf_ratio_5` | money_flow | 5 日净流入占比 | `ts_mean(net_mf_ratio, 5)` |
| `money_flow_trend` | money_flow | 资金流入加速 | `ts_mean(main_net_ratio, 5) - ts_mean(main_net_ratio, 20)` |
| `limit_up_ratio_20` | money_flow | 20 日涨停占比 | `ts_mean(limit_up_flag, 20)` |
| `limit_up_sum_20` | money_flow | 20 日涨停次数 | `ts_sum(limit_up_flag, 20)` |
| `limit_down_ratio_20` | money_flow | 20 日跌停占比 | `ts_mean(limit_down_flag, 20)` |
| `ep` | value | 盈利收益率 E/P | `earnings_yield` |
| `bp` | value | 账面市值比 B/P | `book_to_price` |
| `sp` | value | 营收市值比 S/P | `sales_to_price` |
| `dy` | value | 股息率 | `dividend_yield` |
| `log_mv` | value | 对数流通市值（小市值） | `log_mv` |
| `log_total_mv` | value | 对数总市值 | `log_total_mv` |
| `roe` | quality_growth | 净资产收益率 ROE（PIT 财务） | `roe` |
| `netprofit_yoy` | quality_growth | 净利润同比 | `netprofit_yoy` |
| `or_yoy` | quality_growth | 营收同比 | `or_yoy` |
| `q_profit_yoy` | quality_growth | 单季净利润同比 | `q_profit_yoy` |
| `q_sales_yoy` | quality_growth | 单季营收同比 | `q_sales_yoy` |
| `grossprofit_margin` | quality_growth | 毛利率 | `grossprofit_margin` |
| `debt_to_assets` | quality_growth | 资产负债率 | `debt_to_assets` |
| `eps` | quality_growth | 每股收益 | `eps` |
| `bps` | quality_growth | 每股净资产 | `bps` |
| `launch_vol_surge_5` | launch | 5 日放量幅度 | `volume / ts_mean(volume, 5) - 1` |
| `launch_vol_surge_20` | launch | 20 日放量幅度 | `volume / ts_mean(volume, 20) - 1` |
| `launch_amount_surge_20` | launch | 成交额突增 | `amount / ts_mean(amount, 20) - 1` |
| `launch_turnover_surge_20` | launch | 换手突增 | `turnover_f / ts_mean(turnover_f, 20) - 1` |
| `launch_turnover_pct_120` | launch | 换手率历史分位 | `ts_rank(turnover_f, 120)` |
| `launch_breakout_60` | launch | 60 日突破幅度 | `close / ts_max(close, 60) - 1` |
| `launch_breakout_120` | launch | 120 日突破幅度 | `close / ts_max(close, 120) - 1` |
| `launch_consolidation` | launch | 波动压缩（启动前蓄势） | `ts_std(ret, 20) / ts_std(ret, 60)` |
| `launch_range_expansion` | launch | 振幅扩张 | `(high - low) / close / (ts_mean((high - low) / close, 20) + 1e-09)` |
| `launch_close_strength` | launch | 收盘强度 | `(close - low) / (high - low + 1e-09)` |
| `launch_ma_stack` | launch | 短期均线上穿 | `ts_mean(close, 5) / ts_mean(close, 20) - 1` |
| `launch_vol_price_resonance` | launch | 量价共振 | `ts_corr(ret, volume / ts_mean(volume, 20) - 1, 20)` |
| `launch_pre_vol_ratio` | launch | 启动前成交量抬升 | `ts_mean(volume, 5) / ts_mean(volume, 60)` |
| `launch_small_cap` | launch | 小市值弹性 | `-log_mv` |
| `launch_money_inflow_5` | launch | 启动前 5 日资金流入 | `ts_mean(main_net_ratio, 5)` |
| `launch_flow_price_div` | launch | 资金与价格背离 | `cs_rank(close / delay(close, 20) - 1) - cs_rank(ts_mean(main_net_ratio, 20))` |
| `launch_high_52w` | launch | 距 52 周高点 | `close / ts_max(high, 250) - 1` |
| `launch_volume_contraction` | launch | 成交量收敛 | `ts_std(volume, 20) / (ts_mean(volume, 20) + 1e-09)` |
| `launch_price_compression` | launch | 价格波动收敛 | `ts_std(ret, 20) / ts_std(ret, 120)` |
| `launch_limit_up_20` | launch | 近期涨停次数 | `ts_sum(limit_up_flag, 20)` |
| `launch_flow_trend` | launch | 资金流入加速 | `ts_mean(main_net_ratio, 5) - ts_mean(main_net_ratio, 20)` |

## WorldQuant 101（101）

| 因子 | 类别 | 中文说明 | 表达式 |
|---|---|---|---|
| `wq001` | wq101 | 收益为负时用20日波动率替代价格，平方后取5日最高点位置并截面排名，捕捉下行波动中的反转。 | `cs_rank(ts_argmax(signed_power(where(lt(ret, 0), ts_std(ret, 20), close), 2), 5)) - 0.5` |
| `wq002` | wq101 | 成交量对数2日变化与开收盘收益的秩相关（6日），取负向，衡量量价配合的反转。 | `-1 * ts_corr(cs_rank(delta(log(volume), 2)), cs_rank((close - open) / open), 6)` |
| `wq003` | wq101 | 开盘价与成交量的10日秩相关，取负向，衡量开盘放量后的反转。 | `-1 * ts_corr(cs_rank(open), cs_rank(volume), 10)` |
| `wq004` | wq101 | 低价截面排名的9日时序排名，取负向，短期反转因子。 | `-1 * ts_rank(cs_rank(low), 9)` |
| `wq005` | wq101 | 开盘价对10日VWAP均值的偏离，乘以收盘对VWAP偏离的负绝对值，衡量价格与均价背离。 | `cs_rank(open - ts_sum(vwap, 10) / 10) * (-1 * abs(cs_rank(close - vwap)))` |
| `wq006` | wq101 | 开盘价与成交量的10日相关，取负向。 | `-1 * ts_corr(open, volume, 10)` |
| `wq007` | wq101 | 放量（volume>adv20）时，7日价格变化绝对值的60日时序排名乘以变化方向，取负向。 | `where(lt(ts_mean(amount, 20), volume), -1 * ts_rank(abs(delta(close, 7)), 60) * sign(delta(close, 7)), -1 * 1)` |
| `wq008` | wq101 | 5日开盘和与5日收益和乘积的10日变化，取负向，量价配合反转。 | `-1 * cs_rank(ts_sum(open, 5) * ts_sum(ret, 5) - delay(ts_sum(open, 5) * ts_sum(ret, 5), 10))` |
| `wq009` | wq101 | 5日价格变化的最小值>0 取变化，最大值<0 取变化，否则反向，趋势确认。 | `where(lt(0, ts_min(delta(close, 1), 5)), delta(close, 1), where(lt(ts_max(delta(close, 1), 5), 0), delta(close, 1), -1 * delta(close, 1)))` |
| `wq010` | wq101 | 同Alpha#9，使用4日窗口并在外层做截面排名。 | `cs_rank(where(lt(0, ts_min(delta(close, 1), 4)), delta(close, 1), where(lt(ts_max(delta(close, 1), 4), 0), delta(close, 1), -1 * delta(close, 1))))` |
| `wq011` | wq101 | 3日VWAP与收盘价差的极值排名，乘以3日成交量变化排名。 | `(cs_rank(ts_max(vwap - close, 3)) + cs_rank(ts_min(vwap - close, 3))) * cs_rank(delta(volume, 3))` |
| `wq012` | wq101 | 成交量变化方向乘以价格变化的负向，量价背离。 | `sign(delta(volume, 1)) * (-1 * delta(close, 1))` |
| `wq013` | wq101 | 收盘价与成交量秩的5日协方差排名，取负向。 | `-1 * cs_rank(ts_cov(cs_rank(close), cs_rank(volume), 5))` |
| `wq014` | wq101 | 3日收益变化排名乘以开盘价与成交量的10日相关，取负向。 | `-1 * cs_rank(delta(ret, 3)) * ts_corr(open, volume, 10)` |
| `wq015` | wq101 | 高价与成交量3日秩相关，3日求和后排名，取负向。 | `-1 * ts_sum(cs_rank(ts_corr(cs_rank(high), cs_rank(volume), 3)), 3)` |
| `wq016` | wq101 | 高价与成交量5日秩协方差排名，取负向。 | `-1 * cs_rank(ts_cov(cs_rank(high), cs_rank(volume), 5))` |
| `wq017` | wq101 | 收盘10日时序排名、价格二阶差分排名、量比5日时序排名三者相乘。 | `-1 * cs_rank(ts_rank(close, 10)) * cs_rank(delta(delta(close, 1), 1)) * cs_rank(ts_rank(volume / ts_mean(amount, 20), 5))` |
| `wq018` | wq101 | 5日绝对日内收益波动、日内收益、开收盘10日相关之和，排名取负向。 | `-1 * cs_rank(ts_std(abs(close - open), 5) + (close - open) + ts_corr(close, open, 10))` |
| `wq019` | wq101 | 7日价格趋势方向乘以(1+250日收益排名)，取负向。 | `-1 * sign(close - delay(close, 7) + delta(close, 7)) * (1 + cs_rank(1 + ts_sum(ret, 250)))` |
| `wq020` | wq101 | 开盘价相对昨日高/收/低偏离的排名乘积。 | `-1 * cs_rank(open - delay(high, 1)) * cs_rank(open - delay(close, 1)) * cs_rank(open - delay(low, 1))` |
| `wq021` | wq101 | 8日/2日均线、波动带与量比条件的多状态信号（-1/1）。 | `where(lt(ts_sum(close, 8) / 8 + ts_std(close, 8), ts_sum(close, 2) / 2), -1 * 1, where(lt(ts_sum(close, 2) / 2, ts_sum(close, 8) / 8 - ts_std(close, 8)), 1, where(or(lt(1, volume / ts_mean(amount, 20)), eq(volume / ts_mean(amount, 20), 1)), 1, -1 * 1)))` |
| `wq022` | wq101 | 高价与成交量5日相关的变化，乘以20日收盘波动排名，取负向。 | `-1 * (delta(ts_corr(high, volume, 5), 5) * cs_rank(ts_std(close, 20)))` |
| `wq023` | wq101 | 20日高价均线低于现价时做2日高价变化，否则为0。 | `where(lt(ts_sum(high, 20) / 20, high), -1 * delta(high, 2), 0)` |
| `wq024` | wq101 | 100日均线100日变化<0.05时做100日区间下沿反转，否则做3日反转。 | `where(or(lt(delta(ts_sum(close, 100) / 100, 100) / delay(close, 100), 0.05), eq(delta(ts_sum(close, 100) / 100, 100) / delay(close, 100), 0.05)), -1 * (close - ts_min(close, 100)), -1 * delta(close, 3))` |
| `wq025` | wq101 | 收益、adv20、VWAP、上影线的组合，取负向。 | `cs_rank(-1 * ret * ts_mean(amount, 20) * vwap * (high - close))` |
| `wq026` | wq101 | 成交量与高价5日时序排名的相关，3日最大值，取负向。 | `-1 * ts_max(ts_corr(ts_rank(volume, 5), ts_rank(high, 5), 5), 3)` |
| `wq027` | wq101 | 成交量与VWAP6日秩相关2日均值>0.5时取-1，否则1。 | `where(lt(0.5, cs_rank(ts_sum(ts_corr(cs_rank(volume), cs_rank(vwap), 6), 2) / 2)), -1 * 1, 1)` |
| `wq028` | wq101 | adv20与低价的5日相关加中间价减收盘，截面scale。 | `cs_scale(ts_corr(ts_mean(amount, 20), low, 5) + (high + low) / 2 - close)` |
| `wq029` | wq101 | 价格秩的复杂嵌套加6日延迟收益，取极小值组合。 | `ts_min(ts_product(cs_rank(cs_rank(cs_scale(log(ts_sum(ts_min(cs_rank(cs_rank(-1 * cs_rank(delta(close - 1, 5)))), 2), 1))))), 1), 5) + ts_rank(delay(-1 * ret, 6), 5)` |
| `wq030` | wq101 | 价格变化符号和，乘以5日/20日成交量。 | `(1 - cs_rank(sign(close - delay(close, 1)) + sign(delay(close, 1) - delay(close, 2)) + sign(delay(close, 2) - delay(close, 3)))) * ts_sum(volume, 5) / ts_sum(volume, 20)` |
| `wq031` | wq101 | 10日价格变化秩的10日线性衰减，加3日变化和adv20/低价12日相关。 | `cs_rank(cs_rank(cs_rank(ts_decay_linear(-1 * cs_rank(cs_rank(delta(close, 10))), 10)))) + cs_rank(-1 * delta(close, 3)) + sign(cs_scale(ts_corr(ts_mean(amount, 20), low, 12)))` |
| `wq032` | wq101 | 7日均线偏离，加20倍VWAP与5日前收盘的230日相关。 | `cs_scale(ts_sum(close, 7) / 7 - close) + 20 * cs_scale(ts_corr(vwap, delay(close, 5), 230))` |
| `wq033` | wq101 | 开盘/收盘比值的负一次方排名。 | `cs_rank(-1 * (1 - open / close)^1)` |
| `wq034` | wq101 | 2日/5日波动比加1日变化排名。 | `cs_rank(1 - cs_rank(ts_std(ret, 2) / ts_std(ret, 5)) + (1 - cs_rank(delta(close, 1))))` |
| `wq035` | wq101 | 32日成交量时序排名×(1-16日价格区间时序排名)×(1-32日收益时序排名)。 | `ts_rank(volume, 32) * (1 - ts_rank(close + high - low, 16)) * (1 - ts_rank(ret, 32))` |
| `wq036` | wq101 | 5个子信号加权：开收盘、开收盘排名、延迟收益、VWAP/adv20、200日均线。 | `2.21 * cs_rank(ts_corr(close - open, delay(volume, 1), 15)) + 0.7 * cs_rank(open - close) + 0.73 * cs_rank(ts_rank(delay(-1 * ret, 6), 5)) + cs_rank(abs(ts_corr(vwap, ts_mean(amount, 20), 6))) + 0.6 * cs_rank((ts_sum(close, 200) / 200 - open) * (close - open))` |
| `wq037` | wq101 | 开收盘1日延迟与收盘的200日相关，加开收盘。 | `cs_rank(ts_corr(delay(open - close, 1), close, 200)) + cs_rank(open - close)` |
| `wq038` | wq101 | 收盘10日时序排名乘以收盘/开盘。 | `-1 * cs_rank(ts_rank(close, 10)) * cs_rank(close / open)` |
| `wq039` | wq101 | 7日价格变化×(1-量比9日衰减排名)×(1+250日收益排名)。 | `-1 * cs_rank(delta(close, 7) * (1 - cs_rank(ts_decay_linear(volume / ts_mean(amount, 20), 9)))) * (1 + cs_rank(ts_sum(ret, 250)))` |
| `wq040` | wq101 | 高价10日波动排名×高价与成交量10日相关，取负向。 | `-1 * cs_rank(ts_std(high, 10)) * ts_corr(high, volume, 10)` |
| `wq041` | wq101 | 最高价与最低价的几何均值减VWAP。 | `(high * low)^0.5 - vwap` |
| `wq042` | wq101 | VWAP-收盘与VWAP+收盘的秩比。 | `cs_rank(vwap - close) / cs_rank(vwap + close)` |
| `wq043` | wq101 | 量比20日时序排名×负7日价格变化8日时序排名。 | `ts_rank(volume / ts_mean(amount, 20), 20) * ts_rank(-1 * delta(close, 7), 8)` |
| `wq044` | wq101 | 高价与成交量秩的5日相关，取负向。 | `-1 * ts_corr(high, cs_rank(volume), 5)` |
| `wq045` | wq101 | 5日前收盘20日均值排名×收盘与成交量2日相关×5日/20日收盘和2日相关，取负向。 | `-1 * (cs_rank(ts_sum(delay(close, 5), 20) / 20) * ts_corr(close, volume, 2) * cs_rank(ts_corr(ts_sum(close, 5), ts_sum(close, 20), 2)))` |
| `wq046` | wq101 | 20/10/现价的20日、10日趋势状态，负向时反向。 | `where(lt(0.25, (delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10), -1 * 1, where(lt((delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10, 0), 1, -1 * 1 * (close - delay(close, 1))))` |
| `wq047` | wq101 | 1/收盘排名×量/adv20×上影线/5日均高，再减VWAP变化排名。 | `cs_rank(1 / close) * volume / ts_mean(amount, 20) * (high * cs_rank(high - close) / (ts_sum(high, 5) / 5)) - cs_rank(vwap - delay(vwap, 5))` |
| `wq048` | wq101 | 250日价格变化与收益变化的相关×价格变化/收盘，行业中性后除以250日平方收益和。 | `cs_indneutralize(ts_corr(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1) / close) / ts_sum((delta(close, 1) / delay(close, 1))^2, 250)` |
| `wq049` | wq101 | 同Alpha#46，阈值改为-0.1。 | `where(lt((delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10, -1 * 0.1), 1, -1 * 1 * (close - delay(close, 1)))` |
| `wq050` | wq101 | 成交量与VWAP5日秩相关，5日最大值后排名，取负向。 | `-1 * ts_max(cs_rank(ts_corr(cs_rank(volume), cs_rank(vwap), 5)), 5)` |
| `wq051` | wq101 | 同Alpha#46，阈值改为-0.05。 | `where(lt((delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10, -1 * 0.05), 1, -1 * 1 * (close - delay(close, 1)))` |
| `wq052` | wq101 | 5日最低价变化×240/20日收益差排名×5日成交量排名。 | `(-1 * ts_min(low, 5) + delay(ts_min(low, 5), 5)) * cs_rank((ts_sum(ret, 240) - ts_sum(ret, 20)) / 220) * ts_rank(volume, 5)` |
| `wq053` | wq101 | 收盘-低-(高-收盘) / (收盘-低) 的9日变化，取负向。 | `-1 * delta((close - low - (high - close)) / (close - low), 9)` |
| `wq054` | wq101 | (低-收)×开^5 / ((低-高)×收^5)，取负向。 | `-1 * ((low - close) * open^5) / ((low - high) * close^5)` |
| `wq055` | wq101 | 12日价格区间位置排名×成交量排名6日相关，取负向。 | `-1 * ts_corr(cs_rank((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12))), cs_rank(volume), 6)` |
| `wq056` | wq101 | 10日收益和/2日收益和3日滚动×收益×市值排名，取负向。 | `0 - 1 * (cs_rank(ts_sum(ret, 10) / ts_sum(ts_sum(ret, 2), 3)) * cs_rank(ret * circ_mv))` |
| `wq057` | wq101 | (收盘-VWAP)/2日衰减的30日最高价位置排名，取负向。 | `0 - 1 * ((close - vwap) / ts_decay_linear(cs_rank(ts_argmax(close, 30)), 2))` |
| `wq058` | wq101 | VWAP行业中性后与成交量3.9日相关，7.9日衰减后5.5日时序排名，取负向。 | `-1 * ts_rank(ts_decay_linear(ts_corr(cs_indneutralize(vwap), volume, 3.92795), 7.89291), 5.50322)` |
| `wq059` | wq101 | 混合VWAP行业中性后与成交量4.25日相关，16.2日衰减后8.2日时序排名，取负向。 | `-1 * ts_rank(ts_decay_linear(ts_corr(cs_indneutralize(vwap * 0.728317 + vwap * (1 - 0.728317)), volume, 4.25197), 16.2289), 8.19648)` |
| `wq060` | wq101 | 2×scale(区间位置×成交量排名)-scale(10日最高价位置排名)。 | `0 - 1 * (2 * cs_scale(cs_rank((close - low - (high - close)) / (high - low) * volume)) - cs_scale(cs_rank(ts_argmax(close, 10))))` |
| `wq061` | wq101 | VWAP距16日低点排名 < VWAP与adv180的17.9日相关排名。 | `lt(cs_rank(vwap - ts_min(vwap, 16.1219)), cs_rank(ts_corr(vwap, ts_mean(amount, 180), 17.9282)))` |
| `wq062` | wq101 | VWAP与adv20的和9.9日相关排名 < 开盘/中间价/高价秩和，取负向。 | `lt(cs_rank(ts_corr(vwap, ts_sum(ts_mean(amount, 20), 22.4101), 9.91009)), cs_rank(lt(cs_rank(open) + cs_rank(open), cs_rank((high + low) / 2) + cs_rank(high)))) * -1` |
| `wq063` | wq101 | 行业中性收盘2.25日变化8.22日衰减排名 - 混合价与adv180和13.56日相关12.29日衰减排名，取负向。 | `(cs_rank(ts_decay_linear(delta(cs_indneutralize(close), 2.25164), 8.22237)) - cs_rank(ts_decay_linear(ts_corr(vwap * 0.318108 + open * (1 - 0.318108), ts_sum(ts_mean(amount, 180), 37.2467), 13.557), 12.2883))) * -1` |
| `wq064` | wq101 | 混合开低12.7日均值与adv120和16.6日相关排名 < 中间价/VWAP3.7日变化排名，取负向。 | `lt(cs_rank(ts_corr(ts_sum(open * 0.178404 + low * (1 - 0.178404), 12.7054), ts_sum(ts_mean(amount, 120), 12.7054), 16.6208)), cs_rank(delta((high + low) / 2 * 0.178404 + vwap * (1 - 0.178404), 3.69741))) * -1` |
| `wq065` | wq101 | 混合开VWAP与adv60的6.4日相关排名 < 开盘距13.6日低点排名，取负向。 | `lt(cs_rank(ts_corr(open * 0.00817205 + vwap * (1 - 0.00817205), ts_sum(ts_mean(amount, 60), 8.6911), 6.40374)), cs_rank(open - ts_min(open, 13.635))) * -1` |
| `wq066` | wq101 | VWAP3.5日变化7.2日衰减排名 + 低价与中间价差/开盘-中间价11.4日衰减6.7日时序排名，取负向。 | `(cs_rank(ts_decay_linear(delta(vwap, 3.51013), 7.23052)) + ts_rank(ts_decay_linear((low * 0.96633 + low * (1 - 0.96633) - vwap) / (open - (high + low) / 2), 11.4157), 6.72611)) * -1` |
| `wq067` | wq101 | 高价距2.15日低点排名 ^ 行业中性VWAP与行业中性adv20的6.03日相关排名，取负向。 | `cs_rank(high - ts_min(high, 2.14593))^cs_rank(ts_corr(cs_indneutralize(vwap), cs_indneutralize(ts_mean(amount, 20)), 6.02936)) * -1` |
| `wq068` | wq101 | 高价与adv15秩8.9日相关13.9日时序排名 < 混合收盘低价1.06日变化排名，取负向。 | `lt(ts_rank(ts_corr(cs_rank(high), cs_rank(ts_mean(amount, 15)), 8.91644), 13.9333), cs_rank(delta(close * 0.518371 + low * (1 - 0.518371), 1.06157))) * -1` |
| `wq069` | wq101 | 行业中性VWAP2.72日变化4.79日最大排名 ^ 混合价与adv20的4.92日相关9.06日时序排名，取负向。 | `cs_rank(ts_max(delta(cs_indneutralize(vwap), 2.72412), 4.79344))^ts_rank(ts_corr(close * 0.490655 + vwap * (1 - 0.490655), ts_mean(amount, 20), 4.92416), 9.0615) * -1` |
| `wq070` | wq101 | VWAP1.29日变化排名 ^ 行业中性收盘与adv50的17.8日相关17.9日时序排名，取负向。 | `cs_rank(delta(vwap, 1.29456))^ts_rank(ts_corr(cs_indneutralize(close), ts_mean(amount, 50), 17.8256), 17.9171) * -1` |
| `wq071` | wq101 | 两个衰减相关时序排名的较大者：收盘3.44日/adv18012.06日，低价+开盘-2VWAP平方16.47日。 | `max(ts_rank(ts_decay_linear(ts_corr(ts_rank(close, 3.43976), ts_rank(ts_mean(amount, 180), 12.0647), 18.0175), 4.20501), 15.6948), ts_rank(ts_decay_linear(cs_rank(low + open - (vwap + vwap))^2, 16.4662), 4.4388))` |
| `wq072` | wq101 | 中间价/adv40的8.93日相关10.15日衰减排名 / VWAP与成交量3.72/18.52日时序相关6.87日衰减排名。 | `cs_rank(ts_decay_linear(ts_corr((high + low) / 2, ts_mean(amount, 40), 8.93345), 10.1519)) / cs_rank(ts_decay_linear(ts_corr(ts_rank(vwap, 3.72469), ts_rank(volume, 18.5188), 6.86671), 2.95011))` |
| `wq073` | wq101 | max(VWAP4.73日变化2.92日衰减排名, 混合开低2.04日变化3.34日衰减16.74日时序排名)，取负向。 | `max(cs_rank(ts_decay_linear(delta(vwap, 4.72775), 2.91864)), ts_rank(ts_decay_linear(delta(open * 0.147155 + low * (1 - 0.147155), 2.03608) / (open * 0.147155 + low * (1 - 0.147155)) * -1, 3.33829), 16.7411)) * -1` |
| `wq074` | wq101 | 收盘与adv30和15.14日相关排名 < 混合高价VWAP/成交量11.48日相关排名，取负向。 | `lt(cs_rank(ts_corr(close, ts_sum(ts_mean(amount, 30), 37.4843), 15.1365)), cs_rank(ts_corr(cs_rank(high * 0.0261661 + vwap * (1 - 0.0261661)), cs_rank(volume), 11.4791))) * -1` |
| `wq075` | wq101 | VWAP与成交量4.24日相关排名 < 低价/adv50的12.44日相关排名。 | `lt(cs_rank(ts_corr(vwap, volume, 4.24304)), cs_rank(ts_corr(cs_rank(low), cs_rank(ts_mean(amount, 50)), 12.4413)))` |
| `wq076` | wq101 | max(VWAP1.24日变化11.83日衰减排名, 行业中性低价/adv81的8.15日相关19.57日时序衰减19.38日时序排名)，取负向。 | `max(cs_rank(ts_decay_linear(delta(vwap, 1.24383), 11.8259)), ts_rank(ts_decay_linear(ts_rank(ts_corr(cs_indneutralize(low), ts_mean(amount, 81), 8.14941), 19.569), 17.1543), 19.383)) * -1` |
| `wq077` | wq101 | min(中间价+高-2VWAP的20.05日衰减排名, 中间价/adv40的3.16日相关5.64日衰减排名)。 | `min(cs_rank(ts_decay_linear((high + low) / 2 + high - (vwap + high), 20.0451)), cs_rank(ts_decay_linear(ts_corr((high + low) / 2, ts_mean(amount, 40), 3.1614), 5.64125)))` |
| `wq078` | wq101 | 混合低价VWAP19.74日与adv40和6.83日相关排名 ^ VWAP/成交量5.77日秩相关排名。 | `cs_rank(ts_corr(ts_sum(low * 0.352233 + vwap * (1 - 0.352233), 19.7428), ts_sum(ts_mean(amount, 40), 19.7428), 6.83313))^cs_rank(ts_corr(cs_rank(vwap), cs_rank(volume), 5.77492))` |
| `wq079` | wq101 | 行业中性混合收盘开盘1.23日变化排名 < VWAP3.61日/adv1509.19日时序相关14.66日时序排名。 | `lt(cs_rank(delta(cs_indneutralize(close * 0.60733 + open * (1 - 0.60733)), 1.23438)), cs_rank(ts_corr(ts_rank(vwap, 3.60973), ts_rank(ts_mean(amount, 150), 9.18637), 14.6644)))` |
| `wq080` | wq101 | 行业中性混合开高4.05日变化符号排名 ^ 高价adv10的5.11日相关5.54日时序排名，取负向。 | `cs_rank(sign(delta(cs_indneutralize(open * 0.868128 + high * (1 - 0.868128)), 4.04545)))^ts_rank(ts_corr(high, ts_mean(amount, 10), 5.11456), 5.53756) * -1` |
| `wq081` | wq101 | log(product(rank(rank(VWAP/adv10的8.48日相关^4)),14.97))排名 < VWAP/成交量5.08日秩相关排名，取负向。 | `lt(cs_rank(log(ts_product(cs_rank(cs_rank(ts_corr(vwap, ts_sum(ts_mean(amount, 10), 49.6054), 8.47743))^4), 14.9655))), cs_rank(ts_corr(cs_rank(vwap), cs_rank(volume), 5.07914))) * -1` |
| `wq082` | wq101 | min(开盘1.46日变化14.87日衰减排名, 行业中性成交量与混合开盘17.48日相关6.92日衰减13.43日时序排名)，取负向。 | `min(cs_rank(ts_decay_linear(delta(open, 1.46063), 14.8717)), ts_rank(ts_decay_linear(ts_corr(cs_indneutralize(volume), open * 0.634196 + open * (1 - 0.634196), 17.4842), 6.92131), 13.4283)) * -1` |
| `wq083` | wq101 | 2日延迟的区间/5日均收 × 成交量排名² / (区间/5日均收/(VWAP-收盘))。 | `cs_rank(delay((high - low) / (ts_sum(close, 5) / 5), 2)) * cs_rank(cs_rank(volume)) / ((high - low) / (ts_sum(close, 5) / 5) / (vwap - close))` |
| `wq084` | wq101 | SignedPower(20日VWAP距15.32日高点时序排名, 4.97日收盘变化)。 | `signed_power(ts_rank(vwap - ts_max(vwap, 15.3217), 20.7127), delta(close, 4.96796))` |
| `wq085` | wq101 | 混合高收/adv30的9.61日相关排名 ^ 中间价3.71日/成交量10.16日时序相关7.11日时序排名。 | `cs_rank(ts_corr(high * 0.876703 + close * (1 - 0.876703), ts_mean(amount, 30), 9.61331))^cs_rank(ts_corr(ts_rank((high + low) / 2, 3.70596), ts_rank(volume, 10.1595), 7.11408))` |
| `wq086` | wq101 | 收盘/adv20和14.74日相关6日时序排名 < 开盘+收盘-VWAP-开盘排名，取负向。 | `lt(ts_rank(ts_corr(close, ts_sum(ts_mean(amount, 20), 14.7444), 6.00049), 20.4195), cs_rank(open + close - (vwap + open))) * -1` |
| `wq087` | wq101 | max(混合收盘VWAP1.91日变化2.65日衰减排名, 行业中性adv81与收盘13.41日相关绝对4.90日衰减14.45日时序排名)，取负向。 | `max(cs_rank(ts_decay_linear(delta(close * 0.369701 + vwap * (1 - 0.369701), 1.91233), 2.65461)), ts_rank(ts_decay_linear(abs(ts_corr(cs_indneutralize(ts_mean(amount, 81)), close, 13.4132)), 4.89768), 14.4535)) * -1` |
| `wq088` | wq101 | min(开低高收秩组合8.07日衰减排名, 收盘8.45日/adv60 20.70日时序相关6.65日衰减2.62日时序排名)。 | `min(cs_rank(ts_decay_linear(cs_rank(open) + cs_rank(low) - (cs_rank(high) + cs_rank(close)), 8.06882)), ts_rank(ts_decay_linear(ts_corr(ts_rank(close, 8.44728), ts_rank(ts_mean(amount, 60), 20.6966), 8.01266), 6.65053), 2.61957))` |
| `wq089` | wq101 | 低价/adv10的6.94日相关5.52日衰减3.80日时序排名 - 行业中性VWAP3.48日变化10.15日衰减15.30日时序排名。 | `ts_rank(ts_decay_linear(ts_corr(low * 0.967285 + low * (1 - 0.967285), ts_mean(amount, 10), 6.94279), 5.51607), 3.79744) - ts_rank(ts_decay_linear(delta(cs_indneutralize(vwap), 3.48158), 10.1466), 15.3012)` |
| `wq090` | wq101 | 收盘距4.67日高点排名 ^ 行业中性adv40与低价5.38日相关3.22日时序排名，取负向。 | `cs_rank(close - ts_max(close, 4.66719))^ts_rank(ts_corr(cs_indneutralize(ts_mean(amount, 40)), low, 5.38375), 3.21856) * -1` |
| `wq091` | wq101 | 行业中性收盘/成交量9.75日相关16.40日衰减3.83日衰减4.87日时序排名 - VWAP/adv30的4.01日相关2.68日衰减排名，取负向。 | `(ts_rank(ts_decay_linear(ts_decay_linear(ts_corr(cs_indneutralize(close), volume, 9.74928), 16.398), 3.83219), 4.8667) - cs_rank(ts_decay_linear(ts_corr(vwap, ts_mean(amount, 30), 4.01303), 2.6809))) * -1` |
| `wq092` | wq101 | min(中间价+收盘<低+开盘的14.72日衰减18.87日时序排名, 低价/adv30的7.59日相关6.94日衰减6.81日时序排名)。 | `min(ts_rank(ts_decay_linear(lt((high + low) / 2 + close, low + open), 14.7221), 18.8683), ts_rank(ts_decay_linear(ts_corr(cs_rank(low), cs_rank(ts_mean(amount, 30)), 7.58555), 6.94024), 6.80584))` |
| `wq093` | wq101 | 行业中性VWAP/adv81的17.42日相关19.85日衰减7.54日时序排名 / 混合收盘VWAP2.77日变化16.27日衰减排名。 | `ts_rank(ts_decay_linear(ts_corr(cs_indneutralize(vwap), ts_mean(amount, 81), 17.4193), 19.848), 7.54455) / cs_rank(ts_decay_linear(delta(close * 0.524434 + vwap * (1 - 0.524434), 2.77377), 16.2664))` |
| `wq094` | wq101 | VWAP距11.58日低点排名 ^ VWAP19.65日/adv60 4.03日时序相关18.09日时序相关2.71日时序排名，取负向。 | `cs_rank(vwap - ts_min(vwap, 11.5783))^ts_rank(ts_corr(ts_rank(vwap, 19.6462), ts_rank(ts_mean(amount, 60), 4.02992), 18.0926), 2.70756) * -1` |
| `wq095` | wq101 | 开盘距12.41日低点排名 < (中间价/adv40的12.87日相关排名^5)的11.76日时序排名。 | `lt(cs_rank(open - ts_min(open, 12.4105)), ts_rank(cs_rank(ts_corr(ts_sum((high + low) / 2, 19.1351), ts_sum(ts_mean(amount, 40), 19.1351), 12.8742))^5, 11.7584))` |
| `wq096` | wq101 | max(VWAP/成交量3.84日秩相关4.17日衰减8.38日时序排名, 30日相关12.66日时序最大14.04日衰减13.41日时序排名)，取负向。 | `max(ts_rank(ts_decay_linear(ts_corr(cs_rank(vwap), cs_rank(volume), 3.83878), 4.16783), 8.38151), ts_rank(ts_decay_linear(ts_argmax(ts_corr(ts_rank(close, 7.45404), ts_rank(ts_mean(amount, 60), 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1` |
| `wq097` | wq101 | 行业中性混合低VWAP3.37日变化20.45日衰减排名 - 低价7.88日/adv60 17.26日时序相关4.98日时序18.59日衰减15.72日时序6.72日时序排名，取负向。 | `(cs_rank(ts_decay_linear(delta(cs_indneutralize(low * 0.721001 + vwap * (1 - 0.721001)), 3.3705), 20.4523)) - ts_rank(ts_decay_linear(ts_rank(ts_corr(ts_rank(low, 7.87871), ts_rank(ts_mean(amount, 60), 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1` |
| `wq098` | wq101 | VWAP/adv5和26.47日相关7.18日衰减排名 - 开盘/adv15的20.82日秩相关8.63日时序6.96日时序8.07日衰减排名。 | `cs_rank(ts_decay_linear(ts_corr(vwap, ts_sum(ts_mean(amount, 5), 26.4719), 4.58418), 7.18088)) - cs_rank(ts_decay_linear(ts_rank(ts_argmin(ts_corr(cs_rank(open), cs_rank(ts_mean(amount, 15)), 20.8187), 8.62571), 6.95668), 8.07206))` |
| `wq099` | wq101 | 中间价19.90日和/adv60 19.90日和8.81日相关排名 < 低价与成交量6.28日相关排名，取负向。 | `lt(cs_rank(ts_corr(ts_sum((high + low) / 2, 19.8975), ts_sum(ts_mean(amount, 60), 19.8975), 8.8136)), cs_rank(ts_corr(low, volume, 6.28259))) * -1` |
| `wq100` | wq101 | 1.5×行业中性(区间位置×成交量秩) - 行业中性(收盘/adv20 5日相关 - 30日最低价位置排名)，再乘量比。 | `0 - 1 * ((1.5 * cs_scale(cs_indneutralize(cs_indneutralize(cs_rank((close - low - (high - close)) / (high - low) * volume)))) - cs_scale(cs_indneutralize(ts_corr(close, cs_rank(ts_mean(amount, 20)), 5) - cs_rank(ts_argmin(close, 30))))) * (volume / ts_mean(amount, 20)))` |
| `wq101` | wq101 | (收盘-开盘)/(最高-最低+0.001)，日内收益相对振幅。 | `(close - open) / (high - low + 0.001)` |

## Qlib Alpha158（158）

| 因子 | 类别 | 中文说明 | 表达式 |
|---|---|---|---|
| `a158_KMID` | alpha158 | 日内收益：(收盘-开盘)/开盘 | `(close-open)/open` |
| `a158_KLEN` | alpha158 | K线振幅：(最高-最低)/开盘 | `(high-low)/open` |
| `a158_KMID2` | alpha158 | 实体占振幅比：(收盘-开盘)/(最高-最低) | `(close-open)/(high-low+1e-12)` |
| `a158_KUP` | alpha158 | 上影线/开盘：(最高-max(开,收))/开盘 | `(high-max(open, close))/open` |
| `a158_KUP2` | alpha158 | 上影线占振幅比 | `(high-max(open, close))/(high-low+1e-12)` |
| `a158_KLOW` | alpha158 | 下影线/开盘：(min(开,收)-最低)/开盘 | `(min(open, close)-low)/open` |
| `a158_KLOW2` | alpha158 | 下影线占振幅比 | `(min(open, close)-low)/(high-low+1e-12)` |
| `a158_KSFT` | alpha158 | 收盘位置：(2×收-高-低)/开盘 | `(2*close-high-low)/open` |
| `a158_KSFT2` | alpha158 | 收盘位置占振幅比 | `(2*close-high-low)/(high-low+1e-12)` |
| `a158_OPEN0` | alpha158 | 开盘价/收盘价 | `open/close` |
| `a158_HIGH0` | alpha158 | 最高价/收盘价 | `high/close` |
| `a158_LOW0` | alpha158 | 最低价/收盘价 | `low/close` |
| `a158_VWAP0` | alpha158 | VWAP/收盘价 | `vwap/close` |
| `a158_ROC5` | alpha158 | 5日收益率 | `delay(close, 5)/close` |
| `a158_ROC10` | alpha158 | 10日收益率 | `delay(close, 10)/close` |
| `a158_ROC20` | alpha158 | 20日收益率 | `delay(close, 20)/close` |
| `a158_ROC30` | alpha158 | 30日收益率 | `delay(close, 30)/close` |
| `a158_ROC60` | alpha158 | 60日收益率 | `delay(close, 60)/close` |
| `a158_MA5` | alpha158 | 收盘价/5日均线 | `ts_mean(close, 5)/close` |
| `a158_MA10` | alpha158 | 收盘价/10日均线 | `ts_mean(close, 10)/close` |
| `a158_MA20` | alpha158 | 收盘价/20日均线 | `ts_mean(close, 20)/close` |
| `a158_MA30` | alpha158 | 收盘价/30日均线 | `ts_mean(close, 30)/close` |
| `a158_MA60` | alpha158 | 收盘价/60日均线 | `ts_mean(close, 60)/close` |
| `a158_STD5` | alpha158 | 5日收益波动率 | `ts_std(close, 5)/close` |
| `a158_STD10` | alpha158 | 10日收益波动率 | `ts_std(close, 10)/close` |
| `a158_STD20` | alpha158 | 20日收益波动率 | `ts_std(close, 20)/close` |
| `a158_STD30` | alpha158 | 30日收益波动率 | `ts_std(close, 30)/close` |
| `a158_STD60` | alpha158 | 60日收益波动率 | `ts_std(close, 60)/close` |
| `a158_BETA5` | alpha158 | 5日收益对时间回归的斜率 | `ts_slope(close, 5)/close` |
| `a158_BETA10` | alpha158 | 10日收益对时间回归的斜率 | `ts_slope(close, 10)/close` |
| `a158_BETA20` | alpha158 | 20日收益对时间回归的斜率 | `ts_slope(close, 20)/close` |
| `a158_BETA30` | alpha158 | 30日收益对时间回归的斜率 | `ts_slope(close, 30)/close` |
| `a158_BETA60` | alpha158 | 60日收益对时间回归的斜率 | `ts_slope(close, 60)/close` |
| `a158_RSQR5` | alpha158 | 5日收益线性回归的R² | `ts_rsquare(close, 5)` |
| `a158_RSQR10` | alpha158 | 10日收益线性回归的R² | `ts_rsquare(close, 10)` |
| `a158_RSQR20` | alpha158 | 20日收益线性回归的R² | `ts_rsquare(close, 20)` |
| `a158_RSQR30` | alpha158 | 30日收益线性回归的R² | `ts_rsquare(close, 30)` |
| `a158_RSQR60` | alpha158 | 60日收益线性回归的R² | `ts_rsquare(close, 60)` |
| `a158_RESI5` | alpha158 | 5日收益回归残差/收盘 | `ts_resi(close, 5)/close` |
| `a158_RESI10` | alpha158 | 10日收益回归残差/收盘 | `ts_resi(close, 10)/close` |
| `a158_RESI20` | alpha158 | 20日收益回归残差/收盘 | `ts_resi(close, 20)/close` |
| `a158_RESI30` | alpha158 | 30日收益回归残差/收盘 | `ts_resi(close, 30)/close` |
| `a158_RESI60` | alpha158 | 60日收益回归残差/收盘 | `ts_resi(close, 60)/close` |
| `a158_MAX5` | alpha158 | 5日最大单日收益 | `ts_max(high, 5)/close` |
| `a158_MAX10` | alpha158 | 10日最大单日收益 | `ts_max(high, 10)/close` |
| `a158_MAX20` | alpha158 | 20日最大单日收益 | `ts_max(high, 20)/close` |
| `a158_MAX30` | alpha158 | 30日最大单日收益 | `ts_max(high, 30)/close` |
| `a158_MAX60` | alpha158 | 60日最大单日收益 | `ts_max(high, 60)/close` |
| `a158_MIN5` | alpha158 | 5日最小单日收益 | `ts_min(low, 5)/close` |
| `a158_MIN10` | alpha158 | 10日最小单日收益 | `ts_min(low, 10)/close` |
| `a158_MIN20` | alpha158 | 20日最小单日收益 | `ts_min(low, 20)/close` |
| `a158_MIN30` | alpha158 | 30日最小单日收益 | `ts_min(low, 30)/close` |
| `a158_MIN60` | alpha158 | 60日最小单日收益 | `ts_min(low, 60)/close` |
| `a158_QTLU5` | alpha158 | 5日收益80%分位 | `ts_quantile(close, 5, 0.8)/close` |
| `a158_QTLU10` | alpha158 | 10日收益80%分位 | `ts_quantile(close, 10, 0.8)/close` |
| `a158_QTLU20` | alpha158 | 20日收益80%分位 | `ts_quantile(close, 20, 0.8)/close` |
| `a158_QTLU30` | alpha158 | 30日收益80%分位 | `ts_quantile(close, 30, 0.8)/close` |
| `a158_QTLU60` | alpha158 | 60日收益80%分位 | `ts_quantile(close, 60, 0.8)/close` |
| `a158_QTLD5` | alpha158 | 5日收益20%分位 | `ts_quantile(close, 5, 0.2)/close` |
| `a158_QTLD10` | alpha158 | 10日收益20%分位 | `ts_quantile(close, 10, 0.2)/close` |
| `a158_QTLD20` | alpha158 | 20日收益20%分位 | `ts_quantile(close, 20, 0.2)/close` |
| `a158_QTLD30` | alpha158 | 30日收益20%分位 | `ts_quantile(close, 30, 0.2)/close` |
| `a158_QTLD60` | alpha158 | 60日收益20%分位 | `ts_quantile(close, 60, 0.2)/close` |
| `a158_RANK5` | alpha158 | 当前收益在5日内的时序分位 | `ts_rank(close, 5)` |
| `a158_RANK10` | alpha158 | 当前收益在10日内的时序分位 | `ts_rank(close, 10)` |
| `a158_RANK20` | alpha158 | 当前收益在20日内的时序分位 | `ts_rank(close, 20)` |
| `a158_RANK30` | alpha158 | 当前收益在30日内的时序分位 | `ts_rank(close, 30)` |
| `a158_RANK60` | alpha158 | 当前收益在60日内的时序分位 | `ts_rank(close, 60)` |
| `a158_RSV5` | alpha158 | 收盘价在5日区间中的位置 | `(close-ts_min(low, 5))/(ts_max(high, 5)-ts_min(low, 5)+1e-12)` |
| `a158_RSV10` | alpha158 | 收盘价在10日区间中的位置 | `(close-ts_min(low, 10))/(ts_max(high, 10)-ts_min(low, 10)+1e-12)` |
| `a158_RSV20` | alpha158 | 收盘价在20日区间中的位置 | `(close-ts_min(low, 20))/(ts_max(high, 20)-ts_min(low, 20)+1e-12)` |
| `a158_RSV30` | alpha158 | 收盘价在30日区间中的位置 | `(close-ts_min(low, 30))/(ts_max(high, 30)-ts_min(low, 30)+1e-12)` |
| `a158_RSV60` | alpha158 | 收盘价在60日区间中的位置 | `(close-ts_min(low, 60))/(ts_max(high, 60)-ts_min(low, 60)+1e-12)` |
| `a158_IMAX5` | alpha158 | 5日最高点距今天数 | `ts_idxmax(high, 5)/5` |
| `a158_IMAX10` | alpha158 | 10日最高点距今天数 | `ts_idxmax(high, 10)/10` |
| `a158_IMAX20` | alpha158 | 20日最高点距今天数 | `ts_idxmax(high, 20)/20` |
| `a158_IMAX30` | alpha158 | 30日最高点距今天数 | `ts_idxmax(high, 30)/30` |
| `a158_IMAX60` | alpha158 | 60日最高点距今天数 | `ts_idxmax(high, 60)/60` |
| `a158_IMIN5` | alpha158 | 5日最低点距今天数 | `ts_idxmin(low, 5)/5` |
| `a158_IMIN10` | alpha158 | 10日最低点距今天数 | `ts_idxmin(low, 10)/10` |
| `a158_IMIN20` | alpha158 | 20日最低点距今天数 | `ts_idxmin(low, 20)/20` |
| `a158_IMIN30` | alpha158 | 30日最低点距今天数 | `ts_idxmin(low, 30)/30` |
| `a158_IMIN60` | alpha158 | 60日最低点距今天数 | `ts_idxmin(low, 60)/60` |
| `a158_IMXD5` | alpha158 | 最高点与最低点的天数差 | `(ts_idxmax(high, 5)-ts_idxmin(low, 5))/5` |
| `a158_IMXD10` | alpha158 | 最高点与最低点的天数差 | `(ts_idxmax(high, 10)-ts_idxmin(low, 10))/10` |
| `a158_IMXD20` | alpha158 | 最高点与最低点的天数差 | `(ts_idxmax(high, 20)-ts_idxmin(low, 20))/20` |
| `a158_IMXD30` | alpha158 | 最高点与最低点的天数差 | `(ts_idxmax(high, 30)-ts_idxmin(low, 30))/30` |
| `a158_IMXD60` | alpha158 | 最高点与最低点的天数差 | `(ts_idxmax(high, 60)-ts_idxmin(low, 60))/60` |
| `a158_CORR5` | alpha158 | 收盘价与log成交量的5日相关 | `ts_corr(close, log(volume+1), 5)` |
| `a158_CORR10` | alpha158 | 收盘价与log成交量的10日相关 | `ts_corr(close, log(volume+1), 10)` |
| `a158_CORR20` | alpha158 | 收盘价与log成交量的20日相关 | `ts_corr(close, log(volume+1), 20)` |
| `a158_CORR30` | alpha158 | 收盘价与log成交量的30日相关 | `ts_corr(close, log(volume+1), 30)` |
| `a158_CORR60` | alpha158 | 收盘价与log成交量的60日相关 | `ts_corr(close, log(volume+1), 60)` |
| `a158_CORD5` | alpha158 | 收益与log成交量变化的5日相关 | `ts_corr(close/delay(close,1), log(volume/delay(volume, 1)+1), 5)` |
| `a158_CORD10` | alpha158 | 收益与log成交量变化的10日相关 | `ts_corr(close/delay(close,1), log(volume/delay(volume, 1)+1), 10)` |
| `a158_CORD20` | alpha158 | 收益与log成交量变化的20日相关 | `ts_corr(close/delay(close,1), log(volume/delay(volume, 1)+1), 20)` |
| `a158_CORD30` | alpha158 | 收益与log成交量变化的30日相关 | `ts_corr(close/delay(close,1), log(volume/delay(volume, 1)+1), 30)` |
| `a158_CORD60` | alpha158 | 收益与log成交量变化的60日相关 | `ts_corr(close/delay(close,1), log(volume/delay(volume, 1)+1), 60)` |
| `a158_CNTP5` | alpha158 | 5日上涨天数占比 | `ts_mean(close>delay(close, 1), 5)` |
| `a158_CNTP10` | alpha158 | 10日上涨天数占比 | `ts_mean(close>delay(close, 1), 10)` |
| `a158_CNTP20` | alpha158 | 20日上涨天数占比 | `ts_mean(close>delay(close, 1), 20)` |
| `a158_CNTP30` | alpha158 | 30日上涨天数占比 | `ts_mean(close>delay(close, 1), 30)` |
| `a158_CNTP60` | alpha158 | 60日上涨天数占比 | `ts_mean(close>delay(close, 1), 60)` |
| `a158_CNTN5` | alpha158 | 5日下跌天数占比 | `ts_mean(close<delay(close, 1), 5)` |
| `a158_CNTN10` | alpha158 | 10日下跌天数占比 | `ts_mean(close<delay(close, 1), 10)` |
| `a158_CNTN20` | alpha158 | 20日下跌天数占比 | `ts_mean(close<delay(close, 1), 20)` |
| `a158_CNTN30` | alpha158 | 30日下跌天数占比 | `ts_mean(close<delay(close, 1), 30)` |
| `a158_CNTN60` | alpha158 | 60日下跌天数占比 | `ts_mean(close<delay(close, 1), 60)` |
| `a158_CNTD5` | alpha158 | 5日涨跌天数差占比 | `ts_mean(close>delay(close, 1), 5)-ts_mean(close<delay(close, 1), 5)` |
| `a158_CNTD10` | alpha158 | 10日涨跌天数差占比 | `ts_mean(close>delay(close, 1), 10)-ts_mean(close<delay(close, 1), 10)` |
| `a158_CNTD20` | alpha158 | 20日涨跌天数差占比 | `ts_mean(close>delay(close, 1), 20)-ts_mean(close<delay(close, 1), 20)` |
| `a158_CNTD30` | alpha158 | 30日涨跌天数差占比 | `ts_mean(close>delay(close, 1), 30)-ts_mean(close<delay(close, 1), 30)` |
| `a158_CNTD60` | alpha158 | 60日涨跌天数差占比 | `ts_mean(close>delay(close, 1), 60)-ts_mean(close<delay(close, 1), 60)` |
| `a158_SUMP5` | alpha158 | 5日上涨收益之和 | `ts_sum(max(close-delay(close, 1), 0), 5)/(ts_sum(abs(close-delay(close, 1)), 5)+1e-12)` |
| `a158_SUMP10` | alpha158 | 10日上涨收益之和 | `ts_sum(max(close-delay(close, 1), 0), 10)/(ts_sum(abs(close-delay(close, 1)), 10)+1e-12)` |
| `a158_SUMP20` | alpha158 | 20日上涨收益之和 | `ts_sum(max(close-delay(close, 1), 0), 20)/(ts_sum(abs(close-delay(close, 1)), 20)+1e-12)` |
| `a158_SUMP30` | alpha158 | 30日上涨收益之和 | `ts_sum(max(close-delay(close, 1), 0), 30)/(ts_sum(abs(close-delay(close, 1)), 30)+1e-12)` |
| `a158_SUMP60` | alpha158 | 60日上涨收益之和 | `ts_sum(max(close-delay(close, 1), 0), 60)/(ts_sum(abs(close-delay(close, 1)), 60)+1e-12)` |
| `a158_SUMN5` | alpha158 | 5日下跌收益之和 | `ts_sum(max(delay(close, 1)-close, 0), 5)/(ts_sum(abs(close-delay(close, 1)), 5)+1e-12)` |
| `a158_SUMN10` | alpha158 | 10日下跌收益之和 | `ts_sum(max(delay(close, 1)-close, 0), 10)/(ts_sum(abs(close-delay(close, 1)), 10)+1e-12)` |
| `a158_SUMN20` | alpha158 | 20日下跌收益之和 | `ts_sum(max(delay(close, 1)-close, 0), 20)/(ts_sum(abs(close-delay(close, 1)), 20)+1e-12)` |
| `a158_SUMN30` | alpha158 | 30日下跌收益之和 | `ts_sum(max(delay(close, 1)-close, 0), 30)/(ts_sum(abs(close-delay(close, 1)), 30)+1e-12)` |
| `a158_SUMN60` | alpha158 | 60日下跌收益之和 | `ts_sum(max(delay(close, 1)-close, 0), 60)/(ts_sum(abs(close-delay(close, 1)), 60)+1e-12)` |
| `a158_SUMD5` | alpha158 | 5日涨跌收益和之差 | `(ts_sum(max(close-delay(close, 1), 0), 5)-ts_sum(max(delay(close, 1)-close, 0), 5))/(ts_sum(abs(close-delay(close, 1)), 5)+1e-12)` |
| `a158_SUMD10` | alpha158 | 10日涨跌收益和之差 | `(ts_sum(max(close-delay(close, 1), 0), 10)-ts_sum(max(delay(close, 1)-close, 0), 10))/(ts_sum(abs(close-delay(close, 1)), 10)+1e-12)` |
| `a158_SUMD20` | alpha158 | 20日涨跌收益和之差 | `(ts_sum(max(close-delay(close, 1), 0), 20)-ts_sum(max(delay(close, 1)-close, 0), 20))/(ts_sum(abs(close-delay(close, 1)), 20)+1e-12)` |
| `a158_SUMD30` | alpha158 | 30日涨跌收益和之差 | `(ts_sum(max(close-delay(close, 1), 0), 30)-ts_sum(max(delay(close, 1)-close, 0), 30))/(ts_sum(abs(close-delay(close, 1)), 30)+1e-12)` |
| `a158_SUMD60` | alpha158 | 60日涨跌收益和之差 | `(ts_sum(max(close-delay(close, 1), 0), 60)-ts_sum(max(delay(close, 1)-close, 0), 60))/(ts_sum(abs(close-delay(close, 1)), 60)+1e-12)` |
| `a158_VMA5` | alpha158 | 成交量/5日均量 | `ts_mean(volume, 5)/(volume+1e-12)` |
| `a158_VMA10` | alpha158 | 成交量/10日均量 | `ts_mean(volume, 10)/(volume+1e-12)` |
| `a158_VMA20` | alpha158 | 成交量/20日均量 | `ts_mean(volume, 20)/(volume+1e-12)` |
| `a158_VMA30` | alpha158 | 成交量/30日均量 | `ts_mean(volume, 30)/(volume+1e-12)` |
| `a158_VMA60` | alpha158 | 成交量/60日均量 | `ts_mean(volume, 60)/(volume+1e-12)` |
| `a158_VSTD5` | alpha158 | 成交量5日波动 | `ts_std(volume, 5)/(volume+1e-12)` |
| `a158_VSTD10` | alpha158 | 成交量10日波动 | `ts_std(volume, 10)/(volume+1e-12)` |
| `a158_VSTD20` | alpha158 | 成交量20日波动 | `ts_std(volume, 20)/(volume+1e-12)` |
| `a158_VSTD30` | alpha158 | 成交量30日波动 | `ts_std(volume, 30)/(volume+1e-12)` |
| `a158_VSTD60` | alpha158 | 成交量60日波动 | `ts_std(volume, 60)/(volume+1e-12)` |
| `a158_WVMA5` | alpha158 | 成交量加权收益波动（5日） | `ts_std(abs(close/delay(close, 1)-1)*volume, 5)/(ts_mean(abs(close/delay(close, 1)-1)*volume, 5)+1e-12)` |
| `a158_WVMA10` | alpha158 | 成交量加权收益波动（10日） | `ts_std(abs(close/delay(close, 1)-1)*volume, 10)/(ts_mean(abs(close/delay(close, 1)-1)*volume, 10)+1e-12)` |
| `a158_WVMA20` | alpha158 | 成交量加权收益波动（20日） | `ts_std(abs(close/delay(close, 1)-1)*volume, 20)/(ts_mean(abs(close/delay(close, 1)-1)*volume, 20)+1e-12)` |
| `a158_WVMA30` | alpha158 | 成交量加权收益波动（30日） | `ts_std(abs(close/delay(close, 1)-1)*volume, 30)/(ts_mean(abs(close/delay(close, 1)-1)*volume, 30)+1e-12)` |
| `a158_WVMA60` | alpha158 | 成交量加权收益波动（60日） | `ts_std(abs(close/delay(close, 1)-1)*volume, 60)/(ts_mean(abs(close/delay(close, 1)-1)*volume, 60)+1e-12)` |
| `a158_VSUMP5` | alpha158 | 5日放量上涨收益和 | `ts_sum(max(volume-delay(volume, 1), 0), 5)/(ts_sum(abs(volume-delay(volume, 1)), 5)+1e-12)` |
| `a158_VSUMP10` | alpha158 | 10日放量上涨收益和 | `ts_sum(max(volume-delay(volume, 1), 0), 10)/(ts_sum(abs(volume-delay(volume, 1)), 10)+1e-12)` |
| `a158_VSUMP20` | alpha158 | 20日放量上涨收益和 | `ts_sum(max(volume-delay(volume, 1), 0), 20)/(ts_sum(abs(volume-delay(volume, 1)), 20)+1e-12)` |
| `a158_VSUMP30` | alpha158 | 30日放量上涨收益和 | `ts_sum(max(volume-delay(volume, 1), 0), 30)/(ts_sum(abs(volume-delay(volume, 1)), 30)+1e-12)` |
| `a158_VSUMP60` | alpha158 | 60日放量上涨收益和 | `ts_sum(max(volume-delay(volume, 1), 0), 60)/(ts_sum(abs(volume-delay(volume, 1)), 60)+1e-12)` |
| `a158_VSUMN5` | alpha158 | 5日放量下跌收益和 | `ts_sum(max(delay(volume, 1)-volume, 0), 5)/(ts_sum(abs(volume-delay(volume, 1)), 5)+1e-12)` |
| `a158_VSUMN10` | alpha158 | 10日放量下跌收益和 | `ts_sum(max(delay(volume, 1)-volume, 0), 10)/(ts_sum(abs(volume-delay(volume, 1)), 10)+1e-12)` |
| `a158_VSUMN20` | alpha158 | 20日放量下跌收益和 | `ts_sum(max(delay(volume, 1)-volume, 0), 20)/(ts_sum(abs(volume-delay(volume, 1)), 20)+1e-12)` |
| `a158_VSUMN30` | alpha158 | 30日放量下跌收益和 | `ts_sum(max(delay(volume, 1)-volume, 0), 30)/(ts_sum(abs(volume-delay(volume, 1)), 30)+1e-12)` |
| `a158_VSUMN60` | alpha158 | 60日放量下跌收益和 | `ts_sum(max(delay(volume, 1)-volume, 0), 60)/(ts_sum(abs(volume-delay(volume, 1)), 60)+1e-12)` |
| `a158_VSUMD5` | alpha158 | 5日放量涨跌收益差 | `(ts_sum(max(volume-delay(volume, 1), 0), 5)-ts_sum(max(delay(volume, 1)-volume, 0), 5))/(ts_sum(abs(volume-delay(volume, 1)), 5)+1e-12)` |
| `a158_VSUMD10` | alpha158 | 10日放量涨跌收益差 | `(ts_sum(max(volume-delay(volume, 1), 0), 10)-ts_sum(max(delay(volume, 1)-volume, 0), 10))/(ts_sum(abs(volume-delay(volume, 1)), 10)+1e-12)` |
| `a158_VSUMD20` | alpha158 | 20日放量涨跌收益差 | `(ts_sum(max(volume-delay(volume, 1), 0), 20)-ts_sum(max(delay(volume, 1)-volume, 0), 20))/(ts_sum(abs(volume-delay(volume, 1)), 20)+1e-12)` |
| `a158_VSUMD30` | alpha158 | 30日放量涨跌收益差 | `(ts_sum(max(volume-delay(volume, 1), 0), 30)-ts_sum(max(delay(volume, 1)-volume, 0), 30))/(ts_sum(abs(volume-delay(volume, 1)), 30)+1e-12)` |
| `a158_VSUMD60` | alpha158 | 60日放量涨跌收益差 | `(ts_sum(max(volume-delay(volume, 1), 0), 60)-ts_sum(max(delay(volume, 1)-volume, 0), 60))/(ts_sum(abs(volume-delay(volume, 1)), 60)+1e-12)` |
