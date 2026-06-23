#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


HISTORY_HEADER = (
    "date,rank,code,name,sector,score,close_price,ma20_score,ma_score,volume_score,"
    "breakout_score,risk_score,market_cap_score,sector_heat_bonus,next_day_return,return_3d,"
    "return_5d,return_10d,max_gain_5d,max_drawdown_5d\n"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fallback today_stock.md when selector times out or fails.")
    parser.add_argument("--date", default="2026-06-23")
    parser.add_argument("--reason", default="选股超时或失败，使用已有数据生成降级报告。")
    parser.add_argument("--csv", type=Path, default=Path("reports/baostock-top10-2026-06-23.csv"))
    parser.add_argument("--output", type=Path, default=Path("reports/today_stock.md"))
    parser.add_argument("--history", type=Path, default=Path("history/selection_history.csv"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.history.parent.mkdir(parents=True, exist_ok=True)
    if not args.history.exists():
        args.history.write_text(HISTORY_HEADER, encoding="utf-8")

    if not args.csv.exists():
        args.output.write_text(_empty_failure_report(args.date, args.reason), encoding="utf-8")
        pd.DataFrame(columns=["code", "name", "today_rank", "continuous_days", "list_count_5d", "latest_score", "advice"]).to_csv(
            args.output.parent / "repeat-watch-pool.csv",
            index=False,
            encoding="utf-8-sig",
        )
        print(f"Fallback report: {args.output}")
        return 0

    frame = pd.read_csv(args.csv)
    top3 = frame.sort_values("rank").head(3)
    args.output.write_text(_render_report(top3, args.date, args.reason), encoding="utf-8")
    _repeat_pool(top3).to_csv(args.output.parent / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
    print(f"Fallback report: {args.output}")
    return 0


def _render_report(top3: pd.DataFrame, report_date: str, reason: str) -> str:
    lines = [
        f"# 今日主板选股摘要: {report_date}",
        "",
        "市场状态：失败降级",
        "市场评分：暂无",
        f"结论：{reason}",
        "",
        "## 今日推荐3只主板股票",
        "",
    ]
    for row in top3.itertuples():
        lines.extend(
            [
                f"### {int(row.rank)}. {row.name} ({str(row.code).zfill(6)})",
                f"- 所属板块：{row.sector}",
                f"- 最终评分：{float(row.score):.2f}",
                f"- 推荐理由：降级报告复用已有 2026-06-23 选股结果；{row.reasons}",
                f"- 买入区间：{row.buy_range}",
                f"- 止损位：{float(row.stop_loss):.2f}",
                "- 风险等级：高",
                "",
            ]
        )
    lines.extend(_repeat_lines(top3))
    return "\n".join(lines)


def _repeat_lines(top3: pd.DataFrame) -> list[str]:
    lines = [
        "## 最近5日重复上榜观察池",
        "",
        "| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in top3.itertuples():
        lines.append(
            f"| {str(row.code).zfill(6)} {row.name} | {int(row.rank)} | 1 | 1 | "
            f"{float(row.score):.2f} | 暂不操作 |"
        )
    first = top3.sort_values("rank").iloc[0]
    lines.extend(
        [
            "",
            "最近5日最强股票：",
            f"{str(first['code']).zfill(6)} {first['name']}，最近5日出现 1 次，连续上榜 1 天，"
            f"今日排名第 {int(first['rank'])}，最新评分 {float(first['score']):.2f}。",
            "",
            "今日优先观察股票：",
            "1. 暂无",
            "2. 暂无",
            "3. 暂无",
            "",
        ]
    )
    return lines


def _repeat_pool(top3: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "code": str(row.code).zfill(6),
                "name": row.name,
                "today_rank": int(row.rank),
                "continuous_days": 1,
                "list_count_5d": 1,
                "latest_score": round(float(row.score), 2),
                "advice": "暂不操作",
            }
            for row in top3.itertuples()
        ]
    )


def _empty_failure_report(report_date: str, reason: str) -> str:
    return "\n".join(
        [
            f"# 今日主板选股摘要: {report_date}",
            "",
            "市场状态：失败降级",
            "市场评分：暂无",
            f"结论：{reason}",
            "",
            "## 今日推荐3只主板股票",
            "",
            "今日无入选股票。选股超时或失败，且未找到可复用的历史报告。",
            "",
            "## 最近5日重复上榜观察池",
            "",
            "| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
            "| 暂无 | - | 0 | 0 | - | 暂不操作 |",
            "",
            "最近5日最强股票：",
            "暂无",
            "",
            "今日优先观察股票：",
            "1. 暂无",
            "2. 暂无",
            "3. 暂无",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
