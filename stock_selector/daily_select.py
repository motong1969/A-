from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import signal

import pandas as pd

from stock_selector.akshare_engine import AkShareSelectionResult, AkShareV1Engine
from stock_selector.data.baostock import BaoStockDataFetcher
from stock_selector.data.akshare_mock import MockAkShareDataFetcher
from stock_selector.history_validation import build_repeat_watch_pool, generate_weekly_review, update_selection_history


def _raise_run_timeout(signum, frame):
    raise TimeoutError("run_daily_select exceeded 5-minute runtime limit")


def _candidate_rows(result: AkShareSelectionResult, items) -> list[dict]:
    return [
        {
            "rank": index,
            "code": item.code,
            "name": item.name,
            "sector": item.sector,
            "sector_type": item.sector_type,
            "sector_rank": item.sector_rank,
            "sector_heat_score": item.sector_heat_score,
            "sector_is_mainline": item.sector_is_mainline,
            "score": item.score,
            "score_breakdown": item.score_breakdown,
            "trend_score": item.trend_score,
            "fund_score": item.fund_score,
            "volume_score": item.volume_score,
            "strength_score": item.strength_score,
            "risk_penalty": item.risk_penalty,
            "ma20_score": item.ma20_score,
            "ma_score": item.ma_score,
            "breakout_score": item.breakout_score,
            "risk_score": item.risk_score,
            "market_cap_score": item.market_cap_score,
            "sector_heat_bonus": item.sector_heat_bonus,
            "close": item.close,
            "ma5": round(item.ma5, 3),
            "ma10": round(item.ma10, 3),
            "ma20": round(item.ma20, 3),
            "volume_ratio": round(item.volume_ratio, 3),
            "turnover_rate": round(item.turnover_rate, 3),
            "amount": item.amount,
            "breakout_margin": round(item.breakout_margin, 4),
            "sector_pct_change": item.sector_pct_change,
            "sector_main_net_inflow": item.sector_main_net_inflow,
            "main_net_inflow": item.main_net_inflow,
            "main_net_inflow_5d": item.main_net_inflow_5d,
            "circulating_market_cap": item.circulating_market_cap,
            "buy_range": item.buy_range,
            "stop_loss": item.stop_loss,
            "first_target": item.first_target,
            "reasons": "；".join(item.reasons),
            "risks": "；".join(item.risks),
            "action": item.action,
        }
        for index, item in enumerate(items, start=1)
    ]


def _render_candidates(lines: list[str], items, *, detailed: bool) -> None:
    if not items:
        lines.append("- 暂无可评分股票。")
    for index, item in enumerate(items, start=1):
        if not detailed:
            mainline = "主线" if item.sector_is_mainline else "非主线"
            lines.append(
                f"{index}. {item.name} ({item.code}) | {item.sector_type}:{item.sector} "
                f"| 板块第{item.sector_rank} | {mainline} | {item.score:.2f}"
            )
            continue
        lines.extend(
            [
                f"### {index}. {item.name} ({item.code})",
                f"- 所属板块: {item.sector_type}:{item.sector}",
                f"- 板块排名/热度: 第{item.sector_rank} / {item.sector_heat_score:.2f}",
                f"- 是否市场主线: {'是' if item.sector_is_mainline else '否'}",
                f"- 总评分: {item.score:.2f}/100",
                f"- 分项评分: {item.score_breakdown}",
                f"- 推荐理由: {'；'.join(item.reasons)}",
                f"- 风险提示: {'；'.join(item.risks)}",
                f"- 操作建议: {item.action}",
            ]
        )


def render_result(result: AkShareSelectionResult) -> str:
    rank_names = ["第一名", "第二名", "第三名"]
    best_score = result.best.score if result.best else None
    if best_score is None or best_score < 75:
        suggestion = "今日无高确定性机会，建议空仓观察。"
        buy_decision = "否"
        risk_level = "高"
        best_name = "空仓观察"
    elif best_score < 85:
        suggestion = "可观察，轻仓试错"
        buy_decision = "轻仓观察"
        risk_level = "中"
        best_name = f"{result.best.name}（{result.best.code}）"
    else:
        suggestion = "可重点关注"
        buy_decision = "是"
        risk_level = "中" if result.market.status == "可交易" else "高"
        best_name = f"{result.best.name}（{result.best.code}）"
    lines = [
        f"# A股主板收盘后选股报告: {result.trade_date.isoformat()}",
        "",
        f"市场状态：{result.market.status}",
        f"市场评分：{result.market.score:.2f}/100",
        f"上涨家数占比：{result.market.up_ratio:.1%}",
        f"涨停 / 跌停：{result.market.limit_up_count} / {result.market.limit_down_count}",
        f"市场成交额：{result.market.total_amount / 100_000_000:.2f} 亿元",
        f"通过硬过滤股票数量：{result.scored_count}",
        f"最高分：{best_score:.2f}" if best_score is not None else "最高分：无",
        f"是否建议出手：{suggestion}",
        "",
        "排名前3名：",
        "",
    ]
    if not result.top3:
        lines.extend(["今日无高确定性机会，建议空仓观察。"])
    for index, item in enumerate(result.top3):
        lines.extend(
            [
                "",
                f"{rank_names[index]}：",
                f"股票代码：{item.code}",
                f"股票名称：{item.name}",
                f"所属板块：{item.sector}",
                f"最终评分：{item.score:.2f}",
                f"市值：{item.circulating_market_cap / 100_000_000:.2f}亿元",
                f"板块热度：{item.sector_heat_bonus:.2f}",
                f"MA20评分：{item.ma20_score:.2f}",
                f"均线评分：{item.ma_score:.2f}",
                f"成交量评分：{item.volume_score:.2f}",
                f"突破评分：{item.breakout_score:.2f}",
                f"风险评分：{item.risk_score:.2f}",
                f"买入区间：{item.buy_range}",
                f"止损位：{item.stop_loss:.2f}",
                f"第一目标位：{item.first_target:.2f}",
                f"推荐理由：{'；'.join(item.reasons)}",
            ]
        )
    lines.extend(
        [
            "",
            f"今日最优选择：{best_name}",
            f"风险等级：{risk_level}",
            f"是否建议买入：{buy_decision}",
        ]
    )
    return "\n".join(lines) + "\n"


def _risk_level_for_candidate(item, market_status: str) -> str:
    if item.score < 75:
        return "高"
    if item.score < 85:
        return "中"
    return "中" if market_status == "可交易" else "高"


def render_today_stock(
    result: AkShareSelectionResult,
    repeat_watch_pool: list[dict] | None = None,
    *,
    data_source: str = "实时数据",
    data_date: date | None = None,
    is_realtime: bool = True,
    formal_allowed: bool = True,
) -> str:
    best_score = result.best.score if result.best else None
    has_high_confidence = best_score is not None and best_score >= 75
    actual_data_date = data_date or result.trade_date
    lines = [
        f"# 今日主板选股摘要: {result.trade_date.isoformat()}",
        "",
        f"数据源名称：{data_source}",
        f"数据日期：{actual_data_date.isoformat()}",
        f"是否实时数据：{'是' if is_realtime else '否'}",
        f"是否允许作为正式选股依据：{'是' if formal_allowed else '否'}",
        "数据来源：实时数据" if is_realtime and formal_allowed else "数据来源：实时数据获取失败",
        f"市场状态：{result.market.status}",
        f"市场评分：{result.market.score:.2f}/100",
        f"通过硬过滤股票数量：{result.scored_count}",
        (
            "结论：今日有可跟踪机会，以下为前3名。"
            if has_high_confidence
            else "结论：今日无高确定性机会，建议空仓观察。以下为当日排序前3，仅供复盘观察。"
        ),
        "",
    ]
    if not result.top3:
        lines.extend(
            [
                "## 今日推荐3只主板股票",
                "",
                "今日无入选股票。",
            ]
        )
        lines.extend(_repeat_watch_pool_lines(repeat_watch_pool or []))
        return "\n".join(lines) + "\n"

    lines.extend(["## 今日推荐3只主板股票", ""])
    for index, item in enumerate(result.top3, start=1):
        lines.extend(
            [
                f"### {index}. {item.name} ({item.code})",
                f"- 所属板块：{item.sector}",
                f"- 最终评分：{item.score:.2f}",
                f"- 推荐理由：{'；'.join(item.reasons)}",
                f"- 买入区间：{item.buy_range}",
                f"- 止损位：{item.stop_loss:.2f}",
                f"- 风险等级：{_risk_level_for_candidate(item, result.market.status)}",
                "",
            ]
        )
    lines.extend(_repeat_watch_pool_lines(repeat_watch_pool or []))
    return "\n".join(lines).rstrip() + "\n"


def _repeat_watch_pool_lines(repeat_watch_pool: list[dict]) -> list[str]:
    lines = [
        "## 最近5日重复上榜观察池",
        "",
        "| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if not repeat_watch_pool:
        lines.append("| 暂无 | - | 0 | 0 | - | 暂不操作 |")
    for item in repeat_watch_pool:
        lines.append(
            "| {code} {name} | {latest_rank} | {continuous_days} | "
            "{list_count_5d} | {latest_score:.2f} | {advice} |".format(**item)
        )
    strongest = _strongest_repeat_stock(repeat_watch_pool)
    lines.extend(["", "最近5日最强股票："])
    if strongest is None:
        lines.append("暂无")
    else:
        lines.append(
            f"{strongest['code']} {strongest['name']}，最近5日出现 {strongest['list_count_5d']} 次，"
            f"连续上榜 {strongest['continuous_days']} 天，今日排名第 {strongest['latest_rank']}，"
            f"最新评分 {strongest['latest_score']:.2f}。"
        )
    lines.extend(["", "今日优先观察股票："])
    priority_items = [item for item in repeat_watch_pool if item["advice"] in {"优先观察", "可低吸观察"}][:3]
    for index in range(3):
        if index < len(priority_items):
            item = priority_items[index]
            lines.append(f"{index + 1}. {item['code']} {item['name']} - {item['advice']}")
        else:
            lines.append(f"{index + 1}. 暂无")
    lines.append("")
    return lines


def _strongest_repeat_stock(repeat_watch_pool: list[dict]) -> dict | None:
    if not repeat_watch_pool:
        return None
    return sorted(
        repeat_watch_pool,
        key=lambda item: (
            -item["list_count_5d"],
            -item["continuous_days"],
            item["latest_rank"],
            -item["latest_score"],
        ),
    )[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the A-share main-board selector.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Scan date in YYYY-MM-DD format.")
    parser.add_argument("--mode", choices=["baostock", "akshare", "mock"], default="baostock", help="Use BaoStock, legacy AKShare, or deterministic mock data.")
    parser.add_argument("--limit", type=int, help="Optional stock limit for real-data smoke tests.")
    parser.add_argument("--sector-limit", type=int, default=20, help="Number of strongest industry boards to map to stocks.")
    parser.add_argument("--output-dir", type=Path, default=Path("reports"), help="Output directory.")
    args = parser.parse_args()

    fetcher = MockAkShareDataFetcher() if args.mode == "mock" else (BaoStockDataFetcher() if args.mode == "baostock" else None)
    previous = signal.signal(signal.SIGALRM, _raise_run_timeout)
    signal.alarm(300)
    try:
        result = AkShareV1Engine(fetcher=fetcher, sector_member_limit=args.sector_limit).run(
            date.fromisoformat(args.date), limit=args.limit
        )
        report = render_result(result)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = args.output_dir / f"{args.mode}-scan-{args.date}.md"
        pool_path = args.output_dir / f"{args.mode}-top10-{args.date}.csv"
        today_stock_path = args.output_dir / "today_stock.md"
        report_path.write_text(report, encoding="utf-8")
        pd.DataFrame(_candidate_rows(result, result.top20)).to_csv(pool_path, index=False, encoding="utf-8-sig")
        run_date = date.fromisoformat(args.date)
        history_path = update_selection_history(result, fetcher=fetcher, as_of_date=run_date)
        repeat_watch_pool = build_repeat_watch_pool(history_path, as_of_date=run_date)
        pd.DataFrame(repeat_watch_pool).to_csv(args.output_dir / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
        today_stock = render_today_stock(result, repeat_watch_pool=repeat_watch_pool)
        today_stock_path.write_text(today_stock, encoding="utf-8")
        weekly_review_path = generate_weekly_review(as_of_date=run_date)
        print(report)
        print(f"Top10 CSV: {pool_path}")
        print(f"Markdown report: {report_path}")
        print(f"Today summary: {today_stock_path}")
        print(f"Selection history: {history_path}")
        if weekly_review_path is not None:
            print(f"Weekly review: {weekly_review_path}")
    except TimeoutError as exc:
        print(f"运行超时：{exc}")
        print("已在5分钟上限内终止本次执行。")
        return 1
    except Exception as exc:
        print(f"数据获取失败：{exc}")
        print("请稍后重试，或使用 --mode mock 验证流程。")
        return 1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        if hasattr(fetcher, "close"):
            fetcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
