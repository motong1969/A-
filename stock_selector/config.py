from dataclasses import dataclass, field


@dataclass(frozen=True)
class MainBoardTradingRules:
    """Permanent account and strategy rules for the AKShare short-term engine."""

    allowed_code_prefixes: tuple[str, ...] = ("600", "601", "603", "605", "000", "001", "002")
    ma_cross_gap_max: float = 0.015
    volume_ratio_min: float = 1.5
    breakout_lookback: int = 20
    big_bearish_pct: float = -0.045
    max_consecutive_big_bearish: int = 1
    high_volume_stall_ratio: float = 2.0
    high_volume_stall_pct: float = 0.015
    high_position_60d: float = 0.88
    min_close_to_high: float = 0.97
    min_average_amount_5d: float = 80_000_000
    min_turnover_rate: float = 2.0
    preferred_turnover_rate: float = 3.0
    min_daily_amount: float = 300_000_000
    preferred_daily_amount: float = 500_000_000
    max_10d_return: float = 0.80
    hot_10d_return: float = 0.50
    min_close_vs_ma20: float = 0.98
    max_ma20_down_slope: float = -0.01
    max_close_vs_ma20: float = 1.20
    long_upper_shadow_ratio: float = 0.45
    min_volatility_20d: float = 0.012
    preferred_circulating_market_cap_min: float = 5_000_000_000
    preferred_circulating_market_cap_max: float = 50_000_000_000
    secondary_circulating_market_cap_max: float = 100_000_000_000
    excluded_sector_keywords: tuple[str, ...] = ("银行", "保险")
    min_sector_score: float = 45.0
    mainline_sector_score: float = 70.0
    mainline_sector_rank_limit: int = 5
    scoring_universe_limit: int = 300
    top_n_pool: int = 10
    top_n_candidates: int = 3


@dataclass(frozen=True)
class MainBoardScoreWeights:
    above_ma20: float = 15.0
    ma_cross_ready: float = 12.0
    volume: float = 12.0
    breakout: float = 12.0
    fund_flow: float = 12.0
    sector_strength: float = 30.0
    activity: float = 7.0


@dataclass(frozen=True)
class MainBoardStrategySettings:
    rules: MainBoardTradingRules = field(default_factory=MainBoardTradingRules)
    weights: MainBoardScoreWeights = field(default_factory=MainBoardScoreWeights)
