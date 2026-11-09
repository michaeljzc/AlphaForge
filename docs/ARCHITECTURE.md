# 架构说明

## 1. 分层与职责

```text
configs/default.yaml
        │
src/alphaforge/
├── data/          原始数据 -> SQLite -> 稠密面板 -> Qlib 二进制
├── expr/          表达式字符串 -> AST -> (T,N) 因子矩阵
├── preprocess.py  去极值 -> 标准化 -> 行业/市值中性化
├── evaluate/      IC / 分层 / 换手 / 闸门 / 相关性
├── portfolio/     因子合成 -> Top-N -> 目标权重
├── backtest/      目标权重 -> A 股约束撮合 -> 净值/交易/指标
├── mining/        GP 搜索 -> 候选表达式 -> 注册库
├── event/         T0 检测 -> 标签 -> 事件数据集 -> 事件评估/审计
├── report/        Plotly + Jinja2 -> 离线 HTML
└── pipeline/      端到端编排
```

所有上层模块只依赖 **Panel**（`T×N` 数组 + 掩码）与 **表达式**，不直接读数据库。这样训练、评估、回测、事件四条链路使用完全一致的数据口径。

## 2. 数据流

### 2.1 摄取（`data/ingest.py`）

Tushare API → 单位归一 → SQLite。单位约定：

| 字段 | 单位 |
|---|---|
| price | CNY |
| volume | 股 |
| amount / market cap / money flow | CNY |
| fina_indicator | Tushare 原始单位（%、倍） |

数据集：`daily`、`adj_factor`、`daily_basic`、`moneyflow`、`stk_limit`、`fina`、`index_member`、`index_daily`、`calendar`、`securities`。

- 断点续跑：`ingest_state(dataset, code, end_date, status)`；
- 限频：固定间隔 + 指数退避 + 乘法惩罚；
- 无权限接口：标记 `disabled` 并继续，不阻断整体任务；
- 增量：重新运行会按 `expected_end` 判断是否跳过。

### 2.2 面板（`data/panel.py`）

输入：交易日历、股票池（指数历史成分并集）、各表。

输出：`Panel(dates, symbols, data, masks, industry_id)`。

- 价格：`close = raw_close × adj_factor / last_adj_factor`（前复权）；
- 收益：`ret = close / delay(close,1) - 1`（复权后收益，除权日安全）；
- 可交易性：
  - `universe`：指数成分（as-of）+ 上市天数 + 价格/成交额 + 非停牌 + 非 ST 代理；
  - `tradable`：`universe` 且非涨停；
  - `sellable`：`universe` 且非跌停。
- PIT 财务：对每只股票按 `ann_date` 排序，维护“当前已知各报告期最新修订”，再取最新报告期；对每个日历日做 as-of 展开。绝不使用 `end_date` 对齐。
- 缓存：`data/cache/panel_main_START_END.npz`，DB mtime 变化即失效。

面板里同时保留 `close_raw/open_raw/...`、`up_limit/down_limit`，用于撮合与涨跌停判断；因子默认使用复权价格。

### 2.2b Qlib 原生链路（`qlib_native.py`）

`alphaforge qlib native` 的调用链：

```text
Panel（AlphaForge 计算 Alpha158 因子值）
  -> NativeDataset（DatasetH 兼容：MultiIndex + feature/label 分组）
  -> qlib.contrib.model.gbdt.LGBModel.fit / predict
  -> qlib.workflow.R（MLflow 记录器）
  -> qlib.contrib.strategy.TopkDropoutStrategy
  -> qlib.backtest.backtest + SimulatorExecutor + SH000300 benchmark
  -> 同一预测再喂给 AlphaForge 的 A 股约束回测
```

Qlib 自带的 `Alpha158` handler 在千只股票规模下逐股计算过慢，因此因子值由 AlphaForge
的向量化引擎计算，但**模型/记录器/策略/执行器全部是 Qlib 的代码**。

口径提醒：Qlib 原生回测使用 `deal_price=close`（Qlib 默认），AlphaForge 撮合使用
t+1 开盘；两套结果用于对照规则差异，不能直接比较绝对收益。

### 2.3 Qlib 导出（`data/qlib_export.py`）

```text
data/qlib_cn/
├── calendars/day.txt
├── instruments/all.txt
└── features/SH600000/close.day.bin
```

- 二进制格式：`float32` 数组，首元素为该股票在日历中的起始索引，其后为逐日值；
- 导出字段：`open/high/low/close/vwap/volume/amount/factor`；
- 由于面板已是前复权，`factor` 导出为 1.0；
- `verify_parity()` 用 `D.features(['SH600000'], ['$close'])` 与本地面板逐点比对。

### 2.4 表达式引擎（`expr/`）

- `parser.py`：递归下降；支持 `$` 前缀（Qlib 风格）、比较运算、函数调用；
- `ops.py`：算子注册表，统一签名 `(ctx, *args)`，返回`(T,N)` 或标量；
- `engine.py`：带缓存求值；`mask` 只作用于截面算子（时序算子必须看完整历史）；
- `library.py`：内置因子 + Alpha158 翻译器 + WorldQuant 101 注册；
- `wq101.py` / `wq101_formulas.json`：从 `101factors.pdf` 提取的 101 条公式与转译器。

缓存按表达式字符串键控，超过显存预算时淘汰最旧一半；字段不进入缓存（面板本身持有）。

### 2.5 组合与回测

`combine.py`：

1. 每个因子：`raw -> preprocess -> sign × weight`；
2. sign/weight 只在训练期估计（IC 定向），避免样本外偷看；
3. 合成后再做一次中性化；
4. `build_targets` 在调仓日按得分选 Top-N，保留排名缓冲内的老持仓，行业内数量上限。

`backtest/engine.py`：

- 信号日 `t` → 执行日 `t+1` 开盘；
- 先卖后买；卖不出（跌停/停牌）进入 `deferred_sell`，买不进（涨停/停牌）进入 `deferred_buy`，后续每日只重试这些被阻塞的单子；
- 费用：佣金（最低 5 元）+ 印花税（卖）+ 滑点；
- 每日收盘估值；基准来自 `index_daily`。

### 2.5b Web 控制台（`web/app.py`）

FastAPI 只读 `reports/artifacts/` 与 `market.db`：

```text
GET  /api/overview /api/backtest /api/events /api/gp /api/qlib
GET  /api/factors /api/factors/{name}
POST /api/factors/evaluate        # 在线表达式评估
GET  /api/sources                 # 配置 + 缓存的探活结果
POST /api/sources/{id}/probe      # 实时探活（Tushare / iFinD / DataYes）
GET  /api/data/summary            # 数据湖行数
```

前端为 `web/static/` 下的原生 JS + ECharts（离线可用），通过 hash 路由切换视图。
服务默认绑定 `127.0.0.1:8787`，不对外网开放。

### 2.5c 多数据源（`data/sources.py`）

- 凭据：环境变量 → `config/credentials.json` → `~/Quant/qQuant/quantlab/config/credentials.json`；
- Tushare：主库；iFinD：`cmd_history_quotation`（none/qfq/hfq）；DataYes：`getMktEqud`
  （含 `accumAdjFactor`、`turnoverRate`、`PE/PB`、市值）；
- 探活与预览默认不写库；`--write` 才写入与 Panel/Qlib 共用的 schema。

### 2.6 事件层

- 检测：向量化条件 + 按股票冷却期去重；
- 标签：T0 收盘为基准，取 T0+1..T0+60 的最高/最低/期末；
- 特征：统一取 `t0_idx - 1` 的截面值；
- 事件截面：按 20 交易日分桶，桶内样本 ≥5 才计算 RankIC；
- 审计：把面板截断到 T0−1，重算特征并比对。

## 3. 扩展点

| 想做什么 | 改哪里 |
|---|---|
| 新增数据源 | 实现 `data/ingest.py` 的 `_ingest_*` 或新增 adapter，写入同一 schema |
| 新增因子 | `expr/library.py` 里 `register(name, expr, category, direction)` |
| 新增算子 | `expr/ops.py` 注册；自动被 parser/GP 使用 |
| 新增评估指标 | `evaluate/core.py`，并在 `FactorReport`/`gate` 中暴露 |
| 新增组合优化器 | `portfolio/combine.py` 的 `build_targets` 替换为凸优化/风险模型 |
| 接入 RL/AlphaGen | `mining/` 新增搜索器，复用 `FitnessEvaluator` 与注册库 |
| Web 控制台 | `report/` 输出之外，新增 FastAPI 路由读 `reports/artifacts` |

## 4. 性能基线（本机 M 系列）

| 操作 | 规模 | 时间 |
|---|---|---|
| 全量摄取 | 1,267 只 × 2019–2026 | 约 16 分钟（7,796 次 API） |
| 面板构建 | 1,897 × 1,267 | 约 26 秒（缓存后 0.1 秒） |
| Qlib 导出 | 1,267 只 × 8 字段 | 约 1.5 秒（增量） |
| 内置因子评估 | 30 个 × 4 期限 | 约 27 秒 |
| 组合回测 | 683 个交易日 | 约 7 秒 |
| T0 事件构建 | 1 万事件 + 36 特征 | 约 7 秒 |
| GP（quick） | 80×5，357 次评估 | 约 30 秒 |
| GP（full） | 200×15，约 3,000 次评估 | 约 4–6 分钟 |
| Qlib 原生 LGBM | 150 只 × 158 特征 + Qlib 回测 | 约 82 秒 |
| WQ101 批量评估 | 101 因子 × 4 期限 + 中性化 | 约 110 秒 |
