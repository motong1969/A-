from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stock_selector.akshare_engine import AkShareCandidate, AkShareSelectionResult


HISTORY_COLUMNS = [
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
]

RETURN_COLUMN_TO_OFFSET = {
    "next_day_return": 1,
    "return_3d": 3,
    "return_5d": 5,
    "return_10d": 10,
}


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
        for column in ("score", "close_price", *RETURN_COLUMN_TO_OFFSET):
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
                "next_day_return": pd.NA,
                "return_3d": pd.NA,
                "return_5d": pd.NA,
                "return_10d": pd.NA,
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
    pending_mask = updated[list(RETURN_COLUMN_TO_OFFSET)].isna().any(axis=1)
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
