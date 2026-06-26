from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import signal

import pandas as pd

from stock_selector.akshare_engine import AkShareSelectionResult, AkShareV1Engine
from stock_selector.data.baostock import BaoStockDataFetcher
from stock_selector.data.akshare_mock import MockAkShareDataFetcher
from stock_selector.history_validation import (
    build_repeat_watch_pool,
    generate_weekly_review,
    next_day_validation_lines,
    performance_summary_lines,
    update_performance_summary_database,
    update_selection_history,
)


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
    next_day_validation: list[str] | None = None,
    performance_summary: list[str] | None = None,
    data_source: str = "实时数据",
    data_date: date | None = None,
    is_realtime: bool = True,
    formal_allowed: bool = True,
) -> str:
    best_score = result.best.score if result.best else None
    has_high_confidence = best_score is not None and best_score >= 75
    actual_data_date = data_date or result.trade_date
    repeat_watch_pool = repeat_watch_pool or []
    next_day_validation = next_day_validation or ["暂无已完成的次日验证数据。"]
    performance_summary = performance_summary or ["历史胜率数据库暂无可统计样本。"]
    stats = result.elimination_stats or {}
    lines = [
        f"# A股收盘报告: {result.trade_date.isoformat()}",
        "",
        f"数据源名称：{data_source}",
        f"数据日期：{actual_data_date.isoformat()}",
        f"是否实时数据：{'是' if is_realtime else '否'}",
        f"是否允许作为正式选股依据：{'是' if formal_allowed else '否'}",
        "数据来源：实时数据" if is_realtime and formal_allowed else "数据来源：实时数据获取失败",
        "",
        "## ① 今日首选",
        "",
        *_first_pick_lines(result, repeat_watch_pool),
        "",
        "## ② 今日前三",
        "",
        "## 今日推荐3只主板股票",
        "",
    ]
    if not result.top3:
        lines.extend(["今日无入选股票。", ""])
    else:
        for index, item in enumerate(result.top3, start=1):
            lines.extend(_candidate_summary_lines(index, item, result.market.status))
    lines.extend(
        [
            "## ③ 今天为什么没有（如果没有）",
            "",
            _no_pick_reason(result, has_high_confidence),
            "",
            "## ④ 次日验证",
            "",
            *next_day_validation,
            "",
            "## ⑤ 今日市场概况",
            "",
            *_market_overview_lines(result, best_score),
            "",
            "## ⑥ 今日板块排行榜",
            "",
            *_sector_leaderboard_lines(result),
            "",
        ]
    )
    lines.extend(_repeat_watch_pool_lines(repeat_watch_pool))
    lines.extend(
        [
            "## ⑧ 今日所有候选股票（Top20）",
            "",
            *_top20_lines(result),
            "",
            "## ⑨ 每只股票评分明细",
            "",
            *_score_detail_lines(result),
            "",
            "## ⑩ 今日淘汰统计",
            "",
            *_elimination_stats_lines(result),
            "",
            "## ⑪ 历史胜率数据库",
            "",
            *performance_summary,
            "",
            "## ⑫ 数据来源验证",
            "",
            f"- 数据源名称：{data_source}",
            f"- 历史K线来源：{stats.get('history_source', '未知')}",
            f"- 历史K线成功股票数：{stats.get('history_success_count', '未知')}",
            f"- 历史K线不足股票数：{stats.get('history_insufficient_count', '未知')}",
            f"- 指标计算成功数：{stats.get('feature_valid_count', '未知')}",
            f"- 指标计算失败数：{stats.get('feature_invalid_count', '未知')}",
            f"- 数据日期：{actual_data_date.isoformat()}",
            f"- is_realtime={'true' if is_realtime else 'false'}",
            f"- formal_allowed={'true' if formal_allowed else 'false'}",
            f"- 报告用途：{'正式选股依据' if is_realtime and formal_allowed else '失败/降级说明，不作为正式选股依据'}",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _market_overview_lines(result: AkShareSelectionResult, best_score: float | None) -> list[str]:
    if not result.market.available:
        return [
            "大盘概况获取失败。",
            f"- 原因：{result.market.note}",
            f"- 通过硬过滤股票数量：{result.scored_count}",
            f"- 最高分：{best_score:.2f}" if best_score is not None else "- 最高分：无",
        ]
    data_date = result.market.data_date or result.trade_date
    lines = [
        f"- 统计口径：{result.market.scope}",
        f"- 数据来源：{result.market.source}",
        f"- 数据日期：{data_date.isoformat()}",
        f"- 全A股样本数：{result.market.sample_count}",
        f"- 全A股上涨家数：{result.market.up_count}",
        f"- 全A股下跌家数：{result.market.down_count}",
        f"- 全A股平盘家数：{result.market.flat_count}",
        f"- 全A股成交额：{result.market.total_amount / 1_000_000_000_000:.2f} 万亿元",
    ]
    if result.market.limit_stats_available:
        lines.extend(
            [
                f"- 涨停/跌停统计口径：{result.market.limit_scope}",
                f"- 涨跌停统计排除数量：{result.market.limit_excluded_count}",
                f"- 涨停家数：{result.market.limit_up_count}",
                f"- 跌停家数：{result.market.limit_down_count}",
            ]
        )
    else:
        lines.append("- 涨停/跌停统计：无法按不同涨跌幅限制精确计算，已隐藏。")
    lines.extend(
        [
            f"- 市场状态：{result.market.status}",
            f"- 市场评分：{result.market.score:.2f}/100",
            f"- 通过硬过滤股票数量：{result.scored_count}",
            f"- 最高分：{best_score:.2f}" if best_score is not None else "- 最高分：无",
        ]
    )
    return lines


def _candidate_summary_lines(index: int, item, market_status: str) -> list[str]:
    return [
        f"### {index}. {item.name} ({item.code})",
        f"- 所属板块：{item.sector}",
        f"- 最终评分：{item.score:.2f}",
        f"- 推荐理由：{'；'.join(item.reasons)}",
        f"- 买入区间：{item.buy_range}",
        f"- 止损位：{item.stop_loss:.2f}",
        f"- 风险等级：{_risk_level_for_candidate(item, market_status)}",
        "",
    ]


def _first_pick_lines(result: AkShareSelectionResult, repeat_watch_pool: list[dict]) -> list[str]:
    if not result.top3:
        return ["今日首选：暂无", "原因：今日无通过硬过滤的候选股票。"]
    repeat_by_code = {item["code"]: item for item in repeat_watch_pool}
    candidates = []
    for item in result.top3:
        repeat = repeat_by_code.get(item.code, {})
        list_count = int(repeat.get("list_count_5d", 1))
        continuous_days = int(repeat.get("continuous_days", 1))
        candidates.append((item, list_count, continuous_days))
    item, list_count, continuous_days = sorted(
        candidates,
        key=lambda row: (-row[1], -row[2], -row[0].score, result.top3.index(row[0]) + 1),
    )[0]
    if list_count >= 3:
        level = "强重点观察"
    elif list_count == 2:
        level = "重点观察"
    elif list_count == 1 and item == result.top3[0]:
        level = "短线观察"
    else:
        level = "普通观察"
    rank = result.top3.index(item) + 1
    top_ranked = result.top3[0]
    if rank == 1:
        decision_note = "今日首选同时也是今日评分第一名。"
    else:
        decision_note = (
            f"今日评分第一名是 {top_ranked.code} {top_ranked.name}，总评分 {top_ranked.score:.2f}；"
            f"但今日首选优先考虑最近5日重复上榜次数和连续上榜天数，"
            f"因此选择第 {rank} 名 {item.code} {item.name}。"
        )
    return [
        "决策规则：先比较最近5日上榜次数，再比较连续上榜天数，再比较今日总评分，最后比较今日排名；并列时选择今日总评分更高者。",
        f"股票代码：{item.code}",
        f"股票名称：{item.name}",
        f"推荐等级：{level}",
        f"推荐理由：最近5日上榜 {list_count} 次，连续上榜 {continuous_days} 天，今日排名第 {rank}，总评分 {item.score:.2f}。",
        f"本次选择说明：{decision_note}",
    ]


def _no_pick_reason(result: AkShareSelectionResult, has_high_confidence: bool) -> str:
    if not result.top3:
        stats = result.elimination_stats or {}
        failed = stats.get("hard_filter_failed", {}) if isinstance(stats, dict) else {}
        if failed:
            top_reason = sorted(failed.items(), key=lambda item: item[1], reverse=True)[0]
            return f"结论：今日无高确定性机会，建议空仓观察。今日没有最终候选。主要淘汰原因：{top_reason[0]}，剔除 {top_reason[1]} 只。"
        return "结论：今日无高确定性机会，建议空仓观察。今日没有最终候选。主要原因：数据不足或硬过滤后无股票通过。"
    if not has_high_confidence:
        return f"结论：今日无高确定性机会，建议空仓观察。今日有候选股票，但最高分 {result.top3[0].score:.2f} 未达到 75 分高确定性阈值，因此只输出观察，不输出必须买入。"
    return "今日存在高确定性候选，已输出今日首选和前三。"


def _sector_leaderboard_lines(result: AkShareSelectionResult) -> list[str]:
    if result.sector_rankings:
        lines = ["| 排名 | 板块 | 类型 | 涨跌幅 | 热度 | 是否主线 |", "| ---: | --- | --- | ---: | ---: | --- |"]
        for index, sector in enumerate(result.sector_rankings[:10], start=1):
            lines.append(
                f"| {index} | {sector.name} | {sector.sector_type} | {sector.pct_change:.2f}% | {sector.heat_score:.2f} | {'是' if sector.is_mainline else '否'} |"
            )
        return lines
    if not result.top20:
        return ["暂无板块数据。"]
    rows: dict[str, dict] = {}
    for item in result.top20:
        row = rows.setdefault(item.sector, {"count": 0, "score": 0.0, "best": 0.0})
        row["count"] += 1
        row["score"] += item.score
        row["best"] = max(row["best"], item.score)
    lines = ["| 排名 | 板块 | Top20入选数 | 平均评分 | 最高评分 |", "| ---: | --- | ---: | ---: | ---: |"]
    for index, (sector, row) in enumerate(
        sorted(rows.items(), key=lambda item: (-item[1]["count"], -item[1]["best"], item[0]))[:10],
        start=1,
    ):
        lines.append(f"| {index} | {sector} | {row['count']} | {row['score'] / row['count']:.2f} | {row['best']:.2f} |")
    return lines


def _top20_lines(result: AkShareSelectionResult) -> list[str]:
    lines = ["| 排名 | 代码 | 名称 | 板块 | 总评分 | 收盘价 | 换手率 | 成交额(亿) | 操作建议 |", "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    if not result.top20:
        lines.append("| - | 暂无 | 暂无 | - | - | - | - | - | 暂不操作 |")
        return lines
    for index, item in enumerate(result.top20, start=1):
        lines.append(
            f"| {index} | {item.code} | {item.name} | {item.sector} | {item.score:.2f} | {item.close:.2f} | {item.turnover_rate:.2f}% | {item.amount / 100_000_000:.2f} | {item.action} |"
        )
    return lines


def _score_detail_lines(result: AkShareSelectionResult) -> list[str]:
    lines = [
        "| 排名 | 股票 | MA20 | MA5/MA10 | 量能 | 突破 | 市值 | 板块热度 | 风险扣分 | 总分计算 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    if not result.top20:
        lines.append("| - | 暂无 | - | - | - | - | - | - | - | - |")
        return lines
    for index, item in enumerate(result.top20, start=1):
        breakdown = item.score_breakdown
        ma20 = float(breakdown.get("MA20评分", item.ma20_score))
        ma = float(breakdown.get("均线评分", item.ma_score))
        volume = float(breakdown.get("量能评分", item.volume_score))
        breakout = float(breakdown.get("突破评分", item.breakout_score))
        cap = float(breakdown.get("市值评分", item.market_cap_score))
        heat = float(breakdown.get("板块热度", item.sector_heat_bonus))
        risk = float(breakdown.get("风险扣分", item.risk_score))
        formula = f"{ma20:.1f}+{ma:.1f}+{volume:.1f}+{breakout:.1f}+{cap:.1f}+{heat:.1f}{risk:+.1f}={item.score:.1f}"
        lines.append(
            f"| {index} | {item.code} {item.name} | {ma20:.1f} | {ma:.1f} | {volume:.1f} | {breakout:.1f} | {cap:.1f} | {heat:.1f} | {risk:.1f} | {formula} |"
        )
    return lines


def _elimination_stats_lines(result: AkShareSelectionResult) -> list[str]:
    stats = result.elimination_stats or {}
    lines = [
        f"- 原始行情股票数：{stats.get('source_count', result.source_count)}",
        f"- 主板过滤后：{stats.get('main_board_count', result.main_board_count)}",
        f"- 进入评分池：{stats.get('scoring_universe_count', '未知')}",
        f"- 历史K线来源：{stats.get('history_source', '未知')}",
        f"- 历史K线请求股票数：{stats.get('history_request_count', '未知')}",
        f"- 历史K线成功股票数：{stats.get('history_success_count', '未知')}",
        f"- 历史K线不足股票数：{stats.get('history_insufficient_count', '未知')}",
        f"- 历史K线失败股票数：{stats.get('history_failure_count', '未知')}",
        f"- 指标计算成功：{stats.get('feature_valid_count', '未知')}",
        f"- 指标计算失败：{stats.get('feature_invalid_count', '未知')}",
        f"- 最终候选：{stats.get('final_count', result.scored_count)}",
        "",
        "| 指标计算失败原因 | 数量 |",
        "| --- | ---: |",
    ]
    feature_failed = stats.get("feature_invalid_reasons", {}) if isinstance(stats, dict) else {}
    if feature_failed:
        for reason, count in sorted(feature_failed.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| 暂无 | 0 |")
    lines.extend(
        [
            "",
            "| 淘汰条件 | 数量 |",
            "| --- | ---: |",
        ]
    )
    failed = stats.get("hard_filter_failed", {}) if isinstance(stats, dict) else {}
    if not failed:
        lines.append("| 暂无 | 0 |")
        return lines
    for reason, count in sorted(failed.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| {reason} | {count} |")
    return lines


def _repeat_watch_pool_lines(repeat_watch_pool: list[dict]) -> list[str]:
    lines = [
        "## ⑦ 最近5日重复上榜（按次数排序）",
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
        summary_path = update_performance_summary_database(history_path, as_of_date=run_date)
        repeat_watch_pool = build_repeat_watch_pool(history_path, as_of_date=run_date)
        pd.DataFrame(repeat_watch_pool).to_csv(args.output_dir / "repeat-watch-pool.csv", index=False, encoding="utf-8-sig")
        today_stock = render_today_stock(
            result,
            repeat_watch_pool=repeat_watch_pool,
            next_day_validation=next_day_validation_lines(history_path, as_of_date=run_date),
            performance_summary=performance_summary_lines(summary_path),
        )
        today_stock_path.write_text(today_stock, encoding="utf-8")
        weekly_review_path = generate_weekly_review(as_of_date=run_date)
        print(report)
        print(f"Top10 CSV: {pool_path}")
        print(f"Markdown report: {report_path}")
        print(f"Today summary: {today_stock_path}")
        print(f"Selection history: {history_path}")
        print(f"Performance summary: {summary_path}")
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
