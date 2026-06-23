from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


ALLOWED_CODES = [
    "600001",
    "601002",
    "603003",
    "605004",
    "000005",
    "001006",
    "002007",
    "600008",
    "601009",
    "603010",
    "605011",
    "000012",
]
FORBIDDEN_CODES = ["300001", "301001", "688001", "689001", "920001", "430001", "510300"]


class MockAkShareDataFetcher:
    """Deterministic AKShare-compatible source for offline strategy testing."""

    def __init__(self) -> None:
        self.history_requests: list[str] = []

    def market_spot(self) -> pd.DataFrame:
        rows = []
        for index, code in enumerate(ALLOWED_CODES, start=1):
            rows.append(
                {
                    "代码": code,
                    "名称": f"主板模拟{index:02d}",
                    "最新价": 10.0 + index,
                    "涨跌幅": 2.5 + index * 0.2,
                    "成交量": 2_000_000 + index * 100_000,
                    "成交额": 180_000_000 + index * 10_000_000,
                    "换手率": 4.0 + index * 0.2,
                    "流通市值": 8_000_000_000 + index * 1_000_000_000,
                }
            )
        for index, code in enumerate(FORBIDDEN_CODES, start=1):
            rows.append(
                {
                    "代码": code,
                    "名称": f"禁止标的{index:02d}",
                    "最新价": 20.0,
                    "涨跌幅": 10.0,
                    "成交量": 9_000_000,
                    "成交额": 900_000_000,
                    "换手率": 12.0,
                    "流通市值": 12_000_000_000,
                }
            )
        return pd.DataFrame(rows)

    def stock_history(self, symbol: str, end_date: date, days: int = 160) -> pd.DataFrame:
        self.history_requests.append(symbol)
        index = ALLOWED_CODES.index(symbol) + 1
        base = 9.0 + index * 0.15
        closes = [base + offset * 0.003 for offset in range(119)]
        platform_wave = [0.00, 0.16, -0.07, 0.11]
        closes.extend([base + 0.30 + platform_wave[offset % 4] for offset in range(20)])
        closes.append(base + 0.72 + index * 0.015)
        volumes = [1_000_000.0] * 139 + [3_000_000.0 + index * 60_000]
        dates = [end_date - timedelta(days=139 - offset) for offset in range(140)]
        return pd.DataFrame(
            {
                "trade_date": dates,
                "open": [value * 0.985 for value in closes],
                "high": [value * 1.015 for value in closes],
                "low": [value * 0.975 for value in closes],
                "close": closes,
                "vol": volumes,
                "amount": [value * volume * 12 for value, volume in zip(closes, volumes)],
            }
        )

    def index_history(self, symbol: str, end_date: date, days: int = 30) -> pd.DataFrame:
        closes = [3000 + offset * 1.5 for offset in range(20)]
        dates = [end_date - timedelta(days=19 - offset) for offset in range(20)]
        return pd.DataFrame({"trade_date": dates, "close": closes})

    def industry_boards(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"板块名称": "人工智能", "涨跌幅": 4.2},
                {"板块名称": "机器人", "涨跌幅": 3.1},
                {"板块名称": "银行", "涨跌幅": 0.2},
            ]
        )

    def industry_members(self, board_name: str) -> pd.DataFrame:
        if board_name == "人工智能":
            codes = ALLOWED_CODES[:6] + FORBIDDEN_CODES[:3]
        elif board_name == "机器人":
            codes = ALLOWED_CODES[6:]
        else:
            codes = []
        return pd.DataFrame([{"代码": code} for code in codes])

    def concept_boards(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"板块名称": "算力租赁", "涨跌幅": 5.5, "成交额": 120_000_000_000, "换手率": 6.8},
                {"板块名称": "低空经济", "涨跌幅": 2.8, "成交额": 80_000_000_000, "换手率": 4.2},
                {"板块名称": "中字头", "涨跌幅": 0.5, "成交额": 60_000_000_000, "换手率": 1.1},
            ]
        )

    def concept_members(self, board_name: str) -> pd.DataFrame:
        if board_name == "算力租赁":
            codes = ALLOWED_CODES[:4] + FORBIDDEN_CODES[:2]
        elif board_name == "低空经济":
            codes = ALLOWED_CODES[4:9]
        elif board_name == "中字头":
            codes = ALLOWED_CODES[9:]
        else:
            codes = []
        return pd.DataFrame([{"代码": code} for code in codes])

    def fund_flow_rank(self, indicator: str) -> pd.DataFrame:
        prefix = "今日" if indicator == "今日" else "5日"
        rows = []
        for index, code in enumerate(ALLOWED_CODES, start=1):
            rows.append(
                {
                    "代码": code,
                    f"{prefix}主力净流入-净额": 32_000_000 + index * 1_000_000,
                    f"{prefix}主力净流入-净占比": 4.0 + index * 0.1,
                    f"{prefix}大单净流入-净额": 8_000_000,
                    f"{prefix}超大单净流入-净额": 5_000_000,
                }
            )
        return pd.DataFrame(rows)

    def sector_fund_flow_rank(self, sector_type: str = "行业资金流") -> pd.DataFrame:
        if sector_type == "概念资金流":
            return pd.DataFrame(
                [
                    {"名称": "算力租赁", "今日主力净流入-净额": 1_200_000_000},
                    {"名称": "低空经济", "今日主力净流入-净额": 300_000_000},
                    {"名称": "中字头", "今日主力净流入-净额": -200_000_000},
                ]
            )
        return pd.DataFrame(
            [
                {"名称": "人工智能", "今日主力净流入-净额": 900_000_000},
                {"名称": "机器人", "今日主力净流入-净额": 600_000_000},
                {"名称": "银行", "今日主力净流入-净额": -100_000_000},
            ]
        )

    def risk_notice_codes(self, notice_date: date) -> set[str]:
        return set()
