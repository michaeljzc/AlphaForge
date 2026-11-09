# 数据源：Tushare / iFinD / DataYes

平台默认以 **Tushare Pro** 构建 `data/market.db`，同时提供同花顺 iFinD 与通联 DataYes
的探活、预览与可选落库能力。三套数据源共用同一套 SQLite schema 与 Panel 口径。

## 1. 凭据

优先级（后者覆盖前者）：

1. 环境变量：`TUSHARE_TOKEN`、`IFIND_REFRESH_TOKEN` / `IFIND_ACCESS_TOKEN`、`DATAYES_TOKEN`
2. `config/credentials.json`
3. `~/Quant/qQuant/quantlab/config/credentials.json`（本机已有则自动复用）

Web 控制台的「数据源」页只展示掩码后的 token，不会回传明文。

## 2. 状态与探活

```bash
alphaforge sources status
alphaforge sources status --probe     # 实际发一次轻量请求
alphaforge sources probe --source ifind
alphaforge sources probe --source datayes
```

探活结果（延迟/消息）缓存 120 秒；Web 端的「测试连接」按钮走同一套代码。

| 源 | 能力 | 说明 |
|---|---|---|
| Tushare | daily / adj_factor / daily_basic / moneyflow / stk_limit / fina(PIT) | 主库，Panel 默认来源 |
| iFinD | daily / realtime / limit_pool / consensus | `cmd_history_quotation`，支持 `none/qfq/hfq` |
| DataYes | daily / accumAdjFactor / valuation / index / concepts | `getMktEqud`，自带累计复权因子 |

## 3. 预览与落库

```bash
# 只读预览（默认，不写库）
alphaforge sources fetch --source datayes --codes 000001,600000 \
  --start 2024-01-01 --end 2024-01-31

alphaforge sources fetch --source ifind --codes 000001 \
  --start 2024-01-01 --end 2024-01-31 --adjust qfq

# 确认字段/单位后写入 market.db
alphaforge sources fetch --source datayes --codes ... --write
```

对应 Python：

```python
from alphaforge.data.sources import fetch_datayes_daily, fetch_ifind_daily

rows = fetch_datayes_daily(["000001"], "2024-01-01", "2024-01-31")
rows = fetch_ifind_daily(["000001"], "2024-01-01", "2024-01-31", adjust="qfq")
```

### 字段映射

**DataYes `getMktEqud`**

| 源字段 | 平台字段 |
|---|---|
| `closePrice/openPrice/highestPrice/lowestPrice/preClosePrice` | `daily.close/open/high/low/pre_close` |
| `turnoverVol` | `daily.volume`（股） |
| `turnoverValue` | `daily.amount`（元） |
| `accumAdjFactor` | `adj_factor.adj_factor` |
| `turnoverRate` | `daily_basic.turnover_f` |
| `PE1/PE`、`PB` | `pe_ttm`、`pb` |
| `marketValue`、`negMarketValue` | `total_mv`、`circ_mv` |

**iFinD `cmd_history_quotation`**

`open/high/low/close/preClose/volume/amount/turnoverRatio`；
`CPS`：`1=不复权`、`2=前复权`、`3=后复权`。当前落库把 `adjust=none` 写 `adj_factor=1`；
`qfq` 写前复权价并同样置 1——**两套口径不要混用**。

## 4. 与 Panel / Qlib 的关系

- Panel 读取 `market.db` 的 `daily/adj_factor/daily_basic/...`，因此 DataYes 落库后
  重新 `alphaforge build --no-cache` 即可切换数据源；
- 不建议把 iFinD/DataYes 的日线直接混进已有的 Tushare 全量库；若要切换，建议
  使用独立的 DB 文件（`configs/default.yaml` 的 `paths.market_db`）重建面板；
- Qlib 导出只依赖 Panel，与数据源无关；切换后重跑 `alphaforge build --export-qlib`。

## 5. 注意事项

- iFinD `changeRatio` 返回的是**百分比数值**（例如 -0.978 表示 -0.978%），平台落库不直接使用该字段；
- DataYes 的 `accumAdjFactor` 与 Tushare `adj_factor` 数值量纲不同，但 Panel 只用
  “当期/末期”的比值，因此口径一致；
- 财务 PIT 目前主库来自 Tushare `fina_indicator.ann_date`；iFinD/DataYes 财务字段可后续
  按同样 schema 扩展；
- 数据源权限、限频、字段可用性以你的账号为准。
