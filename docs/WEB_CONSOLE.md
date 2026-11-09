# Web 控制台

```bash
alphaforge web --port 8787
# http://127.0.0.1:8787
```

本地 FastAPI + 原生 JS + ECharts，无需 Node 构建；`web/static/vendor/echarts.min.js`
随仓库提供，断网可用。服务只绑定 `127.0.0.1`。

## 1. 页面

| 视图 | 内容 |
|---|---|
| 总览 | 数据区间/股票池/因子库/T0 事件/组合年化/审计；组合净值；因子闸门 Top；事件分级 |
| 因子库 | 搜索、类别过滤、排序；点击任意因子打开详情抽屉（IC 序列、五分组、分层净值、闸门、表达式、中文说明）；「全部因子字典」列出 355 个因子的中文说明；在线表达式评估 |
| 组合回测 | 收益/夏普/回撤/超额/IR；净值 vs 基准；回撤；月度收益 |
| T0 事件 | 三级标签（对数轴）、事件截面 IC、事件组合净值、特征 IC 表、审计横幅 |
| GP 挖掘 | 进化曲线、候选因子 Train/Valid/Test 表 |
| Qlib 原生 | 二进制一致性、LGBModel 月度 IC、Qlib 回测、AlphaForge 双引擎对照 |
| 数据源 | Tushare/iFinD/DataYes 配置状态、掩码 Token、一键探活、数据湖行数 |

## 2. API

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/overview` | 总览聚合（artifact 摘要） |
| GET | `/api/backtest` | 回测 metrics + equity + benchmark |
| GET | `/api/events` | 事件摘要、IC、回测、审计 |
| GET | `/api/gp` | GP history / evaluated |
| GET | `/api/qlib` | Qlib 导出元数据 + 原生结果 |
| GET | `/api/factors` | 因子快照索引 |
| GET | `/api/factors/{name}` | 单因子完整画像 |
| POST | `/api/factors/evaluate` | 在线评估表达式（body: `{"expression": "...", "start": "2021-01-01"}`） |
| GET | `/api/sources` | 数据源配置 + 缓存探活结果 |
| POST | `/api/sources/{source}/probe` | 实时探活 `tushare/ifind/datayes` |
| GET | `/api/data/summary` | market.db 各表行数 |

数据来自 `reports/artifacts/`，由 `alphaforge demo` 生成；因子详情来自
`reports/artifacts/factors/index.json` 与单因子 JSON。

## 3. 扩展

- 新页面：在 `static/index.html` 增加 `<section class="view" id="view-xxx">`，
  在 `app.js` 的 `VIEW_META`、`LOADERS` 中注册，导航加 `data-view="xxx"`；
- 新 API：在 `web/app.py` 中增加路由，返回 JSON；
- 样式：`static/style.css` 的 CSS 变量 `--blue/--navy/--line` 可整体换肤；
- 重新生成数据：`alphaforge demo`（或 `alphaforge factors mine` / `qlib native`）。

## 4. 故障排查

| 现象 | 处理 |
|---|---|
| `address already in use` | `lsof -nP -iTCP:8787 -sTCP:LISTEN`，结束旧进程 |
| 页面空白 | 确认 `alphaforge demo` 已生成 `reports/artifacts/demo_summary.json` |
| 图表不显示 | 检查 `static/vendor/echarts.min.js` 是否存在；浏览器禁用 JS？ |
| 因子详情 404 | 运行 `alphaforge demo --no-mine` 生成 `reports/artifacts/factors/` |
| 数据源未配置 | 配 `config/credentials.json` 或环境变量；支持复用 quantlab 的凭据文件 |
