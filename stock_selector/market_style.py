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
    "第一主线",
    "第一主线强度",
    "市场温度",
    "市场节奏",
    "建议仓位",
    "交易价值评分",
    "市场风险评分",
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
    "AI服务器": ("AI服务器", "服务器", "液冷服务器"),
    "AI应用": ("AI应用", "AIGC", "人工智能", "AI", "数据"),
    "算力": ("算力", "云计算", "数据中心"),
    "PCB": ("PCB", "印制电路", "覆铜板"),
    "CPO": ("CPO",),
    "铜缆高速连接": ("铜连接", "高速连接", "连接器", "铜缆"),
    "芯片": ("芯片", "集成电路"),
    "半导体设备": ("半导体设备", "光刻", "刻蚀", "设备"),
    "半导体": ("半导体",),
    "光模块": ("光模块", "CPO", "光通信"),
    "机器人": ("机器人", "减速器", "工业母机"),
    "军工": ("军工", "航天", "航空", "船舶"),
    "创新药": ("创新药", "医药", "生物制药"),
    "消费电子": ("消费电子", "苹果", "MR", "电子"),
    "游戏传媒": ("游戏", "传媒", "短剧"),
    "证券": ("证券", "券商"),
    "银行": ("银行",),
    "煤炭": ("煤炭",),
    "电力": ("电力", "公用事业"),
    "有色": ("有色", "铜", "铝", "黄金"),
    "稀土": ("稀土", "磁材"),
    "锂电": ("锂电", "锂矿", "电池"),
    "固态电池": ("固态电池",),
    "房地产": ("地产", "房地产"),
    "中字头": ("中字头", "央企"),
}

INTERNAL_STYLE_GROUPS = {
    "科技成长股",
    "创业板/科创板股票",
    "传统低位权重股",
    "高位强势股",
    "低位补涨股",
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
class MainlineStats:
    name: str
    rank: int
    stars: str
    up_count: int = 0
    average_pct: float = 0.0
    limit_up_count: int = 0
    amount: float = 0.0
    main_net_inflow: float = 0.0
    top20_count: int = 0
    strength: float = 0.0
    leaders: list[dict] = field(default_factory=list)
    persistence_stars: str = "★☆☆☆☆"
    persistence_reason: str = "持续性数据不足"


@dataclass(frozen=True)
class MarketEmotion:
    temperature: float
    profit_effect_stars: str
    loss_effect_stars: str
    limit_up_premium_5d: float
    failed_limit_up_count: int
    max_board_height: int
    max_board_stock: str
    limit_down_count: int
    limit_up_count: int
    promotion_rate: float
    first_board_count: int
    second_board_count: int
    third_board_count: int
    fourth_plus_count: int
    relay_score: float


@dataclass(frozen=True)
class RhythmAssessment:
    stage: str
    stars: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class PredictionDetail:
    prediction: str
    probability: float
    historical_count: int
    success_count: int
    success_rate: float
    similar_cases: list[str]


@dataclass(frozen=True)
class PositionAdvice:
    percent: int
    stars: str
    reason: str


@dataclass(frozen=True)
class RiskAssessment:
    stars: str
    total_score: float
    source_scores: dict[str, float]


@dataclass(frozen=True)
class TradingDecisionSnapshot:
    mainlines: list[MainlineStats]
    emotion: MarketEmotion
    rhythm: RhythmAssessment
    rotation_reasons: list[str]
    prediction_detail: PredictionDetail
    position_advice: PositionAdvice
    trade_mode_scores: dict[str, str]
    forbidden_actions: list[str]
    one_sentence: str
    risk: RiskAssessment
    trade_value_stars: str
    trade_value_reason: str
    validation: dict[str, float]


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
    trading_decision: TradingDecisionSnapshot | None = None


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
    decision = _trading_decision(
        trade_date=trade_date,
        frame=frame,
        history=history,
        group_stats=group_stats,
        index_returns=index_returns,
        directions=directions,
        weak_directions=weak,
        style_state=style_state,
        high_low_state=high_low_state,
        rotation_fast=rotation_fast,
        prediction=prediction,
    )
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
        trading_decision=decision,
    )


def attach_top20_to_market_style(
    snapshot: MarketStyleSnapshot | None,
    top20: Iterable[object],
) -> MarketStyleSnapshot | None:
    if snapshot is None or snapshot.trading_decision is None:
        return snapshot
    mainlines = _attach_top20_to_mainlines(snapshot.trading_decision.mainlines, top20)
    decision = snapshot.trading_decision
    updated = TradingDecisionSnapshot(
        mainlines=mainlines,
        emotion=decision.emotion,
        rhythm=decision.rhythm,
        rotation_reasons=decision.rotation_reasons,
        prediction_detail=decision.prediction_detail,
        position_advice=decision.position_advice,
        trade_mode_scores=decision.trade_mode_scores,
        forbidden_actions=decision.forbidden_actions,
        one_sentence=_one_sentence(decision.rhythm.stage, mainlines, decision.emotion, decision.position_advice),
        risk=decision.risk,
        trade_value_stars=decision.trade_value_stars,
        trade_value_reason=decision.trade_value_reason,
        validation=decision.validation,
    )
    return MarketStyleSnapshot(**{**snapshot.__dict__, "trading_decision": updated})


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
    decision = snapshot.trading_decision
    first_mainline = decision.mainlines[0] if decision and decision.mainlines else None
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
        "第一主线": first_mainline.name if first_mainline else "",
        "第一主线强度": round(first_mainline.strength, 2) if first_mainline else 0.0,
        "市场温度": round(decision.emotion.temperature, 2) if decision else 0.0,
        "市场节奏": decision.rhythm.stage if decision else "",
        "建议仓位": decision.position_advice.percent if decision else 0,
        "交易价值评分": decision.trade_value_stars if decision else "",
        "市场风险评分": round(decision.risk.total_score, 2) if decision else 0.0,
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


def _trading_decision(
    *,
    trade_date: date,
    frame: pd.DataFrame,
    history: pd.DataFrame,
    group_stats: dict[str, StyleGroupStats],
    index_returns: dict[str, dict[str, float]],
    directions: list[CapitalDirection],
    weak_directions: list[CapitalDirection],
    style_state: str,
    high_low_state: str,
    rotation_fast: bool,
    prediction: StylePrediction,
) -> TradingDecisionSnapshot:
    mainlines = _mainline_stats(frame, directions, [])
    emotion = _market_emotion(frame, history)
    rhythm = _market_rhythm(emotion, mainlines, index_returns, rotation_fast)
    rotation_reasons = _rotation_reasons(history, index_returns, directions, weak_directions, group_stats)
    prediction_detail = _prediction_detail(history, prediction, trade_date)
    position = _position_advice(emotion, rhythm, mainlines, rotation_fast)
    risk = _risk_assessment(emotion, rhythm, index_returns, mainlines)
    trade_modes = _trade_mode_scores(emotion, rhythm, position, rotation_fast)
    forbidden = _forbidden_actions(emotion, rhythm, mainlines, risk, high_low_state)
    trade_value_score = max(0.0, min(100.0, emotion.temperature * 0.35 + position.percent * 0.35 + mainlines[0].strength * 0.3 if mainlines else emotion.temperature))
    trade_value_reason = _trade_value_reason(emotion, rhythm, mainlines, risk)
    validation = _prediction_accuracy_windows(history)
    return TradingDecisionSnapshot(
        mainlines=mainlines,
        emotion=emotion,
        rhythm=rhythm,
        rotation_reasons=rotation_reasons,
        prediction_detail=prediction_detail,
        position_advice=position,
        trade_mode_scores=trade_modes,
        forbidden_actions=forbidden,
        one_sentence=_one_sentence(rhythm.stage, mainlines, emotion, position),
        risk=risk,
        trade_value_stars=_stars(trade_value_score),
        trade_value_reason=trade_value_reason,
        validation=validation,
    )


def _mainline_stats(frame: pd.DataFrame, directions: list[CapitalDirection], top20: Iterable[object]) -> list[MainlineStats]:
    rows: dict[str, MainlineStats] = {}
    total_amount = pd.to_numeric(frame.get("成交额", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()
    top20_list = list(top20)
    for direction in directions:
        topic = _topic_label(direction.name)
        if topic in INTERNAL_STYLE_GROUPS:
            continue
        mask = frame["所属板块"].astype(str).map(lambda value: _topic_label(value) == topic or topic in value)
        subset = frame[mask].copy()
        pct = pd.to_numeric(subset.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        amount = pd.to_numeric(subset.get("成交额", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        limit_up = pd.to_numeric(subset.get("涨停标记", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        top20_count = sum(1 for item in top20_list if _topic_label(str(getattr(item, "sector", ""))) == topic)
        amount_score = amount.sum() / total_amount * 100 if total_amount else 0.0
        strength = max(
            0.0,
            min(
                100.0,
                direction.strength * 0.35
                + max(float(pct.mean()) if not pct.empty else direction.pct_change, 0.0) * 8
                + min(amount_score, 25)
                + min(max(direction.main_net_inflow, 0.0) / 100_000_000, 20)
                + top20_count * 4,
            ),
        )
        leaders = _mainline_leaders(topic, subset, top20_list)
        rows[topic] = MainlineStats(
            name=topic,
            rank=0,
            stars=_stars(strength),
            up_count=int((pct > 0).sum()) if not pct.empty else 0,
            average_pct=float(pct.mean()) if not pct.empty else direction.pct_change,
            limit_up_count=int((limit_up == 1).sum()) if not limit_up.empty else 0,
            amount=float(amount.sum()),
            main_net_inflow=direction.main_net_inflow,
            top20_count=top20_count,
            strength=strength,
            leaders=leaders,
            persistence_stars=_stars(strength * 0.65 + min(max(direction.main_net_inflow, 0.0) / 100_000_000, 25)),
            persistence_reason=_persistence_reason(strength, direction.main_net_inflow, top20_count),
        )
    ranked = sorted(rows.values(), key=lambda item: item.strength, reverse=True)[:8]
    return [
        MainlineStats(**{**item.__dict__, "rank": index})
        for index, item in enumerate(ranked, start=1)
    ]


def _attach_top20_to_mainlines(mainlines: list[MainlineStats], top20: Iterable[object]) -> list[MainlineStats]:
    top20_list = list(top20)
    updated = []
    for item in mainlines:
        matched = [stock for stock in top20_list if _topic_label(str(getattr(stock, "sector", ""))) == item.name]
        top20_count = len(matched)
        leaders = _mainline_leaders_from_candidates(matched) or item.leaders
        strength = max(0.0, min(100.0, item.strength + top20_count * 4))
        updated.append(
            MainlineStats(
                name=item.name,
                rank=item.rank,
                stars=_stars(strength),
                up_count=item.up_count,
                average_pct=item.average_pct,
                limit_up_count=item.limit_up_count,
                amount=item.amount,
                main_net_inflow=item.main_net_inflow,
                top20_count=top20_count,
                strength=strength,
                leaders=leaders,
                persistence_stars=_stars(strength * 0.75),
                persistence_reason=_persistence_reason(strength, item.main_net_inflow, top20_count),
            )
        )
    existing = {item.name for item in updated}
    grouped: dict[str, list[object]] = {}
    for item in top20_list:
        topic = _topic_label(str(getattr(item, "sector", "")))
        if not topic or topic == "未映射" or topic in INTERNAL_STYLE_GROUPS or topic in existing:
            continue
        grouped.setdefault(topic, []).append(item)
    for topic, stocks in grouped.items():
        amount = sum(float(getattr(stock, "amount", 0.0) or 0.0) for stock in stocks)
        strength = max(0.0, min(100.0, 45 + len(stocks) * 8 + min(amount / 1_000_000_000, 25)))
        updated.append(
            MainlineStats(
                name=topic,
                rank=len(updated) + 1,
                stars=_stars(strength),
                amount=amount,
                top20_count=len(stocks),
                strength=strength,
                leaders=_mainline_leaders_from_candidates(stocks),
                persistence_stars=_stars(strength * 0.7),
                persistence_reason=_persistence_reason(strength, 0.0, len(stocks)),
            )
        )
    ranked = sorted(updated, key=lambda value: value.strength, reverse=True)
    return [MainlineStats(**{**item.__dict__, "rank": index}) for index, item in enumerate(ranked, start=1)]


def _mainline_leaders(topic: str, subset: pd.DataFrame, candidates: list[object]) -> list[dict]:
    candidate_leaders = _mainline_leaders_from_candidates([item for item in candidates if _topic_label(str(getattr(item, "sector", ""))) == topic])
    if candidate_leaders:
        return candidate_leaders
    if subset.empty:
        return []
    ranked = subset.copy()
    ranked["_pct"] = pd.to_numeric(ranked.get("涨跌幅", 0.0), errors="coerce").fillna(0.0)
    ranked["_amount"] = pd.to_numeric(ranked.get("成交额", 0.0), errors="coerce").fillna(0.0)
    ranked = ranked.sort_values(["_pct", "_amount"], ascending=False).head(3)
    return [
        {
            "name": str(row.get("名称", "")),
            "code": str(row.get("代码", "")),
            "reason": _leader_reason(row.get("_amount", 0.0), row.get("_pct", 0.0), row.get("换手率", 0.0), False, False),
            "amount": float(row.get("_amount", 0.0)),
            "pct": float(row.get("_pct", 0.0)),
            "turnover": float(pd.to_numeric(row.get("换手率", 0.0), errors="coerce") or 0.0),
        }
        for _, row in ranked.iterrows()
    ]


def _mainline_leaders_from_candidates(candidates: list[object]) -> list[dict]:
    ranked = sorted(candidates, key=lambda item: (float(getattr(item, "score", 0.0)), float(getattr(item, "amount", 0.0))), reverse=True)[:3]
    leaders = []
    for item in ranked:
        breakout = float(getattr(item, "breakout_margin", 0.0) or 0.0) > 0
        continuous = float(getattr(item, "ma5", 0.0) or 0.0) >= float(getattr(item, "ma10", 0.0) or 0.0) >= float(getattr(item, "ma20", 0.0) or 0.0)
        leaders.append(
            {
                "name": str(getattr(item, "name", "")),
                "code": str(getattr(item, "code", "")),
                "reason": _leader_reason(getattr(item, "amount", 0.0), getattr(item, "sector_pct_change", 0.0), getattr(item, "turnover_rate", 0.0), breakout, continuous),
                "amount": float(getattr(item, "amount", 0.0) or 0.0),
                "pct": float(getattr(item, "sector_pct_change", 0.0) or 0.0),
                "turnover": float(getattr(item, "turnover_rate", 0.0) or 0.0),
            }
        )
    return leaders


def _leader_reason(amount: float, pct: float, turnover: float, breakout: bool, continuous: bool) -> str:
    parts = [f"成交额{amount / 100_000_000:.1f}亿元", f"涨幅{pct:.2f}%", f"换手率{float(turnover):.2f}%"]
    if breakout:
        parts.append("接近或突破阶段新高")
    if continuous:
        parts.append("均线趋势保持多头")
    return "；".join(parts)


def _market_emotion(frame: pd.DataFrame, history: pd.DataFrame) -> MarketEmotion:
    pct = pd.to_numeric(frame.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    up_ratio = float((pct > 0).mean() * 100) if len(pct) else 0.0
    limit_up = pd.to_numeric(frame.get("涨停标记", pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    limit_down = pd.to_numeric(frame.get("跌停标记", pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    limit_up_count = int((limit_up == 1).sum())
    limit_down_count = int((limit_down == 1).sum())
    failed = _column_sum(frame, ("炸板数量", "炸板", "failed_limit_up"))
    max_board_height = int(max(_column_max(frame, ("连板高度", "连续涨停天数", "board_height")), 1 if limit_up_count else 0))
    max_board_stock = _max_board_stock(frame, max_board_height)
    promotion_rate = limit_up_count / max(limit_up_count + failed, 1) * 100
    temperature = max(0.0, min(100.0, up_ratio * 0.45 + min(limit_up_count, 80) * 0.35 + promotion_rate * 0.2 - limit_down_count * 1.5))
    relay = max(0.0, min(100.0, max_board_height * 12 + promotion_rate * 0.35 + limit_up_count * 0.25 - failed * 1.5))
    return MarketEmotion(
        temperature=temperature,
        profit_effect_stars=_stars(up_ratio),
        loss_effect_stars=_stars(100 - up_ratio + limit_down_count * 2),
        limit_up_premium_5d=_history_average(history, "涨停溢价", default=0.0),
        failed_limit_up_count=int(failed),
        max_board_height=max_board_height,
        max_board_stock=max_board_stock,
        limit_down_count=limit_down_count,
        limit_up_count=limit_up_count,
        promotion_rate=promotion_rate,
        first_board_count=int(max(limit_up_count - max_board_height + 1, 0)) if limit_up_count else 0,
        second_board_count=1 if max_board_height >= 2 else 0,
        third_board_count=1 if max_board_height >= 3 else 0,
        fourth_plus_count=1 if max_board_height >= 4 else 0,
        relay_score=relay,
    )


def _market_rhythm(emotion: MarketEmotion, mainlines: list[MainlineStats], index_returns: dict[str, dict[str, float]], rotation_fast: bool) -> RhythmAssessment:
    index_5d = _index_value(index_returns, "上证指数", "5d")
    leader_strength = mainlines[0].strength if mainlines else 0.0
    if emotion.temperature < 25 or emotion.limit_down_count > emotion.limit_up_count:
        stage = "冰点期"
        reason = "跌停或亏钱效应占优，市场温度低。"
    elif leader_strength >= 85 and emotion.temperature >= 75 and emotion.relay_score >= 70:
        stage = "高潮期"
        reason = "主线强度高，涨停和接力情绪同步升温。"
    elif rotation_fast or (mainlines and len([item for item in mainlines[:3] if item.strength >= 55]) >= 3):
        stage = "分歧期"
        reason = "多条主线并行争夺资金，热点切换速度加快。"
    elif index_5d > 1 and leader_strength >= 65:
        stage = "发酵期"
        reason = "指数和主线同步走强，赚钱效应扩散。"
    elif leader_strength >= 50 and emotion.temperature >= 45:
        stage = "启动期"
        reason = "主线开始出现强度，但赚钱效应尚未全面扩散。"
    else:
        stage = "退潮期"
        reason = "主线强度和市场温度同步回落。"
    confidence = max(emotion.temperature, leader_strength)
    return RhythmAssessment(stage=stage, stars=_stars(confidence), confidence=confidence, reason=reason)


def _rotation_reasons(
    history: pd.DataFrame,
    index_returns: dict[str, dict[str, float]],
    directions: list[CapitalDirection],
    weak_directions: list[CapitalDirection],
    group_stats: dict[str, StyleGroupStats],
) -> list[str]:
    reasons = []
    if directions and directions[0].strength >= 75:
        reasons.append(f"{directions[0].name}资金强度达到{directions[0].strength:.1f}，成为短线资金集中方向。")
    if weak_directions and (not directions or weak_directions[0].name != directions[0].name) and weak_directions[0].strength >= 50:
        reasons.append(f"{weak_directions[0].name}转弱，资金从弱势方向撤出。")
    if _index_value(index_returns, "创业板指", "5d") < 0:
        reasons.append("创业板最近5日走弱，成长方向承压。")
    if _index_value(index_returns, "上证指数", "20d") > _index_value(index_returns, "创业板指", "20d"):
        reasons.append("最近20日上证强于创业板，低位权重相对占优。")
    if _index_value(index_returns, "科创50", "60d") < _index_value(index_returns, "上证指数", "60d"):
        reasons.append("最近60日科创50弱于上证，科技弹性资金持续性不足。")
    if _index_value(index_returns, "北证50", "90d") > _index_value(index_returns, "上证指数", "90d"):
        reasons.append("最近90日北证50相对更强，小盘弹性资金活跃。")
    high = group_stats.get("高位强势股", StyleGroupStats("高位强势股"))
    low = group_stats.get("低位补涨股", StyleGroupStats("低位补涨股"))
    if high.trend_20d > 15 and high.average_pct < low.average_pct:
        reasons.append("高位强势股20日涨幅较大但今日跑输低位补涨，存在兑现压力。")
    if not reasons:
        reasons.append("指数、成交额和主线强度没有形成单边解释，按快速轮动处理。")
    return reasons[:6]


def _prediction_detail(history: pd.DataFrame, prediction: StylePrediction, trade_date: date) -> PredictionDetail:
    predicted = prediction.predicted_style or "其它"
    matches = history[history.get("预测风格", pd.Series(dtype=str)).astype(str) == predicted].copy() if not history.empty else pd.DataFrame()
    historical_count = len(matches)
    success_count = int((matches.get("预测是否正确", pd.Series(dtype=str)).astype(str) == "是").sum()) if not matches.empty else 0
    success_rate = success_count / historical_count * 100 if historical_count else 0.0
    similar = matches.tail(3).get("日期", pd.Series(dtype=str)).astype(str).tolist() if not matches.empty else []
    probability = prediction.probabilities.get(predicted, 0.0) if prediction.probabilities else 0.0
    return PredictionDetail(predicted, probability, historical_count, success_count, success_rate, similar or [trade_date.isoformat()])


def _position_advice(emotion: MarketEmotion, rhythm: RhythmAssessment, mainlines: list[MainlineStats], rotation_fast: bool) -> PositionAdvice:
    leader_strength = mainlines[0].strength if mainlines else 0.0
    raw = emotion.temperature * 0.45 + leader_strength * 0.35 + rhythm.confidence * 0.2
    if rotation_fast:
        raw -= 15
    if rhythm.stage in {"冰点期", "退潮期"}:
        raw -= 20
    percent = int(max(10, min(100, round(raw / 10) * 10)))
    reason = "；".join([f"市场温度{emotion.temperature:.0f}", f"节奏为{rhythm.stage}", f"第一主线强度{leader_strength:.0f}"])
    return PositionAdvice(percent=percent, stars=_stars(percent), reason=reason)


def _risk_assessment(emotion: MarketEmotion, rhythm: RhythmAssessment, index_returns: dict[str, dict[str, float]], mainlines: list[MainlineStats]) -> RiskAssessment:
    source = {
        "成交量": max(0.0, 60 - (mainlines[0].amount / 1_000_000_000 if mainlines else 0.0)),
        "指数": max(0.0, -_index_value(index_returns, "上证指数", "5d") * 12 + -_index_value(index_returns, "创业板指", "5d") * 8),
        "板块": max(0.0, 70 - (mainlines[0].strength if mainlines else 0.0)),
        "龙头": max(0.0, 55 - (mainlines[0].top20_count * 12 if mainlines else 0.0)),
        "情绪": max(0.0, 70 - emotion.temperature + emotion.failed_limit_up_count * 2),
    }
    total = sum(source.values()) / len(source)
    if rhythm.stage in {"退潮期", "冰点期"}:
        total += 15
    total = max(0.0, min(100.0, total))
    return RiskAssessment(_stars(total), total, {key: round(value, 1) for key, value in source.items()})


def _trade_mode_scores(emotion: MarketEmotion, rhythm: RhythmAssessment, position: PositionAdvice, rotation_fast: bool) -> dict[str, str]:
    base = position.percent
    scores = {
        "追涨": base - (25 if rotation_fast else 0) + (15 if rhythm.stage in {"启动期", "发酵期"} else -15),
        "低吸": 70 if rhythm.stage in {"分歧期", "退潮期"} else base,
        "半路": base + (10 if rhythm.stage in {"启动期", "发酵期"} else 0),
        "打板": emotion.relay_score - emotion.failed_limit_up_count * 4,
        "趋势": base + (10 if rhythm.stage in {"发酵期", "高潮期"} else 0),
        "做T": 70 if rotation_fast or rhythm.stage == "分歧期" else 45,
        "潜伏": 65 if rhythm.stage in {"冰点期", "退潮期", "启动期"} else 35,
    }
    return {key: _stars(max(0.0, min(100.0, value))) for key, value in scores.items()}


def _forbidden_actions(
    emotion: MarketEmotion,
    rhythm: RhythmAssessment,
    mainlines: list[MainlineStats],
    risk: RiskAssessment,
    high_low_state: str,
) -> list[str]:
    actions = []
    if risk.total_score >= 55:
        actions.append("不要满仓追涨。")
    if rhythm.stage in {"高潮期", "分歧期"}:
        actions.append("不要接力三板以上高位股。")
    if emotion.failed_limit_up_count > max(emotion.limit_up_count * 0.25, 3):
        actions.append("不要追缩量涨停或炸板回封。")
    if high_low_state in {"高低切换", "快速轮动"}:
        actions.append("不要追高前一日已高潮方向。")
    if mainlines and mainlines[0].top20_count == 0:
        actions.append(f"不要只按概念追{mainlines[0].name}，需等待个股确认。")
    return actions or ["不要脱离主线做随机交易。"]


def _one_sentence(stage: str, mainlines: list[MainlineStats], emotion: MarketEmotion, position: PositionAdvice) -> str:
    leader = mainlines[0].name if mainlines else "无明确主线"
    text = f"今天市场属于{stage}，主线偏{leader}，赚钱效应{emotion.profit_effect_stars}，建议仓位{position.percent}%，优先按节奏低吸。"
    return text[:80]


def _trade_value_reason(emotion: MarketEmotion, rhythm: RhythmAssessment, mainlines: list[MainlineStats], risk: RiskAssessment) -> str:
    leader = mainlines[0].name if mainlines else "无明确主线"
    return f"主线{leader}强度{mainlines[0].strength:.0f}，市场温度{emotion.temperature:.0f}，节奏{rhythm.stage}，风险评分{risk.total_score:.0f}。" if mainlines else f"市场温度{emotion.temperature:.0f}，节奏{rhythm.stage}，风险评分{risk.total_score:.0f}。"


def _prediction_accuracy_windows(history: pd.DataFrame) -> dict[str, float]:
    return {
        "最近30天": _window_accuracy(history, 30),
        "最近60天": _window_accuracy(history, 60),
        "最近90天": _window_accuracy(history, 90),
    }


def _window_accuracy(history: pd.DataFrame, size: int) -> float:
    if history.empty or "预测是否正确" not in history:
        return 0.0
    recent = history[history["预测是否正确"].astype(str).isin(["是", "否"])].tail(size)
    if recent.empty:
        return 0.0
    return float((recent["预测是否正确"].astype(str) == "是").mean() * 100)


def _persistence_reason(strength: float, flow: float, top20_count: int) -> str:
    reasons = []
    if strength >= 75:
        reasons.append("板块强度高")
    if flow > 0:
        reasons.append("主力资金净流入")
    if top20_count:
        reasons.append(f"Top20占{top20_count}只")
    return "；".join(reasons) if reasons else "强度和资金持续性不足"


def _column_sum(frame: pd.DataFrame, names: tuple[str, ...]) -> float:
    for name in names:
        if name in frame:
            return float(pd.to_numeric(frame[name], errors="coerce").fillna(0.0).sum())
    return 0.0


def _column_max(frame: pd.DataFrame, names: tuple[str, ...]) -> float:
    for name in names:
        if name in frame:
            values = pd.to_numeric(frame[name], errors="coerce").fillna(0.0)
            return float(values.max()) if not values.empty else 0.0
    return 0.0


def _max_board_stock(frame: pd.DataFrame, height: int) -> str:
    if height <= 0:
        return "无"
    for name in ("连板高度", "连续涨停天数", "board_height"):
        if name in frame:
            values = pd.to_numeric(frame[name], errors="coerce").fillna(0.0)
            if not values.empty:
                row = frame.loc[values.idxmax()]
                return f"{row.get('名称', '')}({row.get('代码', '')})"
    limit = pd.to_numeric(frame.get("涨停标记", pd.Series(0, index=frame.index)), errors="coerce").fillna(0.0)
    if (limit == 1).any():
        row = frame.loc[limit[limit == 1].index[0]]
        return f"{row.get('名称', '')}({row.get('代码', '')})"
    return "无"


def _history_average(history: pd.DataFrame, column: str, default: float = 0.0) -> float:
    if history.empty or column not in history:
        return default
    values = pd.to_numeric(history[column], errors="coerce").dropna().tail(5)
    return float(values.mean()) if not values.empty else default


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
