from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import pandas as pd

from stock_selector.config import MainBoardStrategySettings
from stock_selector.data.akshare import AkShareDataFetcher
from stock_selector.market_style import MarketStyleSnapshot, analyze_market_style, classify_stock, market_style_score_adjustment


def _number(value, default: float = 0.0) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(number) else float(number)


def _rank_score(values: pd.Series) -> pd.Series:
    return values.rank(pct=True, method="average").fillna(0.0) * 100


def _ratio_score(value: float, full_score_at: float) -> float:
    return max(0.0, min(value / full_score_at, 1.0))


def _range_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min((value - low) / (high - low), 1.0))


def _unmapped_sector() -> "SectorSnapshot":
    return SectorSnapshot("未映射", "未映射", 0, 0.0, 0.0, 0.0, 0.0, False, False)


def _row_sector(row) -> "SectorSnapshot":
    sector = str(row.get("所属板块", "") or "").strip()
    if sector and sector != "nan":
        return SectorSnapshot(sector, "行业", 0, 0.0, 0.0, 0.0, 0.0, False, False)
    return _unmapped_sector()


def _threshold_label(score: float | None) -> str:
    if score is None or score < 75:
        return "今日无高确定性机会，建议空仓观察。"
    if score < 85:
        return "可观察，轻仓试错"
    return "可重点关注"


@dataclass(frozen=True)
class MarketEnvironment:
    score: float
    status: str
    allow_recommendations: bool
    up_ratio: float
    limit_up_count: int
    limit_down_count: int
    total_amount: float
    note: str
    scope: str = "未知"
    source: str = "未知"
    data_date: date | None = None
    sample_count: int = 0
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    available: bool = True
    limit_stats_available: bool = False
    limit_scope: str = ""
    limit_excluded_count: int = 0


@dataclass(frozen=True)
class SectorSnapshot:
    name: str
    sector_type: str
    rank: int
    score: float
    pct_change: float
    main_net_inflow: float
    heat_score: float
    is_mainline: bool
    flow_available: bool

    @property
    def label(self) -> str:
        return f"{self.sector_type}:{self.name}" if self.name != "未映射" else self.name


@dataclass(frozen=True)
class AkShareCandidate:
    code: str
    name: str
    sector: str
    sector_type: str
    sector_rank: int
    sector_heat_score: float
    sector_is_mainline: bool
    sector_pct_change: float
    sector_main_net_inflow: float
    score: float
    score_breakdown: dict[str, float]
    trend_score: float
    fund_score: float
    volume_score: float
    strength_score: float
    risk_penalty: float
    ma20_score: float
    ma_score: float
    breakout_score: float
    risk_score: float
    market_cap_score: float
    sector_heat_bonus: float
    close: float
    ma5: float
    ma10: float
    ma20: float
    volume_ratio: float
    turnover_rate: float
    amount: float
    breakout_margin: float
    main_net_inflow: float
    main_net_inflow_5d: float
    circulating_market_cap: float
    buy_range: str
    stop_loss: float
    first_target: float
    reasons: list[str]
    risks: list[str]
    action: str


@dataclass(frozen=True)
class AkShareSelectionResult:
    trade_date: date
    market: MarketEnvironment
    source_count: int
    main_board_count: int
    scored_count: int
    sector_count: int
    sector_rankings: list[SectorSnapshot]
    top3_candidates: list[AkShareCandidate]
    top20: list[AkShareCandidate]
    ranked_candidates: list[AkShareCandidate]
    elimination_stats: dict | None = None
    market_style: MarketStyleSnapshot | None = None

    @property
    def top10(self) -> list[AkShareCandidate]:
        return self.top20[:10]

    @property
    def top3(self) -> list[AkShareCandidate]:
        return self.top3_candidates

    @property
    def best(self) -> AkShareCandidate | None:
        top3 = self.top3
        return top3[0] if top3 else None

    @property
    def validation_top20(self) -> list[AkShareCandidate]:
        return self.ranked_candidates[:20]


def is_allowed_main_board_code(code: str, settings: MainBoardStrategySettings | None = None) -> bool:
    rules = (settings or MainBoardStrategySettings()).rules
    normalized = str(code).zfill(6)
    return len(normalized) == 6 and normalized.startswith(rules.allowed_code_prefixes)


def _feature_style_group(code: str, sector: str, features: dict) -> str:
    return_20d = float(features.get("stock_return_20d", 0.0))
    return_60d = float(features.get("stock_return_60d", 0.0))
    return_5d = float(features.get("stock_return_5d", 0.0))
    volume_ratio = float(features.get("volume_ratio", 0.0))
    if return_20d >= 0.18:
        return "高位强势股"
    if return_60d <= 0.05 and return_5d > 0.03 and volume_ratio >= 1.2:
        return "低位补涨股"
    return classify_stock(code=code, sector=sector)


def calculate_v1_features(
    bars: pd.DataFrame,
    settings: MainBoardStrategySettings | None = None,
    *,
    market_return_5d: float = 0.0,
    sector_return_10d: float = 0.0,
) -> dict[str, float | bool]:
    rules = (settings or MainBoardStrategySettings()).rules
    if len(bars) < 121:
        raise ValueError("at least 121 daily bars are required")
    df = bars.sort_values("trade_date").reset_index(drop=True).copy()
    for column in ("open", "high", "low", "close", "vol", "amount"):
        df[column] = pd.to_numeric(df[column], errors="raise")
    if "turnover_rate" in df:
        df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce").fillna(0.0)
    else:
        df["turnover_rate"] = 0.0
    if "is_st" in df:
        df["is_st"] = pd.to_numeric(df["is_st"], errors="coerce").fillna(0).astype(int)
    else:
        df["is_st"] = 0
    close = df["close"]
    vol = df["vol"]
    latest = df.iloc[-1]
    pct = close.pct_change()
    ma5 = float(close.tail(5).mean())
    ma10 = float(close.tail(10).mean())
    ma20 = float(close.tail(20).mean())
    previous_ma20 = float(close.iloc[-21:-1].mean())
    average_volume_5d = float(vol.iloc[-6:-1].mean())
    average_volume_10d = float(vol.iloc[-11:-1].mean())
    volume_ratio = float(vol.iloc[-1] / average_volume_5d) if average_volume_5d else 0.0
    volume_ratio_10d = float(vol.iloc[-1] / average_volume_10d) if average_volume_10d else 0.0
    prior_high_20d = float(df["high"].iloc[-rules.breakout_lookback - 1 : -1].max())
    latest_close = float(latest["close"])
    ma_gap = (ma5 - ma10) / ma10 if ma10 else -1.0
    volatility_20d = float(pct.tail(20).abs().mean())
    stock_return_5d = (latest_close / float(close.iloc[-6]) - 1) if float(close.iloc[-6]) else 0.0
    stock_return_10d = (latest_close / float(close.iloc[-11]) - 1) if float(close.iloc[-11]) else 0.0
    stock_return_20d = (latest_close / float(close.iloc[-21]) - 1) if len(close) >= 21 and float(close.iloc[-21]) else 0.0
    stock_return_60d = (latest_close / float(close.iloc[-61]) - 1) if len(close) >= 61 and float(close.iloc[-61]) else 0.0
    high_close_60d = float(close.tail(60).max())
    high_close_120d = float(close.tail(120).max())
    consecutive_limit_up = 0
    for value in reversed(pct.fillna(0.0).tail(10).tolist()):
        if value >= 0.095:
            consecutive_limit_up += 1
            continue
        break
    direction = (close.diff().fillna(0.0) >= 0).map({True: 1, False: -1})
    obv = (direction * vol).cumsum()
    latest_obv = float(obv.iloc[-1])
    prior_obv_5d = float(obv.iloc[-6]) if len(obv) >= 6 else float(obv.iloc[0])
    obv_high_60d = float(obv.iloc[-60:].max())
    latest_open = float(latest["open"])
    latest_high = float(latest["high"])
    latest_low = float(latest["low"])
    daily_range = latest_high - latest_low
    upper_shadow = latest_high - max(latest_open, latest_close)
    return {
        "close": latest_close,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "above_ma20": latest_close > ma20,
        "ma20_up": ma20 > previous_ma20,
        "ma20_slope": (ma20 / previous_ma20 - 1) if previous_ma20 else 0.0,
        "ma5_gt_ma10": ma5 > ma10,
        "ma10_gt_ma20": ma10 > ma20,
        "ma_cross_gap": ma_gap,
        "ma_cross_ready": ma_gap >= -rules.ma_cross_gap_max,
        "volume_ratio": volume_ratio,
        "volume_ratio_10d": volume_ratio_10d,
        "volume_breakout": volume_ratio >= rules.volume_ratio_min,
        "prior_high_20d": prior_high_20d,
        "breakout_20d": latest_close > prior_high_20d,
        "breakout_margin": (latest_close / prior_high_20d - 1) if prior_high_20d else 0.0,
        "close_60d_high": latest_close >= high_close_60d,
        "close_120d_high": latest_close >= high_close_120d,
        "stock_return_5d": stock_return_5d,
        "stock_return_10d": stock_return_10d,
        "stock_return_20d": stock_return_20d,
        "stock_return_60d": stock_return_60d,
        "beats_market_5d": stock_return_5d > market_return_5d,
        "beats_sector_10d": stock_return_10d > sector_return_10d,
        "recent_10d_return": stock_return_10d,
        "consecutive_limit_up": consecutive_limit_up,
        "obv_up": latest_obv > prior_obv_5d,
        "obv_new_high": float(obv.iloc[-1]) >= float(obv.iloc[-60:].max()),
        "obv_near_high": latest_obv >= obv_high_60d * 0.95 if obv_high_60d > 0 else latest_obv >= obv_high_60d,
        "average_amount_5d": float(df["amount"].tail(5).mean()),
        "latest_amount": float(df["amount"].iloc[-1]),
        "latest_turnover_rate": float(df["turnover_rate"].iloc[-1]),
        "latest_is_st": int(df["is_st"].iloc[-1]),
        "volatility_20d": volatility_20d,
        "limit_up_gene": float((pct.tail(60) >= 0.095).sum()),
        "long_upper_shadow": (upper_shadow / daily_range) if daily_range > 0 else 0.0,
        "daily_pct": float(pct.iloc[-1]) if not pd.isna(pct.iloc[-1]) else 0.0,
        "close_position_120d": (latest_close / high_close_120d) if high_close_120d else 0.0,
        "high_close_60d": high_close_60d,
        "high_close_120d": high_close_120d,
    }


class AkShareV1Engine:
    def __init__(
        self,
        fetcher: AkShareDataFetcher | None = None,
        *,
        sector_member_limit: int = 20,
        settings: MainBoardStrategySettings | None = None,
    ) -> None:
        self.fetcher = fetcher or AkShareDataFetcher()
        self.sector_member_limit = sector_member_limit
        self.settings = settings or MainBoardStrategySettings()

    @staticmethod
    def _risk_name(name: str) -> bool:
        normalized = name.upper()
        return (
            normalized.startswith(("*ST", "ST"))
            or "退" in name
            or "ETF" in normalized
            or "基金" in name
        )

    def run(self, trade_date: date, *, limit: int | None = None) -> AkShareSelectionResult:
        spot = self.fetcher.market_spot()
        market = self._market_environment(spot)
        risk_notice_codes = self._risk_notice_codes(trade_date)
        codes = spot["代码"].astype("object").map(str)
        names = spot["名称"].astype("object").map(str)
        allowed_code_mask = codes.map(lambda code: is_allowed_main_board_code(code, self.settings)).astype(bool)
        risk_name_mask = names.map(self._risk_name).astype(bool)
        risk_notice_mask = codes.map(lambda code: str(code).zfill(6) in risk_notice_codes).astype(bool)
        main_board = spot[allowed_code_mask & ~risk_name_mask & ~risk_notice_mask]
        sectors, stock_sectors = self._load_sectors()
        funds = self._load_funds()
        market_return_5d = self._market_return_5d(trade_date)
        universe = self._prioritize_scoring_universe(main_board, stock_sectors, funds, limit)
        elimination_stats = {
            "source_count": len(spot),
            "main_board_count": len(main_board),
            "scoring_universe_count": len(universe),
            "feature_valid_count": 0,
            "feature_invalid_count": 0,
            "feature_invalid_reasons": {},
            "hard_filter_failed": {},
            "final_count": 0,
        }
        candidates = []
        feature_rows = []
        for _, row in universe.iterrows():
            code = str(row["代码"]).zfill(6)
            sector = stock_sectors.get(code, _row_sector(row))
            try:
                bars = self.fetcher.stock_history(code, trade_date, days=160)
                features = calculate_v1_features(
                    bars,
                    self.settings,
                    market_return_5d=market_return_5d,
                    sector_return_10d=sector.pct_change / 100,
                )
            except Exception as exc:
                elimination_stats["feature_invalid_count"] += 1
                reason = f"{type(exc).__name__}: {exc}"
                failed_features = elimination_stats["feature_invalid_reasons"]
                failed_features[reason] = failed_features.get(reason, 0) + 1
                continue
            elimination_stats["feature_valid_count"] += 1
            code = str(row["代码"]).zfill(6)
            sector = stock_sectors.get(code, _row_sector(row))
            feature_rows.append(
                {
                    "code": code,
                    "sector": sector.name,
                    "return_5d": float(features.get("stock_return_5d", 0.0)),
                    "return_10d": float(features.get("stock_return_10d", 0.0)),
                    "return_20d": float(features.get("stock_return_20d", 0.0)),
                    "return_60d": float(features.get("stock_return_60d", 0.0)),
                    "volume_ratio": float(features.get("volume_ratio", 0.0)),
                    "style_group": _feature_style_group(code, sector.name, features),
                }
            )
            rejection_reason = self._candidate_rejection_reason(row, features)
            if rejection_reason:
                failed = elimination_stats["hard_filter_failed"]
                failed[rejection_reason] = failed.get(rejection_reason, 0) + 1
                continue
            candidate = self._candidate(row, features, sector, funds.get(code, {}), market)
            if candidate is not None:
                candidates.append(candidate)
        market_style = self._market_style(trade_date, spot, feature_rows)
        ranked = self._apply_market_style_adjustment(
            self._apply_sector_heat_bonus(sorted(candidates, key=lambda item: item.score, reverse=True)),
            market_style,
        )
        elimination_stats["final_count"] = len(ranked)
        if hasattr(self.fetcher, "history_source_name"):
            elimination_stats["history_source"] = getattr(self.fetcher, "history_source_name", "") or "未知"
        if hasattr(self.fetcher, "history_stats"):
            elimination_stats.update(getattr(self.fetcher, "history_stats", {}))
        sector_rankings = sorted(sectors.values(), key=lambda item: item.rank or 999_999)
        return AkShareSelectionResult(
            trade_date,
            market,
            len(spot),
            len(main_board),
            len(ranked),
            len(sectors),
            sector_rankings,
            ranked[: self.settings.rules.top_n_candidates],
            ranked[: self.settings.rules.top_n_pool],
            ranked,
            elimination_stats,
            market_style,
        )

    def _apply_sector_heat_bonus(self, ranked: list[AkShareCandidate]) -> list[AkShareCandidate]:
        sector_counts: dict[str, int] = {}
        for item in ranked[:50]:
            if item.sector == "未映射":
                continue
            sector_counts[item.sector] = sector_counts.get(item.sector, 0) + 1
        adjusted = []
        for item in ranked:
            heat = min(sector_counts.get(item.sector, 0) / 8.0, 1.0) * 5.0
            breakdown = dict(item.score_breakdown)
            breakdown["板块热度"] = round(heat, 1)
            adjusted.append(
                replace(
                    item,
                    score=round(min(item.score + heat, 100.0), 1),
                    score_breakdown=breakdown,
                    sector_heat_bonus=round(heat, 2),
                )
            )
        return sorted(adjusted, key=lambda item: item.score, reverse=True)

    def _apply_market_style_adjustment(
        self,
        ranked: list[AkShareCandidate],
        market_style: MarketStyleSnapshot | None,
    ) -> list[AkShareCandidate]:
        adjusted = []
        for item in ranked:
            delta, reason = market_style_score_adjustment(
                market_style,
                code=item.code,
                sector=item.sector,
                score=item.score,
            )
            if not delta:
                adjusted.append(item)
                continue
            breakdown = dict(item.score_breakdown)
            breakdown["市场风格调整"] = round(delta, 1)
            risks = list(item.risks)
            reasons = list(item.reasons)
            if delta < 0:
                risks.append(reason)
            else:
                reasons.append(reason)
            new_score = round(max(0.0, min(100.0, item.score + delta)), 1)
            adjusted.append(
                replace(
                    item,
                    score=new_score,
                    score_breakdown=breakdown,
                    risks=risks,
                    reasons=reasons,
                    action=_threshold_label(new_score),
                )
            )
        return sorted(adjusted, key=lambda item: item.score, reverse=True)

    def _market_style(self, trade_date: date, spot: pd.DataFrame, feature_rows: list[dict]) -> MarketStyleSnapshot | None:
        try:
            market_spot = self.fetcher.full_market_spot() if hasattr(self.fetcher, "full_market_spot") else spot
        except Exception:
            market_spot = spot
        try:
            return analyze_market_style(
                trade_date=trade_date,
                fetcher=self.fetcher,
                market_spot=market_spot,
                feature_rows=feature_rows,
            )
        except Exception:
            return None

    def _market_return_5d(self, trade_date: date) -> float:
        try:
            index = self.fetcher.index_history("sh000001", trade_date, days=30)
            close = pd.to_numeric(index["close"], errors="coerce").dropna()
            if len(close) >= 6 and float(close.iloc[-6]):
                return float(close.iloc[-1] / close.iloc[-6] - 1)
        except Exception:
            pass
        return 0.0

    def _risk_notice_codes(self, trade_date: date) -> set[str]:
        try:
            return set(self.fetcher.risk_notice_codes(trade_date))
        except Exception:
            return set()

    def _prioritize_scoring_universe(self, main_board, stock_sectors, funds, limit):
        """Prioritize likely short-term candidates before slow daily-bar requests."""
        frame = main_board.copy()
        frame["_fund"] = frame["代码"].astype(str).map(
            lambda code: _number(funds.get(str(code).zfill(6), {}).get("main_net_inflow"))
        )
        frame["_sector"] = frame["代码"].astype(str).map(
            lambda code: stock_sectors.get(str(code).zfill(6), _unmapped_sector()).score
        )
        turnover = frame["换手率"] if "换手率" in frame else pd.Series(0.0, index=frame.index)
        frame["_turnover"] = pd.to_numeric(turnover, errors="coerce").fillna(0.0)
        frame["_snapshot_score"] = (
            0.45 * _rank_score(frame["_fund"])
            + 0.35 * _rank_score(frame["_sector"])
            + 0.20 * _rank_score(frame["_turnover"])
        )
        requested = limit or (len(frame) if getattr(self.fetcher, "prefer_full_universe", False) else self.settings.rules.scoring_universe_limit)
        return frame.sort_values("_snapshot_score", ascending=False).head(requested)

    def _market_environment(self, spot: pd.DataFrame) -> MarketEnvironment:
        try:
            if not hasattr(self.fetcher, "full_market_spot"):
                raise RuntimeError("fetcher does not provide full-market spot data")
            market_spot = self.fetcher.full_market_spot()
        except Exception as exc:
            return MarketEnvironment(
                0.0,
                "未知",
                True,
                0.0,
                0,
                0,
                0.0,
                f"大盘概况获取失败：{type(exc).__name__}: {exc}",
                available=False,
            )
        pct = pd.to_numeric(market_spot.get("涨跌幅", pd.Series(dtype=float)), errors="coerce").dropna()
        amount = pd.to_numeric(market_spot.get("成交额", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        if pct.empty or amount.empty:
            return MarketEnvironment(
                0.0,
                "未知",
                True,
                0.0,
                0,
                0,
                0.0,
                "大盘概况获取失败：全A股行情缺少涨跌幅或成交额",
                available=False,
            )
        up_count = int((pct > 0).sum())
        down_count = int((pct < 0).sum())
        flat_count = int((pct == 0).sum())
        up_ratio = float((pct > 0).mean()) if not pct.empty else 0.0
        limit_up_count = 0
        limit_down_count = 0
        limit_stats_available = False
        limit_scope = ""
        limit_excluded_count = 0
        if {"涨停标记", "跌停标记"}.issubset(market_spot.columns):
            limit_up = pd.to_numeric(market_spot["涨停标记"], errors="coerce")
            limit_down = pd.to_numeric(market_spot["跌停标记"], errors="coerce")
            valid_limit = limit_up.notna() & limit_down.notna()
            if valid_limit.any():
                limit_stats_available = True
                limit_up_count = int((limit_up[valid_limit] == 1).sum())
                limit_down_count = int((limit_down[valid_limit] == 1).sum())
                limit_excluded_count = int((~valid_limit).sum())
                limit_scope = "沪深A股；按涨跌停价计算；主板10%，创业板/科创板20%，ST/*ST 5%；排除北交所"
        average_pct = float(pct.mean()) if not pct.empty else -10.0
        score = max(0.0, min(100.0, up_ratio * 45 + min(limit_up_count / max(len(pct) * 0.012, 1), 1) * 25 + max(min((average_pct + 2.0) / 4.0, 1), 0) * 20 + max(0.0, 10 - min(limit_down_count, 10))))
        status = "观望" if score < 35 else ("谨慎" if score < 55 else "可交易")
        return MarketEnvironment(
            round(score, 2), status, True, up_ratio, limit_up_count, limit_down_count, float(amount.sum()),
            "全A股市场环境，仅作为风险提示，不再阻止评分输出。",
            scope="全A股",
            source=str(getattr(self.fetcher, "data_source_name", "") or "实时行情"),
            data_date=getattr(self.fetcher, "trade_date", None),
            sample_count=len(pct),
            up_count=up_count,
            down_count=down_count,
            flat_count=flat_count,
            available=True,
            limit_stats_available=limit_stats_available,
            limit_scope=limit_scope,
            limit_excluded_count=limit_excluded_count,
        )

    def _load_funds(self) -> dict[str, dict[str, float]]:
        today = self.fetcher.fund_flow_rank("今日")
        five_day = self.fetcher.fund_flow_rank("5日")
        funds: dict[str, dict[str, float]] = {}
        for _, row in today.iterrows():
            code = str(row["代码"]).zfill(6)
            funds.setdefault(code, {}).update(
                {
                    "main_net_inflow": _number(row.get("今日主力净流入-净额")),
                    "main_net_ratio": _number(row.get("今日主力净流入-净占比")),
                }
            )
        for _, row in five_day.iterrows():
            funds.setdefault(str(row["代码"]).zfill(6), {}).update(
                {"main_net_inflow_5d": _number(row.get("5日主力净流入-净额"))}
            )
        return funds

    def _load_sectors(self) -> tuple[dict[str, SectorSnapshot], dict[str, SectorSnapshot]]:
        industry = self._sector_frame(
            self.fetcher.industry_boards(),
            self.fetcher.sector_fund_flow_rank("行业资金流"),
            "行业",
        )
        concept = self._sector_frame(
            self.fetcher.concept_boards(),
            self.fetcher.sector_fund_flow_rank("概念资金流"),
            "概念",
        )
        frame = pd.concat([industry, concept], ignore_index=True)
        if frame.empty:
            return {}, {}
        frame = frame.sort_values("score", ascending=False).reset_index(drop=True)
        frame["rank"] = frame.index + 1
        rules = self.settings.rules
        frame["is_mainline"] = frame["has_signal"] & (
            (frame["score"] >= rules.mainline_sector_score)
            | (frame["rank"] <= rules.mainline_sector_rank_limit)
        )
        sectors = {
            f"{row['sector_type']}:{row['name']}": SectorSnapshot(
                str(row["name"]),
                str(row["sector_type"]),
                int(row["rank"]),
                round(float(row["score"]), 2),
                float(row["pct_change"]),
                float(row["main_net_inflow"]),
                round(float(row["heat_score"]), 2),
                bool(row["is_mainline"]),
                bool(row["flow_available"]),
            )
            for _, row in frame.iterrows()
        }
        stocks: dict[str, SectorSnapshot] = {}
        for sector in sorted(sectors.values(), key=lambda item: item.score, reverse=True)[: self.sector_member_limit]:
            try:
                members = (
                    self.fetcher.industry_members(sector.name)
                    if sector.sector_type == "行业"
                    else self.fetcher.concept_members(sector.name)
                )
            except Exception:
                continue
            for _, member in members.iterrows():
                code = str(member["代码"]).zfill(6)
                if not is_allowed_main_board_code(code, self.settings):
                    continue
                existing = stocks.get(code)
                if existing is None or sector.score > existing.score:
                    stocks[code] = sector
        return sectors, stocks

    def _sector_frame(self, boards: pd.DataFrame, flow: pd.DataFrame, sector_type: str) -> pd.DataFrame:
        if boards.empty:
            return pd.DataFrame(
                columns=[
                    "name",
                    "sector_type",
                    "pct_change",
                    "main_net_inflow",
                    "heat_score",
                    "score",
                    "flow_available",
                    "has_signal",
                ]
            )
        frame = boards.copy()
        name_column = "板块名称" if "板块名称" in frame else ("名称" if "名称" in frame else frame.columns[0])
        frame["name"] = frame[name_column].astype(str)
        pct_change = frame["涨跌幅"] if "涨跌幅" in frame else pd.Series(0.0, index=frame.index)
        frame["pct_change"] = pd.to_numeric(pct_change, errors="coerce").fillna(0.0)
        flow_name_column = "名称" if "名称" in flow else ("行业" if "行业" in flow else None)
        if flow_name_column is not None and not flow.empty:
            flow_map = {
                str(row.get(flow_name_column)): _number(row.get("今日主力净流入-净额"))
                for _, row in flow.iterrows()
            }
        else:
            flow_map = {}
        frame["main_net_inflow"] = frame["name"].map(flow_map).fillna(0.0)
        amount_source = frame["成交额"] if "成交额" in frame else pd.Series(0.0, index=frame.index)
        turnover_source = frame["换手率"] if "换手率" in frame else pd.Series(0.0, index=frame.index)
        amount = pd.to_numeric(amount_source, errors="coerce").fillna(0.0)
        turnover = pd.to_numeric(turnover_source, errors="coerce").fillna(0.0)
        pct_rank = _rank_score(frame["pct_change"]) if frame["pct_change"].abs().sum() > 0 else pd.Series(0.0, index=frame.index)
        flow_rank = (
            _rank_score(frame["main_net_inflow"])
            if frame["main_net_inflow"].abs().sum() > 0
            else pd.Series(0.0, index=frame.index)
        )
        amount_rank = _rank_score(amount) if amount.abs().sum() > 0 else pd.Series(0.0, index=frame.index)
        turnover_rank = _rank_score(turnover) if turnover.abs().sum() > 0 else pd.Series(0.0, index=frame.index)
        frame["heat_score"] = (0.5 * pct_rank + 0.3 * amount_rank + 0.2 * turnover_rank).fillna(0.0)
        frame["score"] = (
            0.40 * pct_rank
            + 0.35 * flow_rank
            + 0.25 * frame["heat_score"]
        )
        frame["has_signal"] = (
            (frame["pct_change"].abs() > 0)
            | (frame["main_net_inflow"].abs() > 0)
            | (amount.abs() > 0)
            | (turnover.abs() > 0)
        )
        frame["sector_type"] = sector_type
        frame["flow_available"] = not flow.empty
        return frame[
            [
                "name",
                "sector_type",
                "pct_change",
                "main_net_inflow",
                "heat_score",
                "score",
                "flow_available",
                "has_signal",
            ]
        ]

    def _candidate(self, spot, features, sector, fund, market) -> AkShareCandidate | None:
        rules = self.settings.rules
        turnover = _number(spot.get("换手率"))
        if not turnover:
            turnover = _number(spot.get("turnover_rate"))
        if not turnover:
            turnover = float(features.get("latest_turnover_rate", 0.0))
        amount = max(_number(spot.get("成交额")), float(features["latest_amount"]))
        close = float(features["close"])
        ma20 = float(features["ma20"])
        market_cap = _number(spot.get("流通市值"))
        if not market_cap and hasattr(self.fetcher, "market_cap"):
            try:
                market_cap = float(self.fetcher.market_cap(str(spot["代码"]).zfill(6), close))
            except Exception:
                market_cap = 0.0
        fund_inflow = _number(fund.get("main_net_inflow"))
        fund_5d = _number(fund.get("main_net_inflow_5d"))

        if int(features["consecutive_limit_up"]) >= 3:
            return None
        if int(features.get("latest_is_st", 0)):
            return None
        if float(features["recent_10d_return"]) > rules.max_10d_return:
            return None
        if amount < rules.min_daily_amount:
            return None
        if turnover < rules.min_turnover_rate:
            return None
        if close < ma20 * rules.min_close_vs_ma20:
            return None
        if float(features["ma20_slope"]) < rules.max_ma20_down_slope:
            return None
        if float(features["average_amount_5d"]) < rules.min_average_amount_5d:
            return None

        close_ma20_gap = close / ma20 - 1 if ma20 else 0.0
        ma5 = float(features["ma5"])
        ma10 = float(features["ma10"])
        ma20_score = 15.0 * _range_score(close_ma20_gap, -0.02, 0.08)
        ma20_slope_score = 15.0 * _range_score(float(features["ma20_slope"]), -0.002, 0.018)
        ma5_ma10_gap = ma5 / ma10 - 1 if ma10 else 0.0
        ma10_ma20_gap = ma10 / ma20 - 1 if ma20 else 0.0
        ma_score = (
            12.5 * _range_score(ma5_ma10_gap, -0.005, 0.035)
            + 12.5 * _range_score(ma10_ma20_gap, -0.005, 0.05)
        )
        volume_score = (
            5.0 * _range_score(float(features["volume_ratio"]), 0.8, 2.5)
            + 5.0 * _range_score(float(features["volume_ratio_10d"]), 0.8, 2.8)
            + 3.0 * _range_score(amount, rules.min_daily_amount, 1_500_000_000)
            + 2.0 * _range_score(turnover, rules.min_turnover_rate, 10.0)
        )
        high60 = float(features["high_close_60d"])
        high120 = float(features["high_close_120d"])
        high20 = float(features["prior_high_20d"])
        breakout_score = (
            4.0 * _range_score((close / high20 - 1) if high20 else -1.0, -0.03, 0.08)
            + 4.5 * _range_score((close / high60 - 1) if high60 else -1.0, -0.03, 0.06)
            + 4.5 * _range_score((close / high120 - 1) if high120 else -1.0, -0.03, 0.06)
            + 2.0 * _range_score(float(features["stock_return_5d"]) - 0.0, -0.02, 0.12)
        )
        fund_score = (
            5.0 * _range_score(1.0 if bool(features["obv_up"]) else 0.0, 0.0, 1.0)
            + 5.0 * _range_score(1.0 if (bool(features["obv_near_high"]) or bool(features["obv_new_high"])) else 0.0, 0.0, 1.0)
            + 5.0 * _range_score((close / high20 - 1) if high20 else -1.0, -0.02, 0.06)
        )
        if market_cap >= 80_000_000_000:
            market_cap_score = 10.0
        elif market_cap >= 30_000_000_000:
            market_cap_score = 6.0
        elif market_cap >= 10_000_000_000:
            market_cap_score = 3.0
        else:
            market_cap_score = 0.0
        trend_score = ma20_score + ma20_slope_score + ma_score
        strength_score = breakout_score
        risk_items = {
            "最近10日涨幅过大": max(0.0, min((float(features["recent_10d_return"]) - 0.30) / 0.50, 1.0)) * 10.0,
            "距离20日均线过远": max(0.0, min((close_ma20_gap - 0.12) / 0.18, 1.0)) * 10.0,
            "连续涨停风险": _ratio_score(float(features["consecutive_limit_up"]), 3.0) * 8.0,
            "当日长上影线明显": _range_score(float(features["long_upper_shadow"]), 0.30, 0.65) * 10.0,
            "当日放量滞涨": (
                _range_score(float(features["volume_ratio"]), 1.5, 3.0)
                * _range_score(0.025 - float(features["daily_pct"]), 0.0, 0.04)
                * 10.0
            ),
            "成交额偏低": max(0.0, min((500_000_000 - amount) / 200_000_000, 1.0)) * 5.0,
            "波动异常": max(0.0, min((float(features["volatility_20d"]) - 0.045) / 0.06, 1.0)) * 5.0,
            "大盘状态较弱": 5.0 if market.status == "观望" else (2.0 if market.status == "谨慎" else 0.0),
        }
        risk_penalty = sum(risk_items.values())
        score = max(0.0, min(100.0, trend_score + volume_score + breakout_score + market_cap_score - risk_penalty))
        breakdown = {
            "MA20评分": ma20_score + ma20_slope_score,
            "均线评分": ma_score,
            "量能评分": volume_score,
            "突破评分": breakout_score,
            "市值评分": market_cap_score,
            "板块热度": 0.0,
            "资金评分": fund_score,
            "风险扣分": -risk_penalty,
        }
        passed_items = []
        if close >= ma20:
            passed_items.append(f"收盘价高于20日均线{close_ma20_gap:.1%}")
        if ma5 > ma10 > ma20:
            passed_items.append(f"均线多头排列，MA5/MA10距离{ma5_ma10_gap:.1%}，MA10/MA20距离{ma10_ma20_gap:.1%}")
        if float(features["volume_ratio"]) > 1:
            passed_items.append(f"成交量为5日均量{float(features['volume_ratio']):.2f}倍")
        if float(features["volume_ratio_10d"]) > 1:
            passed_items.append(f"成交量为10日均量{float(features['volume_ratio_10d']):.2f}倍")
        if close >= high20:
            passed_items.append("突破近20日高点")
        if close >= high60:
            passed_items.append("接近或突破近60日高点")
        if close >= high120:
            passed_items.append("接近或突破近120日高点")
        if bool(features["obv_up"]):
            passed_items.append("OBV趋势向上")
        if bool(features["obv_near_high"]) or bool(features["obv_new_high"]):
            passed_items.append("OBV接近或创阶段新高")
        reasons = passed_items
        if sector.name != "未映射":
            reasons.append(f"{sector.sector_type}{sector.name}热度评分{sector.heat_score:.2f}")
        risks = [f"{key}扣{value:.1f}分" for key, value in risk_items.items() if value > 0]
        if market.status != "可交易":
            risks.append(f"市场状态为{market.status}，建议降低仓位")
        if not hasattr(self.fetcher, "risk_notice_codes"):
            risks.append("公告重大风险提示需在交易前复核")
        buy_low = close * 0.985
        buy_high = close * 1.015
        stop_loss = min(float(features["ma20"]) * 0.985, close * 0.94)
        first_target = close * 1.08
        action = _threshold_label(score)
        return AkShareCandidate(
            str(spot["代码"]).zfill(6), str(spot["名称"]), sector.name, sector.sector_type, sector.rank,
            sector.heat_score, sector.is_mainline, sector.pct_change, sector.main_net_inflow,
            round(score, 1), {key: round(value, 1) for key, value in breakdown.items()},
            round(trend_score, 2), round(fund_score, 2), round(volume_score, 2),
            round(strength_score, 2), round(risk_penalty, 2),
            round(ma20_score + ma20_slope_score, 2), round(ma_score, 2), round(breakout_score, 2), round(-risk_penalty, 2),
            round(market_cap_score, 2), 0.0,
            float(features["close"]), float(features["ma5"]), float(features["ma10"]), float(features["ma20"]),
            float(features["volume_ratio"]), turnover, amount, float(features["breakout_margin"]), fund_inflow, fund_5d,
            market_cap, f"{buy_low:.2f} - {buy_high:.2f}", round(stop_loss, 2), round(first_target, 2),
            reasons, risks,
            action,
        )

    def _candidate_rejection_reason(self, spot, features) -> str | None:
        rules = self.settings.rules
        turnover = _number(spot.get("换手率"))
        if not turnover:
            turnover = _number(spot.get("turnover_rate"))
        if not turnover:
            turnover = float(features.get("latest_turnover_rate", 0.0))
        amount = max(_number(spot.get("成交额")), float(features["latest_amount"]))
        close = float(features["close"])
        ma20 = float(features["ma20"])
        if int(features["consecutive_limit_up"]) >= 3:
            return "连续涨停>=3"
        if int(features.get("latest_is_st", 0)):
            return "ST标记"
        if float(features["recent_10d_return"]) > rules.max_10d_return:
            return "近10日涨幅>80%"
        if amount < rules.min_daily_amount:
            return "当日成交额<3亿元"
        if turnover < rules.min_turnover_rate:
            return "换手率<2%"
        if close < ma20 * rules.min_close_vs_ma20:
            return "收盘价<MA20*0.98"
        if float(features["ma20_slope"]) < rules.max_ma20_down_slope:
            return "MA20斜率<-1%"
        if float(features["average_amount_5d"]) < rules.min_average_amount_5d:
            return "5日均成交额<8000万"
        return None
