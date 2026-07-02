from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from stock_selector.akshare_engine import AkShareV1Engine
from stock_selector.daily_select import render_today_stock
from stock_selector.data.akshare_mock import MockAkShareDataFetcher
from stock_selector.market_style import STYLE_HISTORY_COLUMNS, analyze_market_style, update_market_style_history


@dataclass(frozen=True)
class SectorRow:
    name: str
    sector_type: str
    rank: int
    score: float
    pct_change: float
    main_net_inflow: float
    heat_score: float


class MarketStyleFetcher(MockAkShareDataFetcher):
    def full_market_spot(self) -> pd.DataFrame:
        frame = super().full_market_spot()
        sectors = ["人工智能", "PCB", "半导体", "机器人", "银行", "煤炭"] * 4
        frame["所属板块"] = sectors[: len(frame)]
        return frame

    def index_history(self, symbol: str, end_date: date, days: int = 90) -> pd.DataFrame:
        frame = super().index_history(symbol, end_date, days)
        multiplier = {
            "sz399006": 1.8,
            "sh000688": 1.6,
            "sz399001": 1.2,
            "sh000001": 0.7,
            "bj899050": 0.5,
        }.get(symbol, 1.0)
        frame["close"] = [3000 + offset * multiplier for offset in range(len(frame))]
        return frame


def test_market_style_history_records_prediction_and_validation(tmp_path) -> None:
    history_path = tmp_path / "market_style_history.csv"
    fetcher = MarketStyleFetcher()
    feature_rows = [
        {"code": "600001", "sector": "人工智能", "return_5d": 0.09, "return_10d": 0.12, "return_20d": 0.18, "style_group": "科技成长股"},
        {"code": "601002", "sector": "PCB", "return_5d": 0.08, "return_10d": 0.10, "return_20d": 0.15, "style_group": "科技成长股"},
        {"code": "600008", "sector": "银行", "return_5d": -0.01, "return_10d": 0.00, "return_20d": 0.02, "style_group": "传统低位权重股"},
    ]
    sectors = [
        SectorRow("人工智能", "概念", 1, 95, 5.2, 1_200_000_000, 9.0),
        SectorRow("PCB", "概念", 2, 90, 4.7, 900_000_000, 8.5),
        SectorRow("银行", "行业", 20, 20, -0.6, -200_000_000, 1.0),
    ]
    first = analyze_market_style(
        trade_date=date(2026, 7, 1),
        fetcher=fetcher,
        market_spot=fetcher.full_market_spot(),
        feature_rows=feature_rows,
        sector_rankings=sectors,
        history_path=history_path,
    )
    assert first.capital_directions[0].name in {"AI应用", "AI服务器", "PCB"}
    assert first.trading_decision is not None
    assert first.trading_decision.mainlines
    assert first.trading_decision.emotion.temperature >= 0
    update_market_style_history(first, history_path=history_path)

    second = analyze_market_style(
        trade_date=date(2026, 7, 2),
        fetcher=fetcher,
        market_spot=fetcher.full_market_spot(),
        feature_rows=feature_rows,
        sector_rankings=sectors,
        history_path=history_path,
    )
    update_market_style_history(second, history_path=history_path)
    history = pd.read_csv(history_path)
    assert list(history.columns) == STYLE_HISTORY_COLUMNS
    assert history.iloc[-1]["持续天数"] >= 1
    assert str(history.iloc[0]["次日验证结果"]).startswith("今日风格=")
    assert history.iloc[-1]["预测风格"] in {"科技继续", "高低切", "传统低位", "其它"}
    assert "第一主线" in history.columns
    assert "市场温度" in history.columns


def test_market_style_report_and_score_adjustment_are_rendered() -> None:
    result = AkShareV1Engine(fetcher=MarketStyleFetcher()).run(date(2026, 7, 2))
    report = render_today_stock(result)
    assert "## 市场风格分析" in report
    assert "资金主要流向：" in report
    assert "## A股每日交易决策" in report
    assert "### 市场主线分析" in report
    assert "### 市场情绪分析" in report
    assert "### 仓位建议" in report
    assert "### 交易禁区" in report
    assert "### 风格预测升级" in report
    assert "当前市场不是单边主线" in report
    assert any("市场风格调整" in item.score_breakdown for item in result.top20)
