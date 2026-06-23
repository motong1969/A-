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

    assert "# 今日主板选股摘要: 2026-06-02" in report
    assert "## 今日推荐3只主板股票" in report
    assert "### 1." in report
    assert "- 推荐理由：" in report
    assert "- 买入区间：" in report
    assert "- 止损位：" in report
    assert "- 风险等级：" in report
    assert "## 最近5日重复上榜观察池" in report
    assert "股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数" in report
    assert "600001 样本1 | 4 | 2 | 3 | 82.50 | 优先观察" in report
    assert "最近5日最强股票：" in report
    assert "今日优先观察股票：" in report
    assert "1. 600001 样本1 - 优先观察" in report


def test_render_today_stock_preserves_empty_position_message() -> None:
    result = AkShareV1Engine(fetcher=LowLiquidityFetcher()).run(date(2026, 6, 2))

    report = render_today_stock(result)

    assert "结论：今日无高确定性机会，建议空仓观察。" in report
    assert "今日无入选股票。" in report
    assert "## 最近5日重复上榜观察池" in report
