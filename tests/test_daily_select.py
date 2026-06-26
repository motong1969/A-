from datetime import date

from stock_selector.akshare_engine import AkShareV1Engine
from stock_selector.daily_select import render_today_stock
from stock_selector.data.akshare_mock import MockAkShareDataFetcher


class LowLiquidityFetcher(MockAkShareDataFetcher):
    def market_spot(self):
        frame = super().market_spot()
        frame["成交额"] = 100_000_000
        frame["换手率"] = 1.0
        return frame

    def stock_history(self, symbol: str, end_date: date, days: int = 160):
        frame = super().stock_history(symbol, end_date, days)
        frame["amount"] = 100_000_000
        return frame


def test_render_today_stock_lists_top3_details() -> None:
    result = AkShareV1Engine(fetcher=MockAkShareDataFetcher()).run(date(2026, 6, 2))

    report = render_today_stock(
        result,
        repeat_watch_pool=[
            {
                "code": "600001",
                "name": "样本1",
                "sector": "人工智能",
                "list_count_5d": 3,
                "continuous_days": 2,
                "latest_rank": 4,
                "latest_score": 82.5,
                "advice": "优先观察",
            }
        ],
    )

    assert "# A股收盘报告: 2026-06-02" in report
    assert "## ① 今日首选" in report
    assert "决策规则：先比较最近5日上榜次数" in report
    assert "本次选择说明：" in report
    assert "## ② 今日前三" in report
    assert "## ④ 为什么今天不买" in report
    assert "距离阈值还差" in report
    assert "补分诊断：" in report
    assert "## ⑤ 次日验证" in report
    assert "## 今日推荐3只主板股票" in report
    assert "### 1." in report
    assert "- 推荐理由：" in report
    assert "- 买入区间：" in report
    assert "- 止损位：" in report
    assert "- 风险等级：" in report
    assert "## ⑧ 最近5日重复上榜（按次数排序）" in report
    assert "股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数" in report
    assert "600001 样本1 | 4 | 2 | 3 | 82.50 | 优先观察" in report
    assert "最近5日最强股票：" in report
    assert "今日优先观察股票：" in report
    assert "1. 600001 样本1 - 优先观察" in report
    assert "## ⑨ 今日所有候选股票（Top20）" in report
    assert "## ⑩ 每只股票评分明细" in report
    assert "## ⑪ 今日淘汰统计" in report
    assert "## ⑫ 历史胜率数据库" in report
    assert "## ⑬ 数据来源验证" in report
    assert "- 统计口径：全A股" in report
    assert "- 全A股上涨家数：" in report
    assert "- 全A股成交额：" in report
    assert (
        "- 涨停/跌停统计口径：" in report
        or "- 涨停/跌停统计：无法按不同涨跌幅限制精确计算，已隐藏。" in report
    )


def test_render_today_stock_preserves_empty_position_message() -> None:
    result = AkShareV1Engine(fetcher=LowLiquidityFetcher()).run(date(2026, 6, 2))

    report = render_today_stock(result)

    assert "结论：今日无高确定性机会，建议空仓观察。" in report
    assert "今日无入选股票。" in report
    assert "## ⑧ 最近5日重复上榜（按次数排序）" in report
