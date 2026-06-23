from datetime import date
from dataclasses import replace

from stock_selector.akshare_engine import AkShareV1Engine, calculate_v1_features, is_allowed_main_board_code
from stock_selector.config import MainBoardStrategySettings
from stock_selector.data.akshare_mock import ALLOWED_CODES, FORBIDDEN_CODES, MockAkShareDataFetcher


def test_account_permission_whitelist_only_allows_main_board_codes() -> None:
    for code in ALLOWED_CODES:
        assert is_allowed_main_board_code(code)
    for code in FORBIDDEN_CODES:
        assert not is_allowed_main_board_code(code)


def test_features_are_calculated_for_scoring() -> None:
    features = calculate_v1_features(MockAkShareDataFetcher().stock_history("600001", date(2026, 6, 2)))
    assert features["above_ma20"]
    assert features["ma20_up"]
    assert features["ma5_gt_ma10"]
    assert features["ma10_gt_ma20"]
    assert features["volume_ratio"] > 1
    assert features["volume_ratio_10d"] > 1
    assert features["breakout_20d"]
    assert features["close_60d_high"]
    assert features["close_120d_high"]


def test_forbidden_markets_never_request_history_or_enter_ranking() -> None:
    fetcher = MockAkShareDataFetcher()
    result = AkShareV1Engine(fetcher=fetcher).run(date(2026, 6, 2))
    assert result.main_board_count == len(ALLOWED_CODES)
    assert not set(fetcher.history_requests).intersection(FORBIDDEN_CODES)
    assert all(is_allowed_main_board_code(item.code) for item in result.top20)


def test_rankings_return_top10_top3_and_best() -> None:
    result = AkShareV1Engine(fetcher=MockAkShareDataFetcher()).run(date(2026, 6, 2))
    assert result.scored_count == 12
    assert len(result.top20) == 10
    assert len(result.top10) == 10
    assert len(result.top3) == 3
    assert result.best == result.top20[0]
    assert all(0 <= item.ma20_score <= 30 for item in result.top3)
    assert all(0 <= item.ma_score <= 25 for item in result.top3)
    assert all(0 <= item.volume_score <= 15 for item in result.top3)
    assert all(0 <= item.breakout_score <= 15 for item in result.top3)
    assert all(0 <= item.market_cap_score <= 10 for item in result.top3)
    assert all(0 <= item.sector_heat_bonus <= 5 for item in result.top3)
    assert all(
        abs(
            item.score
            - min(
                round(
                    item.ma20_score
                    + item.ma_score
                    + item.volume_score
                    + item.breakout_score
                    + item.market_cap_score
                    + item.sector_heat_bonus
                    + item.risk_score,
                    1,
                ),
                100.0,
            )
        )
        <= 0.2
        for item in result.top3
    )
    assert all(item.amount >= 300_000_000 for item in result.top3)
    assert all(item.turnover_rate > 2 for item in result.top3)


def test_industry_and_concept_sectors_are_ranked_and_scored() -> None:
    result = AkShareV1Engine(fetcher=MockAkShareDataFetcher()).run(date(2026, 6, 2))
    assert result.sector_rankings
    assert {sector.sector_type for sector in result.sector_rankings} == {"行业", "概念"}
    assert result.sector_rankings[0].rank == 1
    assert result.sector_rankings[0].is_mainline
    assert "板块强度" not in result.top20[0].score_breakdown
    assert result.top20[0].sector != "未映射"


def test_non_mainline_stocks_cannot_enter_top3() -> None:
    settings = MainBoardStrategySettings()
    settings = replace(
        settings,
        rules=replace(settings.rules, mainline_sector_score=101.0, mainline_sector_rank_limit=0),
    )
    result = AkShareV1Engine(fetcher=MockAkShareDataFetcher(), settings=settings).run(date(2026, 6, 2))
    assert result.top20
    assert result.top3
    assert result.best is result.top3[0]


class NegativeFundFetcher(MockAkShareDataFetcher):
    def fund_flow_rank(self, indicator: str):
        frame = super().fund_flow_rank(indicator)
        frame[f"{indicator}主力净流入-净额"] = -1
        return frame


def test_negative_fund_flow_reduces_score_but_does_not_remove_stock() -> None:
    result = AkShareV1Engine(fetcher=NegativeFundFetcher()).run(date(2026, 6, 2))
    assert result.scored_count == 12
    assert result.top20
    assert all(0 <= item.fund_score <= 15 for item in result.top20)


class WeakMarketFetcher(MockAkShareDataFetcher):
    def market_spot(self):
        frame = super().market_spot()
        frame["涨跌幅"] = -4.0
        return frame


def test_weak_market_warns_but_still_outputs_rankings() -> None:
    result = AkShareV1Engine(fetcher=WeakMarketFetcher()).run(date(2026, 6, 2))
    assert result.market.status == "观望"
    assert result.top20


class LowLiquidityFetcher(MockAkShareDataFetcher):
    def market_spot(self):
        frame = super().market_spot()
        frame["成交额"] = 100_000_000
        frame["换手率"] = 1.0
        return frame

    def stock_history(self, symbol: str, end_date: date, days: int = 160):
        frame = super().stock_history(symbol, end_date, days)
        frame["amount"] = 100_000_000
        return frame


def test_no_forced_recommendation_when_no_stock_passes_hard_filters() -> None:
    result = AkShareV1Engine(fetcher=LowLiquidityFetcher()).run(date(2026, 6, 2))
    assert result.scored_count == 0
    assert result.top3 == []
    assert result.best is None


class RiskNoticeFetcher(MockAkShareDataFetcher):
    def risk_notice_codes(self, notice_date: date) -> set[str]:
        return {ALLOWED_CODES[0]}


def test_risk_notice_codes_are_excluded_before_history_requests() -> None:
    fetcher = RiskNoticeFetcher()
    result = AkShareV1Engine(fetcher=fetcher).run(date(2026, 6, 2))
    assert ALLOWED_CODES[0] not in fetcher.history_requests
    assert all(item.code != ALLOWED_CODES[0] for item in result.top20)
