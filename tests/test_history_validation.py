from datetime import date
from pathlib import Path

import pandas as pd

from stock_selector.akshare_engine import AkShareV1Engine
from stock_selector.data.akshare_mock import MockAkShareDataFetcher
from stock_selector.history_validation import generate_backtest_report, update_selection_history


def test_update_selection_history_saves_top20_and_backfills_returns(tmp_path: Path) -> None:
    fetcher = MockAkShareDataFetcher()
    result = AkShareV1Engine(fetcher=fetcher).run(date(2026, 6, 2))
    history_path = tmp_path / "history" / "selection_history.csv"

    update_selection_history(result, fetcher=fetcher, history_path=history_path, as_of_date=date(2026, 6, 12))

    history = pd.read_csv(history_path)
    assert len(history) == result.scored_count
    assert set(history.columns) == {
        "date",
        "rank",
        "code",
        "name",
        "sector",
        "score",
        "close_price",
        "next_day_return",
        "return_3d",
        "return_5d",
        "return_10d",
    }
    first_row = history.sort_values("rank").iloc[0]
    assert first_row["rank"] == 1
    assert pd.notna(first_row["next_day_return"])
    assert pd.notna(first_row["return_10d"])


def test_generate_backtest_report_formats_rank_and_win_rate_sections(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "selection_history.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "date": "2026-06-02",
                "rank": 1,
                "code": "600001",
                "name": "样本1",
                "sector": "人工智能",
                "score": 88.0,
                "close_price": 10.0,
                "next_day_return": 0.01,
                "return_3d": 0.02,
                "return_5d": -0.01,
                "return_10d": 0.05,
            },
            {
                "date": "2026-06-02",
                "rank": 2,
                "code": "600002",
                "name": "样本2",
                "sector": "机器人",
                "score": 85.0,
                "close_price": 11.0,
                "next_day_return": -0.02,
                "return_3d": 0.01,
                "return_5d": 0.03,
                "return_10d": 0.04,
            },
        ]
    ).to_csv(history_path, index=False, encoding="utf-8-sig")

    report = generate_backtest_report(history_path=history_path)

    assert "## 第一名平均收益" in report
    assert "## 第二名平均收益" in report
    assert "## 前10名平均收益" in report
    assert "## 胜率统计" in report
