#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from build_fallback_report import HISTORY_HEADER


def main() -> int:
    parser = argparse.ArgumentParser(description="Build today_stock.md from local cached selector CSV.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--history", type=Path, default=Path("history/selection_history.csv"))
    args = parser.parse_args()

    args.reports_dir.mkdir(parents=True, exist_ok=True)
    args.history.parent.mkdir(parents=True, exist_ok=True)
    if not args.history.exists():
        args.history.write_text(HISTORY_HEADER, encoding="utf-8")

    source = _data_source(args.reports_dir)
    csv_path = _latest_top10(args.reports_dir)
    output_path = args.reports_dir / "today_stock.md"
    if csv_path is None:
        source = "降级报告"
        output_path.write_text(_empty_report(args.date, source), encoding="utf-8")
        _empty_repeat_pool(args.reports_dir)
        print(f"cached_report={output_path}")
        print(f"data_source={source}")
        return 0

    frame = pd.read_csv(csv_path)
    top3 = frame.sort_values("rank").head(3)
    output_path.write_text(_render_report(top3, args.date, source, csv_path.name), encoding="utf-8")
    _repeat_pool(top3).to_csv(args.reports_dir / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
    print(f"cached_report={output_path}")
    print(f"cached_top10={csv_path}")
    print(f"data_source={source}")
    return 0


def _data_source(reports_dir: Path) -> str:
    status_path = reports_dir / "data-source-status.txt"
    if not status_path.exists():
        return "降级报告"
    value = status_path.read_text(encoding="utf-8").strip()
    return value if value in {"实时数据", "缓存数据", "降级报告"} else "降级报告"


def _latest_top10(reports_dir: Path) -> Path | None:
    files = sorted(reports_dir.glob("baostock-top10-*.csv"), reverse=True)
    return files[0] if files else None


def _render_report(top3: pd.DataFrame, report_date: str, source: str, source_file: str) -> str:
    observation_note = "缓存/降级模式只输出观察，不给出买入建议。"
    lines = [
        f"# 今日主板选股摘要: {report_date}",
        "",
        f"数据来源：{source}",
        f"本地选股结果：{source_file}",
        "市场状态：观察",
        "市场评分：暂无",
        f"结论：{observation_note}",
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
                f"- 推荐理由：基于本地缓存选股结果；{row.reasons}",
                "- 操作建议：观察",
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
            f"{float(row.score):.2f} | 普通观察 |"
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
                "advice": "普通观察",
            }
            for row in top3.itertuples()
        ]
    )


def _empty_report(report_date: str, source: str) -> str:
    return "\n".join(
        [
            f"# 今日主板选股摘要: {report_date}",
            "",
            f"数据来源：{source}",
            "市场状态：失败降级",
            "市场评分：暂无",
            "结论：未找到可用本地选股 CSV，发送失败报告。",
            "",
            "## 今日推荐3只主板股票",
            "",
            "今日无入选股票。",
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


def _empty_repeat_pool(reports_dir: Path) -> None:
    pd.DataFrame(columns=["code", "name", "today_rank", "continuous_days", "list_count_5d", "latest_score", "advice"]).to_csv(
        reports_dir / "repeat-watch-pool.csv",
        index=False,
        encoding="utf-8-sig",
    )


if __name__ == "__main__":
    raise SystemExit(main())
