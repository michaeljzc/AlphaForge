# Qlib 集成说明

> 官方仓库：<https://github.com/microsoft/qlib>
> 本机运行版本：`pyqlib==0.9.7`（官方发布包，代码即 Qlib 仓库的 release 分支）
> 数据目录：`data/qlib_cn/`
> 原生链路：`src/alphaforge/qlib_native.py`

## 1. 哪些部分真正由 Qlib 承担

| 环节 | Qlib 组件 | AlphaForge 中的位置 |
|---|---|---|
| 数据格式 | `calendars/`、`instruments/`、`features/*.day.bin` | `data/qlib_export.py` |
| 数据读取 | `qlib.data.D.features` | `qlib_export.verify_parity()` |
| 因子定义 | `Alpha158DL.get_feature_config()` 的 158 个表达式 | `expr/library.py::alpha158_factors()` |
| 模型 | `qlib.contrib.model.gbdt.LGBModel` | `qlib_native.py` |
| 实验记录 | `qlib.workflow.R`（MLflow recorder） | `qlib_native.py` |
| 组合策略 | `qlib.contrib.strategy.TopkDropoutStrategy` | `qlib_native.py` |
| 回测 | `qlib.backtest.backtest` + `SimulatorExecutor` | `qlib_native.py` |
| 基准 | `SH000300` 的 Qlib instrument | `qlib_export._export_benchmarks()` |

`alphaforge qlib native` 的调用链：

```text
AlphaForge Panel
  └─ 向量化计算 Alpha158 的 158 个表达式值
      └─ NativeDataset（DatasetH 兼容：MultiIndex(datetime, instrument) + feature/label 分组）
          └─ qlib.contrib.model.gbdt.LGBModel.fit / predict
              ├─ qlib.workflow.R 记录参数与指标
              ├─ TopkDropoutStrategy(signal=pred, topk=50, n_drop=5)
              └─ qlib.backtest.backtest(..., benchmark="SH000300",
                     executor=SimulatorExecutor, exchange_kwargs=...)
```

## 2. 为什么是“Qlib + 自研”的混合

1. **Qlib 的 Alpha158 handler 在 A 股全池上过慢**  
   实测 `Alpha158(instruments='alphaforge100', 2022–2024)` 超过 10 分钟未完成；
   1267 只规模不可用。原因是 Qlib 按 instrument × expression 逐次计算，Python 调度开销大。
   因此因子值改由 AlphaForge 的 `(T,N)` 向量化引擎计算，但表达式定义直接来自 Qlib，
   数值语义（`Ref/Mean/Std/Rank/Greater/...`）已做翻译与校验。

2. **T0 是事件截面，不是 Qlib 的日历截面**  
   Qlib 的 `DatasetH`/`DataHandler` 以“日期 × 全部 instrument”组织；T0 的每个样本是
   “某只股票的一次启动事件”，不同股票的 T0 不在同一天。事件样本库、事件截面 IC、
   可交易性掩码需要自研，这也是平台差异化所在。

3. **A 股撮合规则需要精确控制**  
   Qlib 的 `Exchange` 支持涨跌停/成本，但 AlphaForge 还需要 T+1、100 股整手、
   成交额占比、延迟订单重试；因此保留自研撮合，并用同一组 Qlib 预测做“双引擎对照”。

## 3. 实测结果（150 只样本，2025-01 ~ 2026-10 样本外）

| 项 | 结果 |
|---|---|
| Qlib DatasetH 兼容数据集 | 210,600 行 / 150 只 / 158 特征 |
| Qlib LGBModel 月度 IC / ICIR | 0.0160 / 0.21 |
| Qlib 原生回测（TopkDropout + SimulatorExecutor） | 年化 16.3%、IR 0.99、最大回撤 -30.3%、平均日换手 20.3%、累计成本 8.9% |
| 同一预测 → AlphaForge A 股撮合 | 年化 15.5%、夏普 0.76、最大回撤 -20.4%、IR 1.16 |

> Qlib 原生回测默认 `deal_price=close`，AlphaForge 为 t+1 开盘撮合，两者不能直接比较绝对收益；
> 该表用于验证“同一组预测在不同撮合规则下的差异”。

## 4. 如何换成 GitHub 源码安装

当前使用官方 PyPI wheel。若需要固定到某个 commit：

```bash
cd /Users/crsec_ai_lab/Quant/qlib
git clone https://github.com/microsoft/qlib.git .vendor/qlib
.venv/bin/pip install -e .vendor/qlib --no-deps
.venv/bin/python -c "import qlib; print(qlib.__version__, qlib.__file__)"
```

注意：

- Qlib 源码安装需要编译 Cython 扩展（`python setup.py build_ext --inplace`）；
- 本机 Python 3.12 + macOS arm64 已验证 wheel 可用，源码安装请保留 `--no-deps`，避免
  与已安装的 pandas/numpy 版本冲突；
- 升级 Qlib 后重跑 `alphaforge qlib verify`，确认 `max|diff|` 仍为 0。

## 5. 尚未接入的 Qlib 能力

- `qrun` YAML 工作流 / `qlib.workflow` 的完整实验管理；
- Qlib 模型动物园中的 LSTM/Transformer/ALSTM（需要 PyTorch，本机未安装）；
- `OnlineManager` 在线 serving 与 rolling retrain；
- `RD-Agent(Q)` 自动研究循环（独立项目，可作为下一阶段）。

这些能力都可以在现有 `qlib_native.py` 的 Dataset/Model 接口上继续扩展。
