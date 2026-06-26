from datetime import date
from pathlib import Path

import pandas as pd

from stock_selector.akshare_engine import AkShareV1Engine
from stock_selector.data.akshare_mock import MockAkShareDataFetcher
from stock_selector.history_validation import (
    build_repeat_watch_pool,
    generate_backtest_report,
    generate_weekly_review,
    next_day_validation_lines,
    performance_summary_lines,
    update_performance_summary_database,
    update_selection_history,
)


def test_update_selection_history_saves_top20_and_backfills_returns(tmp_path: Path) -> None:
    fetcher = MockAkShareDataFetcher()
    result = AkShareV1Engine(fetcher=fetcher).run(date(2026, 6, 2))
    history_path = tmp_path / "history" / "selection_history.csv"

    update_selection_history(result, fetcher=fetcher, history_path=history_path, as_of_date=date(2026, 6, 12))

    history = pd.read_csv(history_path)
    assert len(history) == result.scored_count
    assert {
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
        "max_gain_5d",
        "max_drawdown_5d",
        "ma20_score",
        "ma_score",
        "volume_score",
        "breakout_score",
        "risk_score",
    }.issubset(set(history.columns))
    first_row = history.sort_values("rank").iloc[0]
    assert first_row["rank"] == 1
    assert pd.notna(first_row["next_day_return"])
    assert pd.notna(first_row["return_10d"])
    assert pd.notna(first_row["max_gain_5d"])
    assert pd.notna(first_row["max_drawdown_5d"])
    assert pd.notna(first_row["ma20_score"])


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


def test_generate_weekly_review_writes_friday_summary(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "selection_history.csv"
    output_dir = tmp_path / "reports"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for day_index, day in enumerate(["2026-06-01", "2026-06-02", "2026-06-03"], start=1):
        for rank in (1, 2, 3):
            rows.append(
                {
                    "date": day,
                    "rank": rank,
                    "code": f"60000{rank}",
                    "name": f"样本{rank}",
                    "sector": "人工智能",
                    "score": 90 - rank,
                    "close_price": 10 + rank,
                    "ma20_score": 8 + rank + day_index,
                    "ma_score": 7 + rank,
                    "volume_score": 6 + rank,
                    "breakout_score": 5 + rank,
                    "risk_score": -rank,
                    "market_cap_score": 2,
                    "sector_heat_bonus": 3,
                    "next_day_return": 0.01 * rank,
                    "return_3d": 0.015 * rank,
                    "return_5d": 0.02 * rank,
                    "return_10d": 0.03 * rank,
                    "max_gain_5d": 0.03 * rank,
                    "max_drawdown_5d": -0.01 * rank,
                }
            )
    pd.DataFrame(rows).to_csv(history_path, index=False, encoding="utf-8-sig")

    weekly_path = generate_weekly_review(
        history_path=history_path,
        output_dir=output_dir,
        as_of_date=date(2026, 6, 5),
    )

    assert weekly_path == output_dir / "weekly-review-2026-06-05.md"
    report = weekly_path.read_text(encoding="utf-8")
    assert "## 本周每天前三名" in report
    assert "## 每只股票后续表现" in report
    assert "## 前三名平均收益" in report
    assert "## 胜率" in report
    assert "## 最大回撤" in report
    assert "## 哪个评分因子最有效" in report
    assert "## 假强势股票" in report
    assert "## 最终结论" in report


def test_generate_weekly_review_skips_non_friday(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "selection_history.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=["date", "rank", "code", "name", "sector", "score", "close_price"]).to_csv(
        history_path,
        index=False,
        encoding="utf-8-sig",
    )

    weekly_path = generate_weekly_review(
        history_path=history_path,
        output_dir=tmp_path / "reports",
        as_of_date=date(2026, 6, 3),
    )

    assert weekly_path is None


def test_next_day_validation_and_performance_summary_database(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "selection_history.csv"
    summary_path = tmp_path / "history" / "performance_summary.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        _history_row("2026-06-22", 1, "600001", "样本1", 80, next_day_return=0.02, return_3d=0.03, return_5d=0.04, max_drawdown_5d=-0.01),
        _history_row("2026-06-22", 2, "600002", "样本2", 79, next_day_return=-0.01, return_3d=0.01, return_5d=0.02, max_drawdown_5d=-0.03),
        _history_row("2026-06-22", 3, "600003", "样本3", 78, next_day_return=0.03, return_3d=0.02, return_5d=-0.01, max_drawdown_5d=-0.06),
    ]
    pd.DataFrame(rows).to_csv(history_path, index=False, encoding="utf-8-sig")

    lines = next_day_validation_lines(history_path, as_of_date=date(2026, 6, 23))
    output = "\n".join(lines)
    assert "验证对象：2026-06-22" in output
    assert "前三名次日平均收益" in output

    generated = update_performance_summary_database(
        history_path,
        output_path=summary_path,
        as_of_date=date(2026, 6, 23),
    )
    assert generated == summary_path
    summary = pd.read_csv(summary_path)
    assert {"weekly", "monthly"}.issubset(set(summary["period_type"]))

    summary_lines = performance_summary_lines(summary_path)
    assert "权重调整原则" in "\n".join(summary_lines)


def test_build_repeat_watch_pool_counts_recent_five_trading_days(tmp_path: Path) -> None:
    history_path = tmp_path / "history" / "selection_history.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        _history_row("2026-06-16", 1, "600999", "过期样本", 80),
        _history_row("2026-06-17", 2, "600001", "样本1", 78),
        _history_row("2026-06-18", 4, "600001", "样本1", 79),
        _history_row("2026-06-19", 3, "600001", "样本1", 80),
        _history_row("2026-06-23", 2, "600001", "样本1", 82),
        _history_row("2026-06-24", 1, "600001", "样本1", 83),
        _history_row("2026-06-23", 4, "600002", "样本2", 86),
        _history_row("2026-06-24", 6, "600002", "样本2", 82),
        _history_row("2026-06-24", 8, "600003", "样本3", 77),
    ]
    pd.DataFrame(rows).to_csv(history_path, index=False, encoding="utf-8-sig")

    pool = build_repeat_watch_pool(history_path=history_path, as_of_date=date(2026, 6, 24))

    first = next(item for item in pool if item["code"] == "600001")
    cautious = next(item for item in pool if item["code"] == "600002")
    single = next(item for item in pool if item["code"] == "600003")
    assert first["list_count_5d"] == 5
    assert first["continuous_days"] == 5
    assert first["latest_rank"] == 1
    assert first["latest_score"] == 83
    assert first["advice"] == "优先观察"
    assert cautious["advice"] == "谨慎观察"
    assert single["advice"] == "暂不操作"
    assert "600999" not in {item["code"] for item in pool}


def _history_row(
    day: str,
    rank: int,
    code: str,
    name: str,
    score: float,
    *,
    next_day_return=pd.NA,
    return_3d=pd.NA,
    return_5d=pd.NA,
    return_10d=pd.NA,
    max_gain_5d=pd.NA,
    max_drawdown_5d=pd.NA,
) -> dict:
    return {
        "date": day,
        "rank": rank,
        "code": code,
        "name": name,
        "sector": "人工智能",
        "score": score,
        "close_price": 10.0,
        "ma20_score": 8.0,
        "ma_score": 7.0,
        "volume_score": 6.0,
        "breakout_score": 5.0,
        "risk_score": -1.0,
        "market_cap_score": 2.0,
        "sector_heat_bonus": 3.0,
        "next_day_return": next_day_return,
        "return_3d": return_3d,
        "return_5d": return_5d,
        "return_10d": return_10d,
        "max_gain_5d": max_gain_5d,
        "max_drawdown_5d": max_drawdown_5d,
    }
