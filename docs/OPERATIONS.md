# 运维手册

## 1. 安装

推荐 Python 3.12（Qlib 0.9.7 的 macOS universal2 wheel 支持 cp312；3.13 无对应 wheel）。

```bash
cd /Users/crsec_ai_lab/Quant/qlib
python3.12 -m venv .venv
.venv/bin/pip install pyqlib==0.9.7 lightgbm scipy scikit-learn pyarrow \
    matplotlib plotly jinja2 pyyaml tqdm tushare
.venv/bin/pip install -e . --no-deps
.venv/bin/alphaforge --help
```

如果 PyPI 依赖解析卡住，可单独下载 wheel：`pip install --no-deps <wheel>`。

## 2. Token

优先级：

1. `export TUSHARE_TOKEN=...`
2. `config/credentials.json` → `{"TUSHARE_TOKEN": "..."}`
3. 本机既有 `~/Quant/qQuant/quantlab/config/credentials.json`

验证：

```bash
alphaforge ingest --codes 000001 --start 2024-01-01 --end 2024-01-31
```

## 3. 数据摄取

```bash
# 全量（首次约 15 分钟）
alphaforge ingest --start 2019-01-01 --end 2026-10-30

# 指定指数与区间
alphaforge ingest --indices 000300.SH,000905.SH --start 2022-01-01 --end 2024-12-31

# 只补某个数据集（跳过其它）
alphaforge ingest --skip daily,adj_factor,daily_basic,moneyflow,stk_limit
```

- 断点续跑：读取 `ingest_state`，覆盖到目标日则跳过；
- 每分钟限频：`--interval 0.13`（默认），被限流会自动退避；
- 无权限接口：打印 warning 并跳过，不会中断；
- 退出码非 0 时看 `data/ingest_run.log`（若用重定向）。

## 4. 面板与 Qlib

```bash
alphaforge build --export-qlib --verify
```

- 面板缓存：`data/cache/panel_main_*.npz`；DB 修改后自动重建；
- Qlib 数据：`data/qlib_cn/`；
- `--force` 强制重建 Qlib（默认按签名增量跳过）。

手工校验：

```bash
alphaforge qlib verify
```

## 4b. Qlib 原生模型与回测

```bash
# 150 只样本、Alpha158 158 特征、LGBM；约 80–90 秒
alphaforge qlib native --symbols 150 --topk 50

# 只训练不跑 Qlib 回测
alphaforge qlib native --symbols 100 --no-backtest
```

产物：`reports/artifacts/qlib_native.json`（IC、Qlib 回测、AlphaForge 回测、净值曲线）。
该命令会启动 Qlib 的 MLflow 记录器（代码内设置 `MLFLOW_ALLOW_FILE_STORE=true`）。

## 4c. Web 控制台

```bash
alphaforge web --port 8787
# http://127.0.0.1:8787
```

- 只读本地 `reports/artifacts` 与 `market.db`，绑定 `127.0.0.1`；
- 支持总览 / 因子库（含在线表达式评估）/ 回测 / T0 事件 / GP / Qlib / 数据源；
- 如果端口被占用：`lsof -nP -iTCP:8787 -sTCP:LISTEN`，结束旧进程后重启。

## 4d. 数据源（iFinD / DataYes）

```bash
alphaforge sources status --probe
alphaforge sources probe --source ifind
alphaforge sources fetch --source datayes --codes 000001 --start 2024-01-01 --end 2024-01-31
alphaforge sources fetch --source ifind  --codes 000001 --start 2024-01-01 --end 2024-01-31 --adjust qfq
```

默认只读预览；`--write` 才写入 `market.db`。详见 `docs/DATA_SOURCES.md`。

## 5. 因子研究

```bash
alphaforge factors list --category launch
alphaforge factors ops --kind ts
alphaforge factors eval "ts_std(ret,20)/ts_std(ret,60)"
alphaforge factors eval a158_KMID --start 2021-01-01 --json > /tmp/kmid.json
alphaforge factors list --category wq101
alphaforge factors batch --category wq101        # 101 个批量评估，合并 Web 因子库
```

## 6. 回测

```bash
alphaforge backtest --start 2024-01-02 --end 2026-10-30 \
  --train-start 2021-01-01 --train-end 2023-12-31 \
  --rebalance 21 --top-n 50 --method ic_weighted
```

输出 `reports/artifacts/backtest_cli.json`，含净值、交易与指标。

## 7. 事件研究

```bash
alphaforge event --audit
```

生成 `data/events/events.parquet` 与摘要，打印事件截面 IC、事件组合指标、精度与审计结果。

## 8. 端到端演示与报告

```bash
alphaforge demo                 # 快速 GP（80×5）
alphaforge demo --full          # 完整 GP（200×15）
alphaforge demo --no-mine       # 不跑 GP
```

报告：`reports/alphaforge_report.html`（离线自包含，可直接双击打开）。

## 9. 常见问题

| 现象 | 原因/处理 |
|---|---|
| `ModuleNotFoundError: qlib` | 用了系统 Python；改用 `.venv/bin/python` |
| `未找到 Tushare token` | 配 token；或 `--codes` 测试时也会校验 |
| `日期 xxx 不在面板日历内` | 传入周末/节假日；回测已自动取最近交易日 |
| Qlib `D.features` 为空 | 未导出或 instrument 名不对；运行 `alphaforge build --export-qlib` |
| 面板构建很慢 | 首次 pivote 约 26 秒；确认没有频繁重建缓存 |
| 报告图表空白 | 浏览器禁用了本地脚本；用 Chrome/Safari 打开，或检查 5MB 文件是否完整 |
| pip 安装卡住 | 直接下载 wheel `pip install --no-deps`；本机 `pip` 缓存目录不可写会退化 |

## 10. 磁盘与清理

| 目录 | 大小（参考） |
|---|---|
| `data/market.db` | ~1.0 GB |
| `data/qlib_cn/` | ~300 MB（1 万个小文件） |
| `data/cache/*.npz` | ~250 MB |
| `.venv/` | ~2 GB |

清理缓存：`rm -f data/cache/panel_*.npz`；重建 Qlib：`alphaforge build --export-qlib --force`。

## 11. 定时任务建议

```bash
# 每日收盘后追加数据（增量），再重建面板
alphaforge ingest --start 2026-01-01 --end $(date +%F)
alphaforge build --export-qlib
alphaforge event --audit
alphaforge demo --no-mine
```

A 股数据通常在收盘后 16:00–18:00 更新；财务数据按公告日增量。
