from __future__ import annotations

from dataclasses import dataclass, field
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
    "主风格",
    "副风格",
    "置信度",
    "持续天数",
    "高低切状态",
    "成长指数",
    "低位指数",
    "轮动指数",
    "资金集中度",
    "热点数量",
    "热点持续性",
    "预测风格",
    "科技继续概率",
    "高低切概率",
    "传统低位概率",
    "其它概率",
    "次日验证结果",
    "预测是否正确",
    "最近30天预测正确率",
]

LEGACY_COLUMN_MAP = {
    "今日主导风格": "主风格",
    "最近5日主导风格": "副风格",
    "是否高低切": "高低切状态",
    "科技成长强度": "成长指数",
    "传统低位强度": "低位指数",
    "风格轮动强度": "轮动指数",
}

TECH_KEYWORDS = (
    "电子",
    "半导体",
    "通信",
    "计算机",
    "软件",
    "人工智能",
    "AI",
    "AIGC",
    "PCB",
    "机器人",
    "光模块",
    "CPO",
    "消费电子",
    "芯片",
    "算力",
    "服务器",
    "云计算",
    "数据",
    "传媒",
    "铜连接",
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
    "电力",
)

TOPIC_KEYWORDS = {
    "AI": ("人工智能", "AI", "AIGC", "算力", "服务器", "数据"),
    "PCB": ("PCB", "印制电路", "覆铜板"),
    "半导体": ("半导体", "芯片", "集成电路"),
    "光模块": ("光模块", "CPO", "光通信"),
    "机器人": ("机器人", "减速器", "工业母机"),
    "消费电子": ("消费电子", "苹果", "MR", "电子"),
    "铜连接": ("铜连接", "高速连接", "连接器"),
    "创业板": ("创业板",),
    "银行": ("银行",),
    "煤炭": ("煤炭",),
    "地产": ("地产", "房地产"),
    "中字头": ("中字头", "央企"),
}


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
class CapitalDirection:
    name: str
    strength: float
    stars: str
    pct_change: float = 0.0
    main_net_inflow: float = 0.0
    source: str = "行情"


@dataclass(frozen=True)
class StylePrediction:
    probabilities: dict[str, float]
    predicted_style: str
    basis: str
    sample_count: int = 0


@dataclass(frozen=True)
class MarketStyleSnapshot:
    trade_date: date
    index_returns: dict[str, dict[str, float]]
    index_rankings: dict[str, list[str]]
    leading_index: str
    today_style: str
    secondary_style: str
    dominant_5d: str
    dominant_20d: str
    confidence: float
    style_scores: dict[str, float]
    duration_days: int
    consecutive_counts: dict[str, int]
    style_state: str
    high_low_state: str
    high_low_switch: bool
    tech_retreat: bool
    growth_board_recovering: bool
    traditional_short_rebound: bool
    rotation_fast: bool
    action_advice: str
    recommendations: list[str]
    style_sentence: str
    explanation: str
    group_stats: dict[str, StyleGroupStats]
    capital_directions: list[CapitalDirection] = field(default_factory=list)
    weak_directions: list[CapitalDirection] = field(default_factory=list)
    prediction: StylePrediction | None = None
    validation_summary: str = "暂无已完成的风格验证数据。"
    rolling_accuracy_30d: float = 0.0
    tech_strength: float = 0.0
    growth_board_strength: float = 0.0
    traditional_strength: float = 0.0
    rotation_strength: float = 0.0
    capital_concentration: float = 0.0
    hot_direction_count: int = 0
    hot_persistence: float = 0.0
    score_cap: float | None = None


def analyze_market_style(
    *,
    trade_date: date,
    fetcher,
    market_spot: pd.DataFrame,
    feature_rows: Iterable[dict] = (),
    sector_rankings: Iterable[object] = (),
    history_path: Path | str = Path("history/market_style_history.csv"),
) -> MarketStyleSnapshot:
    frame = _normalize_spot(market_spot)
    feature_frame = pd.DataFrame(list(feature_rows))
    history = _load_style_history(history_path)
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
    directions = _capital_directions(sector_rankings, group_stats)
    weak = _weak_directions(sector_rankings, group_stats)
    today_style_raw = _dominant_style(group_stats, "average_pct")
    dominant_5d = _dominant_style(group_stats, "trend_5d")
    dominant_20d = _dominant_style(group_stats, "trend_20d")
    tech = group_stats["科技成长股"]
    traditional = group_stats["传统低位权重股"]
    growth_board = group_stats["创业板/科创板股票"]
    tech_strength = _style_strength(tech)
    traditional_strength = _style_strength(traditional)
    growth_board_strength = _style_strength(growth_board)
    capital_concentration = _capital_concentration(directions)
    hot_direction_count = sum(1 for item in directions if item.strength >= 70)
    hot_persistence = _hot_persistence(directions, history)
    rotation_strength = _rotation_strength(group_stats, history)
    style_scores = _style_scores(
        group_stats=group_stats,
        index_returns=index_returns,
        directions=directions,
        tech_strength=tech_strength,
        traditional_strength=traditional_strength,
        growth_board_strength=growth_board_strength,
        rotation_strength=rotation_strength,
        capital_concentration=capital_concentration,
    )
    ranked_styles = sorted(style_scores.items(), key=lambda item: item[1], reverse=True)
    today_style = ranked_styles[0][0] if ranked_styles else today_style_raw
    secondary_style = ranked_styles[1][0] if len(ranked_styles) > 1 else "其它"
    confidence = ranked_styles[0][1] if ranked_styles else 0.0
    score_gap = confidence - (ranked_styles[1][1] if len(ranked_styles) > 1 else 0.0)
    if score_gap < 10:
        today_style = "风格混乱"
    elif rotation_strength >= 65:
        today_style = "快速轮动"
    high_low_switch = tech.trend_5d + 1.5 < traditional.trend_5d and traditional.amount_share > tech.amount_share * 0.8
    tech_retreat = tech.trend_5d < -1.0 and tech.average_pct < traditional.average_pct - 0.8
    growth_board_recovering = (
        _index_value(index_returns, "创业板指", "5d") > _index_value(index_returns, "上证指数", "5d")
        and _index_value(index_returns, "科创50", "5d") > _index_value(index_returns, "上证指数", "5d")
    )
    traditional_short_rebound = traditional.trend_5d > tech.trend_5d + 1.0 and traditional.trend_20d <= tech.trend_20d + 0.5
    rotation_fast = today_style in {"快速轮动", "风格混乱"} or rotation_strength >= 65.0
    high_low_state = _high_low_state(high_low_switch, tech_retreat, traditional_short_rebound, growth_board_recovering, rotation_fast)
    consecutive_counts = _consecutive_counts(history, today_style)
    duration_days = consecutive_counts.get(today_style, 1)
    style_state = _style_state(history, today_style, confidence, rotation_fast)
    prediction = _style_prediction(history, today_style, style_scores, rotation_fast)
    validation_summary, rolling_accuracy = _validation_summary(history, today_style)
    recommendations = _recommendations(rotation_fast, high_low_switch, tech_retreat, growth_board_recovering, confidence, score_gap)
    score_cap = 75.0 if rotation_fast else None
    style_sentence = _style_sentence(high_low_state=high_low_state)
    explanation = _explanation(today_style, duration_days, style_state, high_low_state, directions)
    return MarketStyleSnapshot(
        trade_date=trade_date,
        index_returns=index_returns,
        index_rankings=index_rankings,
        leading_index=leading_index,
        today_style=today_style,
        secondary_style=secondary_style,
        dominant_5d=dominant_5d,
        dominant_20d=dominant_20d,
        confidence=confidence,
        style_scores=style_scores,
        duration_days=duration_days,
        consecutive_counts=consecutive_counts,
        style_state=style_state,
        high_low_state=high_low_state,
        high_low_switch=high_low_switch,
        tech_retreat=tech_retreat,
        growth_board_recovering=growth_board_recovering,
        traditional_short_rebound=traditional_short_rebound,
        rotation_fast=rotation_fast,
        action_advice="；".join(recommendations),
        recommendations=recommendations,
        style_sentence=style_sentence,
        explanation=explanation,
        group_stats=group_stats,
        capital_directions=directions,
        weak_directions=weak,
        prediction=prediction,
        validation_summary=validation_summary,
        rolling_accuracy_30d=rolling_accuracy,
        tech_strength=tech_strength,
        growth_board_strength=growth_board_strength,
        traditional_strength=traditional_strength,
        rotation_strength=rotation_strength,
        capital_concentration=capital_concentration,
        hot_direction_count=hot_direction_count,
        hot_persistence=hot_persistence,
        score_cap=score_cap,
    )


def market_style_score_adjustment(
    snapshot: MarketStyleSnapshot | None,
    *,
    code: str,
    sector: str,
    score: float,
) -> tuple[float, str, float | None]:
    if snapshot is None:
        return 0.0, "无风格数据", None
    group = classify_stock(code=code, sector=sector, score=score)
    topic = _topic_for_sector(sector)
    adjustment = 0.0
    reasons = []
    if snapshot.today_style == "科技成长":
        topic_bonus = {"AI": 4.0, "PCB": 3.0, "半导体": 3.0, "机器人": 2.0, "光模块": 2.0}
        if topic in topic_bonus or group in {"科技成长股", "创业板/科创板股票"}:
            adjustment += topic_bonus.get(topic, 2.0)
            reasons.append("科技成长主线占优，顺势加分")
        if group == "传统低位权重股":
            adjustment -= 2.0
            reasons.append("科技成长占优，低位权重降权")
    if snapshot.high_low_switch or snapshot.high_low_state == "高低切换":
        if group == "高位强势股" or score >= 75:
            adjustment -= 4.0
            reasons.append("高低切换，压低高位追涨分")
        if group in {"低位补涨股", "传统低位权重股"}:
            adjustment += 3.0
            reasons.append("高低切换，低位补涨加分")
    if snapshot.tech_retreat:
        if group == "科技成长股" and score >= 70:
            adjustment -= 5.0
            reasons.append("成长退潮，科技高位降权")
        if group == "传统低位权重股":
            adjustment += 4.0
            reasons.append("成长退潮，低位权重相对加分")
    if snapshot.traditional_short_rebound and group == "传统低位权重股":
        adjustment -= 2.0
        reasons.append("传统低位仅短线补涨，避免盲目推荐")
    if snapshot.rotation_fast:
        if score >= 70:
            adjustment -= 3.0
            reasons.append("快速轮动，降低追高等级")
    if snapshot.duration_days >= 3:
        if snapshot.today_style == "科技成长" and group in {"科技成长股", "创业板/科创板股票"}:
            adjustment += 2.0
            reasons.append("科技成长连续3日以上占优")
        if snapshot.today_style == "传统低位" and group == "传统低位权重股":
            adjustment += 2.0
            reasons.append("传统低位连续3日以上占优")
    if group == "科技成长股" and snapshot.dominant_20d == "科技成长股" and not snapshot.tech_retreat:
        adjustment += 1.0
        reasons.append("科技成长中期仍强，保留候选")
    return adjustment, "；".join(reasons) if reasons else "风格中性", snapshot.score_cap


def update_market_style_history(
    snapshot: MarketStyleSnapshot | None,
    *,
    history_path: Path | str = Path("history/market_style_history.csv"),
) -> Path:
    target = Path(history_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    history = _load_style_history(target)
    if snapshot is None:
        if not target.exists():
            pd.DataFrame(columns=STYLE_HISTORY_COLUMNS).to_csv(target, index=False, encoding="utf-8-sig")
        return target
    history = _apply_previous_validation(history, snapshot.today_style)
    prediction = snapshot.prediction or StylePrediction({}, "", "", 0)
    probabilities = prediction.probabilities
    row = {
        "日期": snapshot.trade_date.isoformat(),
        "主风格": snapshot.today_style,
        "副风格": snapshot.secondary_style,
        "置信度": round(snapshot.confidence, 2),
        "持续天数": snapshot.duration_days,
        "高低切状态": snapshot.high_low_state,
        "成长指数": round(snapshot.tech_strength, 2),
        "低位指数": round(snapshot.traditional_strength, 2),
        "轮动指数": round(snapshot.rotation_strength, 2),
        "资金集中度": round(snapshot.capital_concentration, 2),
        "热点数量": snapshot.hot_direction_count,
        "热点持续性": round(snapshot.hot_persistence, 2),
        "预测风格": prediction.predicted_style,
        "科技继续概率": round(probabilities.get("科技继续", 0.0), 2),
        "高低切概率": round(probabilities.get("高低切", 0.0), 2),
        "传统低位概率": round(probabilities.get("传统低位", 0.0), 2),
        "其它概率": round(probabilities.get("其它", 0.0), 2),
        "次日验证结果": "",
        "预测是否正确": "",
        "最近30天预测正确率": round(snapshot.rolling_accuracy_30d, 2),
    }
    if "日期" in history:
        history = history[history["日期"].astype(str) != row["日期"]].copy()
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True) if not history.empty else pd.DataFrame([row])
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


def _load_style_history(history_path: Path | str) -> pd.DataFrame:
    target = Path(history_path)
    if not target.exists():
        return pd.DataFrame(columns=STYLE_HISTORY_COLUMNS)
    history = pd.read_csv(target)
    for old, new in LEGACY_COLUMN_MAP.items():
        if old in history and new not in history:
            history[new] = history[old]
    for column in STYLE_HISTORY_COLUMNS:
        if column not in history:
            history[column] = ""
    history = history[STYLE_HISTORY_COLUMNS].copy()
    for column in ("次日验证结果", "预测是否正确"):
        history[column] = history[column].fillna("").astype(str)
    return history


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
        for window in (1, 5, 10, 20, 60, 90):
            rows[name][f"{window}d"] = _window_return(close, window)
    return rows


def _window_return(close: pd.Series, window: int) -> float:
    if len(close) <= window:
        return 0.0
    previous = float(close.iloc[-window - 1])
    latest = float(close.iloc[-1])
    return (latest / previous - 1) * 100 if previous else 0.0


def _rank_indices(index_returns: dict[str, dict[str, float]], key: str) -> list[str]:
    return [name for name, _ in sorted(index_returns.items(), key=lambda item: item[1].get(key, 0.0), reverse=True)]


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
    return pd.Series(False, index=frame.index)


def _group_stats(name: str, mask: pd.Series, frame: pd.DataFrame, feature_frame: pd.DataFrame) -> StyleGroupStats:
    if name in {"高位强势股", "低位补涨股"} and not feature_frame.empty and "style_group" in feature_frame:
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
    amount_share = float(amount.sum() / total_amount * 100) if total_amount else 0.0
    return StyleGroupStats(
        name=name,
        up_count=int((pct > 0).sum()),
        down_count=int((pct < 0).sum()),
        limit_up_count=int((limit_up == 1).sum()),
        limit_down_count=int((limit_down == 1).sum()),
        average_pct=float(pct.mean()) if not pct.empty else 0.0,
        amount_share=amount_share,
        fund_strength=float((pct.mean() if not pct.empty else 0.0) * 10 + amount_share),
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


def _style_scores(
    *,
    group_stats: dict[str, StyleGroupStats],
    index_returns: dict[str, dict[str, float]],
    directions: list[CapitalDirection],
    tech_strength: float,
    traditional_strength: float,
    growth_board_strength: float,
    rotation_strength: float,
    capital_concentration: float,
) -> dict[str, float]:
    tech_flow = sum(item.strength for item in directions if _topic_is_tech(item.name))
    traditional_flow = sum(item.strength for item in directions if _topic_is_traditional(item.name))
    growth_index = max(
        _index_value(index_returns, "创业板指", "5d") - _index_value(index_returns, "上证指数", "5d"),
        _index_value(index_returns, "科创50", "5d") - _index_value(index_returns, "上证指数", "5d"),
        0.0,
    )
    traditional_index = max(_index_value(index_returns, "上证指数", "5d") - _index_value(index_returns, "创业板指", "5d"), 0.0)
    raw = {
        "科技成长": tech_strength * 0.45 + growth_board_strength * 0.25 + min(tech_flow / 3, 35) + min(growth_index * 2, 12),
        "传统低位": traditional_strength * 0.55 + min(traditional_flow / 3, 30) + min(traditional_index * 2, 12),
        "快速轮动": rotation_strength * 0.8 + max(0.0, 35.0 - capital_concentration) * 0.35,
        "其它": max(0.0, 45.0 - max(tech_strength, traditional_strength, growth_board_strength)) + group_stats["低位补涨股"].fund_strength * 0.15,
    }
    total = sum(max(value, 0.0) for value in raw.values())
    if total <= 0:
        return {key: 0.0 for key in raw}
    return {key: max(value, 0.0) / total * 100 for key, value in raw.items()}


def _rotation_strength(group_stats: dict[str, StyleGroupStats], history: pd.DataFrame) -> float:
    active = [item for item in group_stats.values() if item.sample_count > 0]
    if len(active) < 2:
        return 0.0
    today_rank = [item.name for item in sorted(active, key=lambda item: item.average_pct, reverse=True)]
    five_rank = [item.name for item in sorted(active, key=lambda item: item.trend_5d, reverse=True)]
    mismatch = sum(1 for index, name in enumerate(today_rank) if index >= len(five_rank) or five_rank[index] != name)
    spread = max(item.average_pct for item in active) - min(item.average_pct for item in active)
    recent_switches = _recent_switches(history)
    return max(0.0, min(100.0, mismatch / len(active) * 45 + min(spread * 7, 35) + recent_switches * 8))


def _capital_directions(sector_rankings: Iterable[object], group_stats: dict[str, StyleGroupStats]) -> list[CapitalDirection]:
    rows = []
    for sector in sector_rankings:
        name = str(getattr(sector, "name", "") or "")
        if not name or name == "未映射":
            continue
        pct = float(getattr(sector, "pct_change", 0.0) or 0.0)
        flow = float(getattr(sector, "main_net_inflow", 0.0) or 0.0)
        heat = float(getattr(sector, "heat_score", 0.0) or 0.0)
        rank = float(getattr(sector, "rank", 999_999) or 999_999)
        strength = max(0.0, heat * 8 + pct * 8 + min(max(flow, 0.0) / 100_000_000, 35) + max(0.0, 20 - min(rank, 20)))
        rows.append(CapitalDirection(_topic_label(name), min(100.0, strength), _stars(strength), pct, flow, str(getattr(sector, "sector_type", "板块"))))
    if not rows:
        for stats in group_stats.values():
            rows.append(CapitalDirection(stats.name, min(100.0, max(0.0, stats.fund_strength)), _stars(stats.fund_strength), stats.average_pct, 0.0, "风格组"))
    deduped: dict[str, CapitalDirection] = {}
    for row in rows:
        current = deduped.get(row.name)
        if current is None or row.strength > current.strength:
            deduped[row.name] = row
    return sorted(deduped.values(), key=lambda item: item.strength, reverse=True)[:8]


def _weak_directions(sector_rankings: Iterable[object], group_stats: dict[str, StyleGroupStats]) -> list[CapitalDirection]:
    rows = []
    for sector in sector_rankings:
        name = str(getattr(sector, "name", "") or "")
        if not name or name == "未映射":
            continue
        pct = float(getattr(sector, "pct_change", 0.0) or 0.0)
        flow = float(getattr(sector, "main_net_inflow", 0.0) or 0.0)
        heat = float(getattr(sector, "heat_score", 0.0) or 0.0)
        weakness = max(0.0, 50 - heat * 6 - pct * 8 - min(flow / 100_000_000, 20))
        rows.append(CapitalDirection(_topic_label(name), min(100.0, weakness), _stars(weakness), pct, flow, str(getattr(sector, "sector_type", "板块"))))
    if not rows:
        for stats in group_stats.values():
            weakness = max(0.0, 50 - stats.fund_strength)
            rows.append(CapitalDirection(stats.name, weakness, _stars(weakness), stats.average_pct, 0.0, "风格组"))
    return sorted(rows, key=lambda item: item.strength, reverse=True)[:5]


def _capital_concentration(directions: list[CapitalDirection]) -> float:
    total = sum(max(item.strength, 0.0) for item in directions)
    if not total:
        return 0.0
    return sum(max(item.strength, 0.0) for item in directions[:3]) / total * 100


def _hot_persistence(directions: list[CapitalDirection], history: pd.DataFrame) -> float:
    if history.empty or not directions:
        return 0.0
    recent = history.tail(10)
    mainline_days = pd.to_numeric(recent.get("置信度", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    return float(mainline_days[mainline_days >= 55].count() / max(len(recent), 1) * 100)


def _consecutive_counts(history: pd.DataFrame, today_style: str) -> dict[str, int]:
    styles = ["科技成长", "传统低位", "快速轮动", "震荡"]
    counts = {style: 0 for style in styles}
    normalized_today = _count_style(today_style)
    counts[normalized_today] = 1
    for value in reversed(history.get("主风格", pd.Series(dtype=str)).astype(str).tolist()):
        normalized = _count_style(value)
        if normalized == normalized_today:
            counts[normalized_today] += 1
        else:
            break
    return counts


def _count_style(style: str) -> str:
    if "科技" in style or "成长" in style:
        return "科技成长"
    if "传统" in style or "低位" in style:
        return "传统低位"
    if "轮动" in style or "混乱" in style:
        return "快速轮动"
    return "震荡"


def _style_state(history: pd.DataFrame, today_style: str, confidence: float, rotation_fast: bool) -> str:
    if rotation_fast:
        return "高低切换" if "轮动" not in today_style else "快速轮动"
    previous = history.tail(1)
    if previous.empty:
        return "新风格确认"
    previous_style = str(previous.iloc[-1].get("主风格", ""))
    previous_confidence = pd.to_numeric(previous.iloc[-1].get("置信度", 0.0), errors="coerce")
    previous_confidence = 0.0 if pd.isna(previous_confidence) else float(previous_confidence)
    if previous_style == today_style and confidence >= previous_confidence:
        return "持续加强"
    if previous_style == today_style:
        return "延续但降温"
    return "风格切换"


def _style_prediction(history: pd.DataFrame, today_style: str, style_scores: dict[str, float], rotation_fast: bool) -> StylePrediction:
    transitions = {"科技继续": 0, "高低切": 0, "传统低位": 0, "其它": 0}
    sample = 0
    styles = history.get("主风格", pd.Series(dtype=str)).astype(str).tolist()
    for current, nxt in zip(styles, styles[1:]):
        if _same_prediction_base(current, today_style):
            sample += 1
            transitions[_prediction_bucket(nxt)] += 1
    if sample >= 3:
        probabilities = {key: value / sample * 100 for key, value in transitions.items()}
        basis = "历史风格库同类状态转移统计"
    else:
        probabilities = {
            "科技继续": style_scores.get("科技成长", 0.0),
            "高低切": max(style_scores.get("快速轮动", 0.0), 45.0 if rotation_fast else 0.0),
            "传统低位": style_scores.get("传统低位", 0.0),
            "其它": style_scores.get("其它", 0.0),
        }
        total = sum(probabilities.values())
        probabilities = {key: (value / total * 100 if total else 0.0) for key, value in probabilities.items()}
        basis = "历史样本不足，使用当前90日风格结构冷启动"
    predicted = max(probabilities.items(), key=lambda item: item[1])[0] if probabilities else "其它"
    return StylePrediction(probabilities=probabilities, predicted_style=predicted, basis=basis, sample_count=sample)


def _same_prediction_base(current: str, today_style: str) -> bool:
    return _prediction_bucket(current) == _prediction_bucket(today_style)


def _prediction_bucket(style: str) -> str:
    if "科技" in style or "成长" in style:
        return "科技继续"
    if "传统" in style or "低位" in style:
        return "传统低位"
    if "轮动" in style or "混乱" in style or "切" in style:
        return "高低切"
    return "其它"


def _validation_summary(history: pd.DataFrame, today_style: str) -> tuple[str, float]:
    if history.empty:
        return "暂无已完成的风格验证数据。", 0.0
    previous = history.tail(1).iloc[-1]
    predicted = str(previous.get("预测风格", "") or "")
    if not predicted:
        return "昨天没有可验证的风格预测。", _rolling_accuracy(history)
    correct = _prediction_bucket(today_style) == predicted
    summary = f"昨天预测：{predicted}；今天：{today_style}；预测{'正确' if correct else '未命中'}。"
    return summary, _rolling_accuracy(_apply_previous_validation(history.copy(), today_style))


def _rolling_accuracy(history: pd.DataFrame) -> float:
    if history.empty or "预测是否正确" not in history:
        return 0.0
    recent = history[history["预测是否正确"].astype(str).isin(["是", "否"])].tail(30)
    if recent.empty:
        return 0.0
    return float((recent["预测是否正确"].astype(str) == "是").mean() * 100)


def _apply_previous_validation(history: pd.DataFrame, today_style: str) -> pd.DataFrame:
    if history.empty or "预测风格" not in history:
        return history
    for column in ("次日验证结果", "预测是否正确"):
        if column in history:
            history[column] = history[column].fillna("").astype(str)
    idx = history.index[-1]
    predicted = str(history.at[idx, "预测风格"] or "")
    if not predicted:
        return history
    correct = _prediction_bucket(today_style) == predicted
    history.at[idx, "次日验证结果"] = f"今日风格={today_style}"
    history.at[idx, "预测是否正确"] = "是" if correct else "否"
    history.at[idx, "最近30天预测正确率"] = round(_rolling_accuracy(history), 2)
    return history


def _recent_switches(history: pd.DataFrame) -> int:
    styles = history.get("主风格", pd.Series(dtype=str)).astype(str).tail(6).tolist()
    return sum(1 for prev, cur in zip(styles, styles[1:]) if prev and cur and _count_style(prev) != _count_style(cur))


def _high_low_state(
    high_low_switch: bool,
    tech_retreat: bool,
    traditional_short_rebound: bool,
    growth_board_recovering: bool,
    rotation_fast: bool,
) -> str:
    if rotation_fast:
        return "快速轮动"
    if high_low_switch or tech_retreat:
        return "高低切换"
    if growth_board_recovering:
        return "成长回流"
    if traditional_short_rebound:
        return "传统低位短线补涨"
    return "主线延续"


def _recommendations(
    rotation_fast: bool,
    high_low_switch: bool,
    tech_retreat: bool,
    growth_board_recovering: bool,
    confidence: float,
    score_gap: float,
) -> list[str]:
    if rotation_fast or score_gap < 10:
        return ["建议控制仓位", "建议只做龙头", "不建议追涨"]
    if high_low_switch:
        return ["可以低吸", "建议只做低位", "不建议打板"]
    if tech_retreat and not growth_board_recovering:
        return ["建议空仓", "建议只观察"]
    if confidence >= 60 and growth_board_recovering:
        return ["可以低吸", "可以追涨", "建议只做龙头"]
    if confidence >= 60:
        return ["可以低吸", "建议控制仓位"]
    return ["建议只观察", "建议控制仓位"]


def _style_sentence(*, high_low_state: str) -> str:
    return f"当前市场不是单边主线，而是{high_low_state}。"


def _explanation(today_style: str, duration_days: int, style_state: str, high_low_state: str, directions: list[CapitalDirection]) -> str:
    leading = "、".join(item.name for item in directions[:3]) or "暂无明确方向"
    return f"最近{duration_days}天{today_style}风格{style_state}，资金主要流向{leading}，当前状态为{high_low_state}。"


def _topic_label(name: str) -> str:
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return topic
    return name


def _topic_for_sector(sector: str) -> str:
    return _topic_label(str(sector))


def _topic_is_tech(name: str) -> bool:
    return any(keyword in name for keyword in ("AI", "PCB", "半导体", "光模块", "机器人", "消费电子", "铜连接", "创业板", "算力"))


def _topic_is_traditional(name: str) -> bool:
    return any(keyword in name for keyword in ("银行", "煤炭", "地产", "中字头", "钢铁", "基建", "电力"))


def _stars(strength: float) -> str:
    stars = max(1, min(5, int(round(max(strength, 0.0) / 20.0))))
    return "★" * stars + "☆" * (5 - stars)
