#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import signal
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_selector.akshare_engine import AkShareV1Engine
from stock_selector.daily_select import _candidate_rows, render_result, render_today_stock
from stock_selector.data.realtime import RealtimeMainBoardFetcher, RealtimeMarketDataError
from stock_selector.history_validation import (
    build_repeat_watch_pool,
    generate_weekly_review,
    next_day_validation_lines,
    performance_summary_lines,
    update_performance_summary_database,
    update_selection_history,
)


class RunTimeout(RuntimeError):
    pass


def _raise_timeout(signum, frame):
    raise RunTimeout("realtime selector exceeded runtime limit")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run formal selector with live same-day market data only.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--pool", type=Path, default=Path("data/mainboard_stock_pool.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sector-limit", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=280)
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.alarm(args.timeout_seconds)
    fetcher = None
    try:
        fetcher = RealtimeMainBoardFetcher(trade_date=trade_date, pool_path=args.pool)
        result = AkShareV1Engine(fetcher=fetcher, sector_member_limit=args.sector_limit).run(trade_date, limit=args.limit)
        _validate_formal_result(result, fetcher.data_source_name, trade_date)
        report_path = args.output_dir / f"realtime-scan-{args.date}.md"
        pool_path = args.output_dir / f"realtime-top10-{args.date}.csv"
        today_stock_path = args.output_dir / "today_stock.md"
        report_path.write_text(render_result(result), encoding="utf-8")
        _candidate_frame(result, result.top20).to_csv(pool_path, index=False, encoding="utf-8-sig")
        history_path = update_selection_history(result, fetcher=fetcher, as_of_date=trade_date)
        summary_path = update_performance_summary_database(history_path, as_of_date=trade_date)
        repeat_watch_pool = build_repeat_watch_pool(history_path, as_of_date=trade_date)
        pd.DataFrame(repeat_watch_pool).to_csv(args.output_dir / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
        today_stock_path.write_text(
            render_today_stock(
                result,
                repeat_watch_pool=repeat_watch_pool,
                next_day_validation=next_day_validation_lines(history_path, as_of_date=trade_date),
                performance_summary=performance_summary_lines(summary_path),
                data_source=fetcher.data_source_name,
                data_date=trade_date,
                is_realtime=True,
                formal_allowed=True,
            ),
            encoding="utf-8",
        )
        weekly_review_path = generate_weekly_review(as_of_date=trade_date)
        print(f"realtime_report={today_stock_path}")
        print(f"data_source={fetcher.data_source_name}")
        print(f"data_date={trade_date.isoformat()}")
        print("is_realtime=true")
        print("formal_allowed=true")
        print(f"top10_csv={pool_path}")
        print(f"selection_history={history_path}")
        print(f"performance_summary={summary_path}")
        for warning in getattr(fetcher, "data_warnings", []):
            print(f"data_warning={warning}")
        if weekly_review_path is not None:
            print(f"weekly_review={weekly_review_path}")
        return 0
    except (RealtimeMarketDataError, RunTimeout, Exception) as exc:
        today_stock_path = args.output_dir / "today_stock.md"
        source_errors = getattr(fetcher, "source_errors", []) if fetcher is not None else []
        today_stock_path.write_text(_failure_report(trade_date, exc, source_errors), encoding="utf-8")
        _empty_repeat_pool(args.output_dir)
        print(f"realtime_report={today_stock_path}")
        print("data_source=none")
        print(f"data_date={trade_date.isoformat()}")
        print("is_realtime=false")
        print("formal_allowed=false")
        print(f"failure={type(exc).__name__}: {exc}")
        for error in source_errors:
            print(f"source_error={error}")
        return 0
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        if fetcher is not None:
            fetcher.close()


def _validate_formal_result(result, data_source: str, trade_date: date) -> None:
    if not data_source:
        raise RealtimeMarketDataError("没有可用实时数据源")
    for item in result.top20:
        if item.close <= 0:
            raise RealtimeMarketDataError(f"{item.code} 缺少当天收盘价")


def _candidate_frame(result, items) -> pd.DataFrame:
    columns = [
        "rank",
        "code",
        "name",
        "sector",
        "sector_type",
        "sector_rank",
        "sector_heat_score",
        "sector_is_mainline",
        "score",
        "score_breakdown",
        "trend_score",
        "fund_score",
        "volume_score",
        "strength_score",
        "risk_penalty",
        "ma20_score",
        "ma_score",
        "breakout_score",
        "risk_score",
        "market_cap_score",
        "sector_heat_bonus",
        "close",
        "ma5",
        "ma10",
        "ma20",
        "volume_ratio",
        "turnover_rate",
        "amount",
        "breakout_margin",
        "sector_pct_change",
        "sector_main_net_inflow",
        "main_net_inflow",
        "main_net_inflow_5d",
        "circulating_market_cap",
        "buy_range",
        "stop_loss",
        "first_target",
        "reasons",
        "risks",
        "action",
    ]
    return pd.DataFrame(_candidate_rows(result, items), columns=columns)


def _failure_report(trade_date: date, exc: Exception, source_errors: list[str]) -> str:
    lines = [
        f"# 今日主板选股摘要: {trade_date.isoformat()}",
        "",
        "数据源名称：无",
        f"数据日期：{trade_date.isoformat()}",
        "是否实时数据：否",
        "是否允许作为正式选股依据：否",
        "数据来源：实时数据获取失败",
        "市场状态：失败",
        "市场评分：暂无",
        "结论：所有实时行情源均不可用或未取得当天有效行情，本日不输出正式前三、不输出今日首选、不提供推荐。",
        "",
        "## 失败原因",
        "",
        f"- {type(exc).__name__}: {exc}",
    ]
    for error in source_errors:
        lines.append(f"- {error}")
    lines.extend(
        [
            "",
            "## 今日推荐3只主板股票",
            "",
            "未生成：实时数据获取失败。",
            "",
            "## 最近5日重复上榜观察池",
            "",
            "| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
            "| 暂无 | - | 0 | 0 | - | 暂不操作 |",
            "",
            "今日优先观察股票：",
            "1. 暂无",
            "2. 暂无",
            "3. 暂无",
            "",
        ]
    )
    return "\n".join(lines)


def _empty_repeat_pool(output_dir: Path) -> None:
    pd.DataFrame(columns=["code", "name", "today_rank", "continuous_days", "list_count_5d", "latest_score", "advice"]).to_csv(
        output_dir / "repeat-watch-pool.csv",
        index=False,
        encoding="utf-8-sig",
    )


if __name__ == "__main__":
    raise SystemExit(main())
