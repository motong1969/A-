from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stock_selector.akshare_engine import AkShareCandidate, AkShareSelectionResult


FACTOR_COLUMNS = [
    "ma20_score",
    "ma_score",
    "volume_score",
    "breakout_score",
    "risk_score",
    "market_cap_score",
    "sector_heat_bonus",
]

HISTORY_COLUMNS = [
    "date",
    "rank",
    "code",
    "name",
    "sector",
    "score",
    "close_price",
    *FACTOR_COLUMNS,
    "next_day_return",
    "return_3d",
    "return_5d",
    "return_10d",
    "max_gain_5d",
    "max_drawdown_5d",
]

RETURN_COLUMN_TO_OFFSET = {
    "next_day_return": 1,
    "return_3d": 3,
    "return_5d": 5,
    "return_10d": 10,
}

PERFORMANCE_COLUMNS = [
    *RETURN_COLUMN_TO_OFFSET,
    "max_gain_5d",
    "max_drawdown_5d",
]


def update_selection_history(
    result: AkShareSelectionResult,
    *,
    fetcher,
    history_path: Path | str = Path("history/selection_history.csv"),
    as_of_date: date | None = None,
) -> Path:
    history_file = Path(history_path)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history(history_file)
    latest_date = as_of_date or result.trade_date
    history = _upsert_daily_selection(history, result.trade_date, result.validation_top20)
    history = _backfill_returns(history, fetcher=fetcher, as_of_date=latest_date)
    history.to_csv(history_file, index=False, encoding="utf-8-sig")
    return history_file


def generate_backtest_report(
    history_path: Path | str = Path("history/selection_history.csv"),
    *,
    output_path: Path | str | None = None,
) -> str:
    history = _load_history(Path(history_path))
    if history.empty:
        report = "# 历史验证报告\n\n暂无历史记录。\n"
    else:
        report = _render_backtest_report(history)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8")
    return report


def generate_weekly_review(
    history_path: Path | str = Path("history/selection_history.csv"),
    *,
    output_dir: Path | str = Path("reports"),
    as_of_date: date | None = None,
) -> Path | None:
    review_date = as_of_date or date.today()
    if review_date.weekday() != 4:
        return None
    history = _load_history(Path(history_path))
    target = Path(output_dir) / f"weekly-review-{review_date.isoformat()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_render_weekly_review(history, review_date), encoding="utf-8")
    return target


def _load_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    frame = pd.read_csv(path)
    for column in HISTORY_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[HISTORY_COLUMNS].copy()
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce").astype("Int64")
        for column in ("score", "close_price", *FACTOR_COLUMNS, *PERFORMANCE_COLUMNS):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["code"] = frame["code"].astype(str).str.zfill(6)
        frame = frame.sort_values(["date", "rank"], ascending=[False, True]).reset_index(drop=True)
    return frame


def _upsert_daily_selection(
    history: pd.DataFrame,
    trade_date: date,
    candidates: list[AkShareCandidate],
) -> pd.DataFrame:
    rows = []
    for rank, item in enumerate(candidates, start=1):
        rows.append(
            {
                "date": trade_date,
                "rank": rank,
                "code": item.code,
                "name": item.name,
                "sector": item.sector,
                "score": round(item.score, 2),
                "close_price": round(item.close, 4),
                "ma20_score": round(item.ma20_score, 4),
                "ma_score": round(item.ma_score, 4),
                "volume_score": round(item.volume_score, 4),
                "breakout_score": round(item.breakout_score, 4),
                "risk_score": round(item.risk_score, 4),
                "market_cap_score": round(item.market_cap_score, 4),
                "sector_heat_bonus": round(item.sector_heat_bonus, 4),
                "next_day_return": pd.NA,
                "return_3d": pd.NA,
                "return_5d": pd.NA,
                "return_10d": pd.NA,
                "max_gain_5d": pd.NA,
                "max_drawdown_5d": pd.NA,
            }
        )
    current = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    if history.empty:
        return current
    preserved = history[history["date"] != trade_date].copy()
    merged = pd.concat([preserved, current], ignore_index=True)
    return merged.sort_values(["date", "rank"], ascending=[False, True]).reset_index(drop=True)


def _backfill_returns(history: pd.DataFrame, *, fetcher, as_of_date: date) -> pd.DataFrame:
    if history.empty:
        return history
    updated = history.copy()
    pending_mask = updated[PERFORMANCE_COLUMNS].isna().any(axis=1)
    pending = updated[pending_mask]
    if pending.empty:
        return updated
    for code in pending["code"].dropna().astype(str).str.zfill(6).unique():
        code_mask = pending["code"].astype(str).str.zfill(6) == code
        code_rows = pending[code_mask]
        oldest_date = min(code_rows["date"])
        if pd.isna(oldest_date):
            continue
        try:
            history_frame = fetcher.stock_history(code, as_of_date, days=40)
        except Exception:
            continue
        if history_frame.empty:
            continue
        history_frame = history_frame.copy()
        history_frame["trade_date"] = pd.to_datetime(history_frame["trade_date"], errors="coerce").dt.date
        history_frame["close"] = pd.to_numeric(history_frame["close"], errors="coerce")
        history_frame = history_frame.dropna(subset=["trade_date", "close"])
        history_frame = history_frame[history_frame["trade_date"] >= oldest_date].sort_values("trade_date").reset_index(drop=True)
        if history_frame.empty:
            continue
        trade_dates = history_frame["trade_date"].tolist()
        close_map = {row.trade_date: float(row.close) for row in history_frame.itertuples()}
        future_dates_map = {
            trade_day: [candidate for candidate in trade_dates if candidate > trade_day]
            for trade_day in set(code_rows["date"])
        }
        for row_index in updated.index[updated["code"].astype(str).str.zfill(6) == code]:
            trade_day = updated.at[row_index, "date"]
            base_close = float(updated.at[row_index, "close_price"]) if pd.notna(updated.at[row_index, "close_price"]) else 0.0
            if not trade_day or base_close <= 0:
                continue
            future_dates = future_dates_map.get(trade_day, [])
            for column, offset in RETURN_COLUMN_TO_OFFSET.items():
                if pd.notna(updated.at[row_index, column]):
                    continue
                if len(future_dates) < offset:
                    continue
                future_close = close_map.get(future_dates[offset - 1])
                if future_close is None:
                    continue
                updated.at[row_index, column] = round(future_close / base_close - 1, 6)
            if len(future_dates) >= 5:
                five_day_closes = [close_map[trade_date] for trade_date in future_dates[:5] if trade_date in close_map]
                if len(five_day_closes) == 5:
                    if pd.isna(updated.at[row_index, "max_gain_5d"]):
                        updated.at[row_index, "max_gain_5d"] = round(max(five_day_closes) / base_close - 1, 6)
                    if pd.isna(updated.at[row_index, "max_drawdown_5d"]):
                        updated.at[row_index, "max_drawdown_5d"] = round(min(five_day_closes) / base_close - 1, 6)
    return updated.sort_values(["date", "rank"], ascending=[False, True]).reset_index(drop=True)


def _render_backtest_report(history: pd.DataFrame) -> str:
    lines = ["# 历史验证报告", ""]
    lines.extend(_rank_section(history))
    lines.append("")
    lines.extend(_top10_section(history))
    lines.append("")
    lines.extend(_win_rate_section(history))
    return "\n".join(lines).rstrip() + "\n"


def _rank_section(history: pd.DataFrame) -> list[str]:
    lines = []
    rank_labels = {1: "第一名平均收益", 2: "第二名平均收益", 3: "第三名平均收益"}
    for rank in (1, 2, 3):
        subset = history[history["rank"] == rank]
        lines.append(f"## {rank_labels[rank]}")
        lines.append("")
        lines.extend(_format_return_stats(subset))
        lines.append("")
    return lines[:-1]


def _top10_section(history: pd.DataFrame) -> list[str]:
    lines = ["## 前10名平均收益", ""]
    subset = history[history["rank"].between(1, 10, inclusive="both")]
    lines.extend(_format_return_stats(subset))
    return lines


def _win_rate_section(history: pd.DataFrame) -> list[str]:
    lines = ["## 胜率统计", ""]
    subsets = {
        "第1名": history[history["rank"] == 1],
        "第2名": history[history["rank"] == 2],
        "第3名": history[history["rank"] == 3],
        "前10名": history[history["rank"].between(1, 10, inclusive="both")],
    }
    for label, subset in subsets.items():
        lines.append(f"### {label}")
        for column in RETURN_COLUMN_TO_OFFSET:
            series = pd.to_numeric(subset[column], errors="coerce").dropna()
            if series.empty:
                lines.append(f"- {column}: 暂无数据")
                continue
            win_rate = (series > 0).mean()
            lines.append(f"- {column}: 胜率 {win_rate:.2%}，样本 {len(series)}")
        lines.append("")
    return lines[:-1]


def _format_return_stats(frame: pd.DataFrame) -> list[str]:
    lines = []
    for column in RETURN_COLUMN_TO_OFFSET:
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            lines.append(f"- {column}: 暂无数据")
            continue
        lines.append(f"- {column}: 平均收益 {series.mean():.2%}，样本 {len(series)}")
    return lines


def _render_weekly_review(history: pd.DataFrame, review_date: date) -> str:
    week_start = review_date - pd.Timedelta(days=review_date.weekday())
    week_start = week_start.date() if hasattr(week_start, "date") else week_start
    weekly = history[(history["date"] >= week_start) & (history["date"] <= review_date)].copy()
    top3 = weekly[weekly["rank"].between(1, 3, inclusive="both")].sort_values(["date", "rank"])

    lines = [f"# 一周验证总结: {review_date.isoformat()}", ""]
    lines.extend(_weekly_top3_lines(top3))
    lines.append("")
    lines.extend(_weekly_performance_lines(top3))
    lines.append("")
    lines.extend(_weekly_average_lines(top3))
    lines.append("")
    lines.extend(_weekly_win_rate_lines(top3))
    lines.append("")
    lines.extend(_weekly_drawdown_lines(top3))
    lines.append("")
    effective_factor = _most_effective_factor(top3)
    lines.extend(_weekly_factor_lines(effective_factor))
    lines.append("")
    lines.extend(_weekly_false_strength_lines(top3))
    lines.append("")
    lines.extend(_weekly_conclusion_lines(top3, effective_factor))
    return "\n".join(lines).rstrip() + "\n"


def _weekly_top3_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 本周每天前三名", ""]
    if top3.empty:
        return lines + ["暂无本周前三名记录。"]
    for row in top3.itertuples():
        lines.append(
            f"- {row.date} 第{int(row.rank)}名: {row.code} {row.name}，"
            f"板块 {row.sector}，评分 {float(row.score):.2f}"
        )
    return lines


def _weekly_performance_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 每只股票后续表现", ""]
    if top3.empty:
        return lines + ["暂无可验证股票。"]
    for row in top3.itertuples():
        lines.append(
            f"- {row.date} 第{int(row.rank)}名 {row.code} {row.name}: "
            f"次日 {_format_pct(row.next_day_return)}，"
            f"3日 {_format_pct(row.return_3d)}，"
            f"5日 {_format_pct(row.return_5d)}，"
            f"最大涨幅 {_format_pct(row.max_gain_5d)}，"
            f"最大回撤 {_format_pct(row.max_drawdown_5d)}"
        )
    return lines


def _weekly_average_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 前三名平均收益", ""]
    for column, label in [
        ("next_day_return", "次日平均收益"),
        ("return_3d", "3日平均收益"),
        ("return_5d", "5日平均收益"),
    ]:
        series = pd.to_numeric(top3[column], errors="coerce").dropna()
        if series.empty:
            lines.append(f"- {label}: 暂无完整数据")
            continue
        lines.append(f"- {label}: {series.mean():.2%}，样本 {len(series)}")
    return lines


def _weekly_win_rate_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 胜率", ""]
    for column, label in [
        ("next_day_return", "次日"),
        ("return_3d", "3日"),
        ("return_5d", "5日"),
    ]:
        series = pd.to_numeric(top3[column], errors="coerce").dropna()
        if series.empty:
            lines.append(f"- {label}: 暂无完整数据")
            continue
        lines.append(f"- {label}: {(series > 0).mean():.2%}，样本 {len(series)}")
    return lines


def _weekly_drawdown_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 最大回撤", ""]
    series = pd.to_numeric(top3["max_drawdown_5d"], errors="coerce").dropna()
    if series.empty:
        return lines + ["暂无完整5日回撤数据。"]
    worst_index = series.idxmin()
    worst = top3.loc[worst_index]
    lines.append(
        f"- 本周前三名样本最大回撤: {series.min():.2%}，"
        f"来自 {worst['date']} 第{int(worst['rank'])}名 {worst['code']} {worst['name']}"
    )
    return lines


def _weekly_factor_lines(effective_factor: tuple[str, float] | None) -> list[str]:
    lines = ["## 哪个评分因子最有效", ""]
    if effective_factor is None:
        return lines + ["样本不足，暂不能判断单个评分因子的有效性。"]
    factor, correlation = effective_factor
    lines.append(f"- 当前样本中 `{factor}` 与5日收益相关性最高，相关系数 {correlation:.3f}。")
    return lines


def _weekly_false_strength_lines(top3: pd.DataFrame) -> list[str]:
    lines = ["## 假强势股票", ""]
    if top3.empty:
        return lines + ["暂无。"]
    return_5d = pd.to_numeric(top3["return_5d"], errors="coerce")
    drawdown = pd.to_numeric(top3["max_drawdown_5d"], errors="coerce")
    false_strength = top3[(return_5d < 0) | (drawdown <= -0.05)]
    if false_strength.empty:
        return lines + ["暂无明确假强势样本。"]
    for row in false_strength.itertuples():
        lines.append(
            f"- {row.date} 第{int(row.rank)}名 {row.code} {row.name}: "
            f"评分 {float(row.score):.2f}，5日收益 {_format_pct(row.return_5d)}，"
            f"最大回撤 {_format_pct(row.max_drawdown_5d)}"
        )
    return lines


def _weekly_conclusion_lines(top3: pd.DataFrame, effective_factor: tuple[str, float] | None) -> list[str]:
    lines = ["## 最终结论", ""]
    five_day = pd.to_numeric(top3["return_5d"], errors="coerce").dropna()
    if len(five_day) < 3:
        conclusion = "当前5日验证样本不足，评分模型可以继续运行观察，暂不建议调整。"
    elif five_day.mean() > 0 and (five_day > 0).mean() >= 0.5 and effective_factor is not None:
        conclusion = "当前评分模型值得继续使用，暂不需要调整。"
    else:
        conclusion = "当前评分模型仍可运行，但需要重点复核因子权重和风险扣分。"
    lines.append(conclusion)
    return lines


def _most_effective_factor(top3: pd.DataFrame) -> tuple[str, float] | None:
    scored = top3.copy()
    scored["return_5d"] = pd.to_numeric(scored["return_5d"], errors="coerce")
    best: tuple[str, float] | None = None
    for factor in FACTOR_COLUMNS:
        if factor not in scored.columns:
            continue
        factor_values = pd.to_numeric(scored[factor], errors="coerce")
        pairs = pd.DataFrame({"factor": factor_values, "return_5d": scored["return_5d"]}).dropna()
        if len(pairs) < 2:
            continue
        correlation = pairs["factor"].corr(pairs["return_5d"])
        if pd.isna(correlation):
            continue
        if best is None or correlation > best[1]:
            best = (factor, float(correlation))
    return best


def _format_pct(value) -> str:
    if pd.isna(value):
        return "暂无数据"
    return f"{float(value):.2%}"
