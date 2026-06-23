# A股主板主力博弈型短线选股系统

本系统面向中国 A 股主板短线交易。当前真实历史 K 线主数据源使用
[BaoStock](https://www.baostock.com/)，免费、无需 Token，并启用本地缓存。

永久核心规则见 [docs/core-trading-rules.md](docs/core-trading-rules.md)。

## 账户权限白名单

系统仅允许以下 A 股主板代码进入历史数据获取、评分和推荐流程：

```text
600*** 601*** 603*** 605*** 000*** 001*** 002***
```

创业板、科创板、北交所、ETF、LOF、REITs、可转债、基金及其他非 A 股主板
标的会在股票池入口直接过滤。

## 核心策略

交易风格：A 股主板 1 至 5 个交易日短线候选。

系统采用“硬条件过滤 + 评分排序 + 空仓阈值”。每天收盘后运行一次，先剔除
非主板、风险标的和流动性不合格标的，再按 100 分模型排序。只输出最终分数
最高的前 10 只候选股，并从中展示前 3 只重点关注。

每日选股完成后，系统会额外把排序前 20 名写入 `history/selection_history.csv`，
并自动回填次日、3 日、5 日、10 日收益，用于历史验证和名次收益统计。

硬过滤规则：

1. 日成交额不低于 3 亿元，换手率不低于 2%。
2. 收盘价不低于 20 日均线的 98%。
3. 20 日均线不能明显向下，允许走平或微微向上。
4. 最近 10 个交易日涨幅不得超过 80%。
5. 最近 3 个交易日不能连续涨停。
6. 剔除 ST、*ST、退市整理、重大风险提示公告和流动性差标的。

## 评分系统

| 维度 | 分值 |
| --- | ---: |
| 趋势评分 | 40 |
| 量能评分 | 25 |
| 强度评分 | 20 |
| 资金评分 | 15 |
| 合计 | 100 |

五关条件不再一票否决。站上均线、多头排列、放量、新高、OBV 和资金流只作为
排序优劣的证据。最近 10 日涨幅超过 50%、偏离 20 日均线超过 20%、长上影线、
放量滞涨、历史高位压力和弱市场环境会扣分。

如果第一名低于 75 分，报告输出“今日无高确定性机会，建议空仓观察。”；75 至
84 分输出“可观察，轻仓试错”；85 分以上输出“可重点关注”。

## 板块强度

系统同时识别行业板块和概念板块，并合并生成板块强度排名：

- 板块涨幅排名。
- 板块资金流排名。
- 板块热度评分。
- 综合板块强度评分。
- 是否市场主线。

主线板块判定：综合分不低于 `70`，或综合排名进入前 `5`。

## 安装

```bash
python3 -m pip install -e '.[dev]'
```

## 运行

真实全市场扫描：

```bash
python3 scripts/run_daily_select.py
```

首次运行需要建立本地日 K 缓存，耗时会明显更长。建议先做小规模检查：

```bash
python3 scripts/run_daily_select.py --limit 20 --sector-limit 0
```

离线 Mock 验证：

```bash
python3 scripts/run_daily_select.py --mode mock --date 2026-06-02
python3 -m pytest
```

输出文件：

```text
reports/akshare-scan-YYYY-MM-DD.md
reports/akshare-top10-YYYY-MM-DD.csv
reports/today_stock.md
history/selection_history.csv
reports/backtest-report.md
```

生成历史验证汇总：

```bash
python3 report_backtest.py
```

## 自动定时运行

项目可通过 macOS `launchd` 在每个工作日 `16:10` 触发调度脚本：

- 系统配置文件模板：`deploy/com.stockselector.a-share-daily.plist`
- 调度脚本：`scripts/run_scheduled_select.sh`
- 交易日判断：`scripts/check_trading_day.py`

调度脚本会先用 BaoStock 判断当天是否为交易日；若不是交易日，则自动跳过。
若是交易日，则执行：

```bash
python3 scripts/run_daily_select.py --mode baostock --sector-limit 0
python3 report_backtest.py
```

## GitHub Actions 迁移

项目现在也支持通过 GitHub Actions 在云端自动运行，不依赖本机开机。

- 工作流文件：`.github/workflows/daily-select.yml`
- 定时触发：每个工作日北京时间 `16:10`
- Workflow 中使用的 cron：`10 8 * * 1-5`
  说明：GitHub Actions 的 `schedule` 使用 UTC，这里 `08:10 UTC = 16:10 Asia/Shanghai`
- 历史与报告持久化分支：`daily-data`

GitHub Actions 会执行：

```bash
python3 scripts/check_trading_day.py
python3 scripts/run_daily_select.py --mode baostock --sector-limit 0
python3 report_backtest.py
```

其中：

- `scripts/ci_restore_daily_data.sh` 会在运行前从 `daily-data` 分支恢复 `reports/` 和 `history/`
- `scripts/ci_publish_daily_data.sh` 会在运行后把新的 `reports/` 和 `history/` 推送回 `daily-data`

首次启用前，需将仓库推送到 GitHub，并保证 Actions 具有 `contents: write` 权限。

## BaoStock 接口

| 接口 | 用途 |
| --- | --- |
| `query_all_stock` | 获取 A 股股票列表 |
| `query_history_k_data_plus` | 获取股票和指数历史日 K |

BaoStock 日 K 会缓存到 `.cache/baostock/daily/`，后续运行只补齐新增日期。

## AKShare 接口

| 接口 | 用途 |
| --- | --- |
| `stock_zh_a_spot_em` | A 股市场快照 |
| `stock_zh_a_spot` | 新浪全市场快照降级源 |
| `stock_zh_a_hist` | 个股日线、成交量和成交额 |
| `stock_zh_a_daily` | 新浪个股日线降级源 |
| `stock_individual_fund_flow_rank` | 个股当日和 5 日资金流 |
| `stock_board_industry_name_em` | 行业板块 |
| `stock_board_industry_cons_em` | 行业成分股 |
| `stock_board_concept_name_em` | 概念板块 |
| `stock_board_concept_cons_em` | 概念成分股 |
| `stock_sector_fund_flow_rank` | 行业/概念板块资金流 |
| `stock_board_industry_name_ths` | 同花顺行业板块降级源 |
| `stock_board_concept_name_ths` | 同花顺概念板块降级源 |

公共源字段缺失或限流时，系统采用保守策略：重试、切换降级源、跳过异常个股，
或不生成推荐。不会伪造数据。

## 风险说明

系统输出仅为规则化短线研究候选，不构成买入建议。实盘前仍需确认分时承接、
公告风险、涨停成交约束、仓位和止损。
