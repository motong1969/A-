#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Build today_stock.md from a saved top10 CSV for email tests.")
    parser.add_argument("--date", default="2026-06-23")
    parser.add_argument("--csv", type=Path, default=Path("reports/baostock-top10-2026-06-23.csv"))
    parser.add_argument("--output", type=Path, default=Path("reports/today_stock.md"))
    args = parser.parse_args()

    frame = pd.read_csv(args.csv)
    top3 = frame.sort_values("rank").head(3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render_report(top3, args.date), encoding="utf-8")
    _repeat_pool(top3).to_csv(args.output.parent / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
    print(f"Email test report: {args.output}")
    return 0


def _render_report(top3: pd.DataFrame, report_date: str) -> str:
    lines = [
        f"# 今日主板选股摘要: {report_date}",
        "",
        "市场状态：谨慎",
        "市场评分：51.94/100",
        "通过硬过滤股票数量：52",
        "结论：邮件链路测试报告，基于 2026-06-23 已生成选股结果。",
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
                f"- 推荐理由：{row.reasons}",
                f"- 买入区间：{row.buy_range}",
                f"- 止损位：{float(row.stop_loss):.2f}",
                "- 风险等级：高",
                "",
            ]
        )
    lines.extend(
        [
            "## 最近5日重复上榜观察池",
            "",
            "| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in top3.itertuples():
        lines.append(
            f"| {str(row.code).zfill(6)} {row.name} | {int(row.rank)} | 1 | 1 | "
            f"{float(row.score):.2f} | 暂不操作 |"
        )
    strongest = top3.sort_values("rank").iloc[0]
    lines.extend(
        [
            "",
            "最近5日最强股票：",
            f"{str(strongest['code']).zfill(6)} {strongest['name']}，最近5日出现 1 次，连续上榜 1 天，"
            f"今日排名第 {int(strongest['rank'])}，最新评分 {float(strongest['score']):.2f}。",
            "",
            "今日优先观察股票：",
            "1. 暂无",
            "2. 暂无",
            "3. 暂无",
            "",
        ]
    )
    return "\n".join(lines)


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


if __name__ == "__main__":
    raise SystemExit(main())
