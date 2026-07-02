from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


INDEX_SYMBOLS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    "北证50": "bj899050",
}

STYLE_HISTORY_COLUMNS = [
    "日期",
    "今日主导风格",
    "最近5日主导风格",
    "最近20日主导风格",
    "是否高低切",
    "科技成长强度",
    "创业板强度",
    "传统低位强度",
    "风格轮动强度",
    "次日验证结果",
]

TECH_KEYWORDS = (
    "电子",
    "半导体",
    "通信",
    "计算机",
    "软件",
    "人工智能",
    "AI",
    "机器人",
    "光模块",
    "消费电子",
    "芯片",
    "算力",
    "云计算",
    "数据",
    "传媒",
)

TRADITIONAL_KEYWORDS = (
    "银行",
    "地产",
    "房地产",
    "钢铁",
    "煤炭",
    "建筑",
    "基建",
    "家电",
    "食品饮料",
    "石油",
    "有色",
    "化工",
    "资源",
    "中字头",
    "保险",
    "证券",
    "公用事业",
)


@dataclass(frozen=True)
class StyleGroupStats:
    name: str
    up_count: int = 0
    down_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    average_pct: float = 0.0
    amount_share: float = 0.0
    fund_strength: float = 0.0
    trend_5d: float = 0.0
    trend_10d: float = 0.0
    trend_20d: float = 0.0
    sample_count: int = 0


@dataclass(frozen=True)
class MarketStyleSnapshot:
    trade_date: date
    index_returns: dict[str, dict[str, float]]
    index_rankings: dict[str, list[str]]
    leading_index: str
    today_style: str
    dominant_5d: str
    dominant_20d: str
    high_low_switch: bool
    tech_retreat: bool
    growth_board_recovering: bool
    traditional_short_rebound: bool
    rotation_fast: bool
    action_advice: str
    style_sentence: str
    group_stats: dict[str, StyleGroupStats]
    tech_strength: float
    growth_board_strength: float
    traditional_strength: float
    rotation_strength: float


def analyze_market_style(
    *,
    trade_date: date,
    fetcher,
    market_spot: pd.DataFrame,
    feature_rows: Iterable[dict] = (),
) -> MarketStyleSnapshot:
    frame = _normalize_spot(market_spot)
    feature_frame = pd.DataFrame(list(feature_rows))
    index_returns = _index_returns(fetcher, trade_date)
    index_rankings = {
        f"{window}日": _rank_indices(index_returns, f"{window}d")
        for window in (5, 10, 20, 60)
    }
    leading_index = index_rankings.get("5日", ["未知"])[0] if index_rankings.get("5日") else "未知"
    group_stats = {
        name: _group_stats(name, _group_mask(frame, name), frame, feature_frame)
        for name in ("科技成长股", "创业板/科创板股票", "传统低位权重股", "高位强势股", "低位补涨股")
    }
    today_style = _dominant_style(group_stats, "average_pct")
    dominant_5d = _dominant_style(group_stats, "trend_5d")
    dominant_20d = _dominant_style(group_stats, "trend_20d")
    tech = group_stats["科技成长股"]
    traditional = group_stats["传统低位权重股"]
    growth_board = group_stats["创业板/科创板股票"]
    tech_strength = _style_strength(tech)
    traditional_strength = _style_strength(traditional)
    growth_board_strength = _style_strength(growth_board)
    high_low_switch = tech.trend_5d + 1.5 < traditional.trend_5d and traditional.amount_share > tech.amount_share * 0.8
    tech_retreat = tech.trend_5d < -1.0 and tech.average_pct < traditional.average_pct - 0.8
    growth_board_recovering = _index_value(index_returns, "创业板指", "5d") > _index_value(index_returns, "上证指数", "5d") and _index_value(index_returns, "科创50", "5d") > _index_value(index_returns, "上证指数", "5d")
    traditional_short_rebound = traditional.trend_5d > tech.trend_5d + 1.0 and traditional.trend_20d <= tech.trend_20d + 0.5
    rotation_strength = _rotation_strength(group_stats)
    rotation_fast = rotation_strength >= 65.0
    style_sentence = _style_sentence(
        high_low_switch=high_low_switch,
        tech_retreat=tech_retreat,
        growth_board_recovering=growth_board_recovering,
        traditional_short_rebound=traditional_short_rebound,
        rotation_fast=rotation_fast,
        today_style=today_style,
    )
    return MarketStyleSnapshot(
        trade_date=trade_date,
        index_returns=index_returns,
        index_rankings=index_rankings,
        leading_index=leading_index,
        today_style=today_style,
        dominant_5d=dominant_5d,
        dominant_20d=dominant_20d,
        high_low_switch=high_low_switch,
        tech_retreat=tech_retreat,
        growth_board_recovering=growth_board_recovering,
        traditional_short_rebound=traditional_short_rebound,
        rotation_fast=rotation_fast,
        action_advice=_action_advice(rotation_fast, high_low_switch, tech_retreat, growth_board_recovering),
        style_sentence=style_sentence,
        group_stats=group_stats,
        tech_strength=tech_strength,
        growth_board_strength=growth_board_strength,
        traditional_strength=traditional_strength,
        rotation_strength=rotation_strength,
    )


def market_style_score_adjustment(snapshot: MarketStyleSnapshot | None, *, code: str, sector: str, score: float) -> tuple[float, str]:
    if snapshot is None:
        return 0.0, "无风格数据"
    group = classify_stock(code=code, sector=sector, score=score)
    adjustment = 0.0
    reasons = []
    if snapshot.tech_retreat and group == "科技成长股" and score >= 70:
        adjustment -= 4.0
        reasons.append("科技成长退潮，降低科技追高分")
    if snapshot.rotation_fast and score >= 70:
        adjustment -= 3.0
        reasons.append("快速轮动，降低追高等级")
    if snapshot.traditional_short_rebound and group == "传统低位权重股":
        adjustment -= 2.0
        reasons.append("传统低位疑似短线补涨，避免盲目推荐")
    if snapshot.dominant_5d == group and snapshot.dominant_20d == group:
        adjustment += 3.0
        reasons.append(f"{group}连续占优，提高风格顺势分")
    elif snapshot.dominant_5d == group:
        adjustment += 1.5
        reasons.append(f"{group}短线占优，小幅加分")
    if group == "科技成长股" and snapshot.dominant_20d == "科技成长股" and not snapshot.tech_retreat:
        adjustment += 1.0
        reasons.append("科技成长中期仍强，保留候选")
    return adjustment, "；".join(reasons) if reasons else "风格中性"


def update_market_style_history(
    snapshot: MarketStyleSnapshot | None,
    *,
    history_path: Path | str = Path("history/market_style_history.csv"),
) -> Path:
    target = Path(history_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        history = pd.read_csv(target)
    else:
        history = pd.DataFrame(columns=STYLE_HISTORY_COLUMNS)
    if snapshot is None:
        return target
    row = {
        "日期": snapshot.trade_date.isoformat(),
        "今日主导风格": snapshot.today_style,
        "最近5日主导风格": snapshot.dominant_5d,
        "最近20日主导风格": snapshot.dominant_20d,
        "是否高低切": "是" if snapshot.high_low_switch else "否",
        "科技成长强度": round(snapshot.tech_strength, 2),
        "创业板强度": round(snapshot.growth_board_strength, 2),
        "传统低位强度": round(snapshot.traditional_strength, 2),
        "风格轮动强度": round(snapshot.rotation_strength, 2),
        "次日验证结果": "",
    }
    if "日期" in history:
        history = history[history["日期"].astype(str) != row["日期"]].copy()
    row_frame = pd.DataFrame([row])
    history = row_frame if history.empty else pd.concat([history, row_frame], ignore_index=True)
    history = history[STYLE_HISTORY_COLUMNS]
    history.to_csv(target, index=False, encoding="utf-8-sig")
    return target


def classify_stock(*, code: str, sector: str, score: float = 0.0) -> str:
    normalized = str(code).zfill(6)
    sector_text = str(sector)
    if normalized.startswith(("300", "301", "688", "689")):
        return "创业板/科创板股票"
    if any(keyword in sector_text for keyword in TECH_KEYWORDS):
        return "科技成长股"
    if any(keyword in sector_text for keyword in TRADITIONAL_KEYWORDS):
        return "传统低位权重股"
    if score >= 75:
        return "高位强势股"
    return "低位补涨股"


def _normalize_spot(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["代码", "名称", "所属板块", "涨跌幅", "成交额", "涨停标记", "跌停标记"])
    normalized = frame.copy()
    for column in ("代码", "名称", "所属板块"):
        if column not in normalized:
            normalized[column] = ""
    for column in ("涨跌幅", "成交额", "流通市值", "涨停标记", "跌停标记"):
        if column not in normalized:
            normalized[column] = 0.0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)
    normalized["代码"] = normalized["代码"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(normalized["代码"].astype(str)).str.zfill(6)
    return normalized


def _index_returns(fetcher, trade_date: date) -> dict[str, dict[str, float]]:
    rows = {}
    for name, symbol in INDEX_SYMBOLS.items():
        rows[name] = {}
        try:
            history = fetcher.index_history(symbol, trade_date, days=90)
            close = pd.to_numeric(history["close"], errors="coerce").dropna().reset_index(drop=True)
        except Exception:
            close = pd.Series(dtype=float)
        for window in (1, 5, 10, 20, 60):
            rows[name][f"{window}d"] = _window_return(close, window)
    return rows


def _window_return(close: pd.Series, window: int) -> float:
    if len(close) <= window:
        return 0.0
    previous = float(close.iloc[-window - 1])
    latest = float(close.iloc[-1])
    return (latest / previous - 1) * 100 if previous else 0.0


def _rank_indices(index_returns: dict[str, dict[str, float]], key: str) -> list[str]:
    return [
        name
        for name, _ in sorted(index_returns.items(), key=lambda item: item[1].get(key, 0.0), reverse=True)
    ]


def _index_value(index_returns: dict[str, dict[str, float]], name: str, key: str) -> float:
    return float(index_returns.get(name, {}).get(key, 0.0))


def _group_mask(frame: pd.DataFrame, group_name: str) -> pd.Series:
    codes = frame["代码"].astype(str).str.zfill(6)
    sector = frame["所属板块"].astype(str)
    if group_name == "创业板/科创板股票":
        return codes.str.startswith(("300", "301", "688", "689"))
    if group_name == "科技成长股":
        return sector.map(lambda value: any(keyword in value for keyword in TECH_KEYWORDS))
    if group_name == "传统低位权重股":
        return sector.map(lambda value: any(keyword in value for keyword in TRADITIONAL_KEYWORDS))
    if group_name == "高位强势股":
        return pd.Series(False, index=frame.index)
    if group_name == "低位补涨股":
        return pd.Series(False, index=frame.index)
    return pd.Series(False, index=frame.index)


def _group_stats(name: str, mask: pd.Series, frame: pd.DataFrame, feature_frame: pd.DataFrame) -> StyleGroupStats:
    if name in {"高位强势股", "低位补涨股"} and not feature_frame.empty:
        subset_features = feature_frame[feature_frame["style_group"] == name].copy()
        codes = set(subset_features["code"].astype(str).str.zfill(6))
        subset = frame[frame["代码"].isin(codes)].copy()
    else:
        subset = frame[mask].copy()
        subset_features = _features_for_codes(feature_frame, subset["代码"]) if not feature_frame.empty else pd.DataFrame()
    if subset.empty:
        return StyleGroupStats(name=name)
    pct = pd.to_numeric(subset["涨跌幅"], errors="coerce").fillna(0.0)
    amount = pd.to_numeric(subset["成交额"], errors="coerce").fillna(0.0)
    total_amount = pd.to_numeric(frame["成交额"], errors="coerce").fillna(0.0).sum()
    limit_up = pd.to_numeric(subset.get("涨停标记", pd.Series(0.0, index=subset.index)), errors="coerce").fillna(0.0)
    limit_down = pd.to_numeric(subset.get("跌停标记", pd.Series(0.0, index=subset.index)), errors="coerce").fillna(0.0)
    trend_5d = _feature_mean(subset_features, "return_5d")
    trend_10d = _feature_mean(subset_features, "return_10d")
    trend_20d = _feature_mean(subset_features, "return_20d")
    return StyleGroupStats(
        name=name,
        up_count=int((pct > 0).sum()),
        down_count=int((pct < 0).sum()),
        limit_up_count=int((limit_up == 1).sum()),
        limit_down_count=int((limit_down == 1).sum()),
        average_pct=float(pct.mean()) if not pct.empty else 0.0,
        amount_share=float(amount.sum() / total_amount * 100) if total_amount else 0.0,
        fund_strength=float((pct.mean() if not pct.empty else 0.0) * 10 + (amount.sum() / total_amount * 100 if total_amount else 0.0)),
        trend_5d=trend_5d,
        trend_10d=trend_10d,
        trend_20d=trend_20d,
        sample_count=len(subset),
    )


def _features_for_codes(feature_frame: pd.DataFrame, codes: pd.Series) -> pd.DataFrame:
    wanted = set(codes.astype(str).str.zfill(6))
    if "code" not in feature_frame:
        return pd.DataFrame()
    return feature_frame[feature_frame["code"].astype(str).str.zfill(6).isin(wanted)].copy()


def _feature_mean(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean() * 100) if not values.empty else 0.0


def _dominant_style(group_stats: dict[str, StyleGroupStats], attr: str) -> str:
    eligible = [item for item in group_stats.values() if item.sample_count > 0]
    if not eligible:
        return "暂无明确风格"
    return max(eligible, key=lambda item: getattr(item, attr)).name


def _style_strength(stats: StyleGroupStats) -> float:
    breadth = (stats.up_count / stats.sample_count * 100) if stats.sample_count else 0.0
    return max(0.0, min(100.0, breadth * 0.45 + max(stats.trend_5d + 10, 0) * 2.0 + stats.amount_share * 0.35))


def _rotation_strength(group_stats: dict[str, StyleGroupStats]) -> float:
    active = [item for item in group_stats.values() if item.sample_count > 0]
    if len(active) < 2:
        return 0.0
    today_rank = [item.name for item in sorted(active, key=lambda item: item.average_pct, reverse=True)]
    five_rank = [item.name for item in sorted(active, key=lambda item: item.trend_5d, reverse=True)]
    mismatch = sum(1 for index, name in enumerate(today_rank) if index >= len(five_rank) or five_rank[index] != name)
    spread = max(item.average_pct for item in active) - min(item.average_pct for item in active)
    return max(0.0, min(100.0, mismatch / len(active) * 60 + min(spread * 8, 40)))


def _style_sentence(
    *,
    high_low_switch: bool,
    tech_retreat: bool,
    growth_board_recovering: bool,
    traditional_short_rebound: bool,
    rotation_fast: bool,
    today_style: str,
) -> str:
    if rotation_fast:
        state = "风格快速切换"
    elif high_low_switch:
        state = "高低切换"
    elif growth_board_recovering:
        state = "成长回流"
    elif traditional_short_rebound or today_style == "传统低位权重股":
        state = "传统低位占优"
    elif tech_retreat:
        state = "科技成长退潮"
    else:
        state = f"{today_style}占优"
    return f"当前市场不是单边主线，而是{state}。"


def _action_advice(rotation_fast: bool, high_low_switch: bool, tech_retreat: bool, growth_board_recovering: bool) -> str:
    if rotation_fast:
        return "只观察，降低追高仓位"
    if high_low_switch:
        return "低吸优先，避免高位科技追涨"
    if tech_retreat and not growth_board_recovering:
        return "空仓或只观察"
    if growth_board_recovering:
        return "可低吸成长，控制追高"
    return "精选低吸，不盲目追涨"
