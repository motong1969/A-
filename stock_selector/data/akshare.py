from __future__ import annotations

from datetime import date, timedelta
import time
from typing import Any

import pandas as pd


class AkShareDataFetcher:
    """Thin wrapper around AKShare Eastmoney A-share endpoints."""

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self.client = client
            return
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: python3 -m pip install -e .") from exc
        self.client = ak

    def market_spot(self) -> pd.DataFrame:
        snapshots = []
        errors = []
        for attempt in range(3):
            try:
                frame = self.client.stock_zh_a_spot_em().copy()
                snapshots.append(frame)
                if len(frame) >= 1_000:
                    break
            except Exception as exc:
                errors.append(str(exc))
            time.sleep(attempt + 1)
        if not snapshots or max(len(frame) for frame in snapshots) < 1_000:
            for attempt in range(3):
                try:
                    frame = self.client.stock_zh_a_spot().copy()
                    frame["代码"] = frame["代码"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True)
                    snapshots.append(frame)
                    if len(frame) >= 1_000:
                        break
                except Exception as exc:
                    errors.append(str(exc))
                time.sleep(attempt + 1)
            if not snapshots:
                raise RuntimeError(f"AKShare market snapshot failed after retries: {errors[-1] if errors else 'unknown error'}")
        frame = max(snapshots, key=len)
        if len(frame) < 1_000:
            raise RuntimeError(f"AKShare market snapshot is incomplete: only {len(frame)} stocks returned")
        return frame

    def stock_history(self, symbol: str, end_date: date, days: int = 120) -> pd.DataFrame:
        start_date = end_date - timedelta(days=days * 2)
        try:
            frame = self.client.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="",
                timeout=8,
            ).copy()
        except Exception:
            return pd.DataFrame()
        if frame.empty:
            return frame
        return frame.rename(
            columns={
                "日期": "trade_date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "vol",
                "成交额": "amount",
                "换手率": "turnover_rate",
                "date": "trade_date",
                "volume": "vol",
            }
        ).sort_values("trade_date").reset_index(drop=True)

    def index_history(self, symbol: str, end_date: date, days: int = 30) -> pd.DataFrame:
        start_date = end_date - timedelta(days=days * 2)
        try:
            frame = self.client.stock_zh_index_daily_em(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            ).copy()
        except Exception:
            frame = self.client.stock_zh_index_daily(symbol=symbol).copy()
            if "date" in frame:
                frame = frame[frame["date"] <= end_date.isoformat()]
        if frame.empty:
            return frame
        return frame.rename(
            columns={
                "日期": "trade_date",
                "date": "trade_date",
                "收盘": "close",
            }
        ).sort_values("trade_date").reset_index(drop=True)

    def industry_boards(self) -> pd.DataFrame:
        try:
            return self.client.stock_board_industry_name_em().copy()
        except Exception:
            try:
                frame = self.client.stock_board_industry_name_ths().copy()
                return frame.rename(columns={"name": "板块名称", "涨跌幅": "涨跌幅"})
            except Exception:
                return pd.DataFrame(columns=["板块名称", "涨跌幅"])

    def industry_members(self, board_name: str) -> pd.DataFrame:
        try:
            return self.client.stock_board_industry_cons_em(symbol=board_name).copy()
        except Exception:
            return self.client.stock_board_industry_cons_ths(symbol=board_name).copy()

    def concept_boards(self) -> pd.DataFrame:
        try:
            return self.client.stock_board_concept_name_em().copy()
        except Exception:
            try:
                frame = self.client.stock_board_concept_name_ths().copy()
                return frame.rename(columns={"name": "板块名称", "涨跌幅": "涨跌幅"})
            except Exception:
                return pd.DataFrame(columns=["板块名称", "涨跌幅"])

    def concept_members(self, board_name: str) -> pd.DataFrame:
        try:
            return self.client.stock_board_concept_cons_em(symbol=board_name).copy()
        except Exception:
            return self.client.stock_board_concept_cons_ths(symbol=board_name).copy()

    def fund_flow_rank(self, indicator: str) -> pd.DataFrame:
        try:
            return self.client.stock_individual_fund_flow_rank(indicator=indicator).copy()
        except Exception:
            return pd.DataFrame()

    def sector_fund_flow_rank(self, sector_type: str = "行业资金流") -> pd.DataFrame:
        try:
            return self.client.stock_sector_fund_flow_rank(
                indicator="今日", sector_type=sector_type
            ).copy()
        except Exception:
            return pd.DataFrame()

    def risk_notice_codes(self, notice_date: date) -> set[str]:
        try:
            frame = self.client.stock_notice_report(
                symbol="风险提示",
                date=notice_date.strftime("%Y%m%d"),
            ).copy()
        except Exception:
            return set()
        if frame.empty:
            return set()
        code_column = "代码" if "代码" in frame else ("股票代码" if "股票代码" in frame else None)
        if code_column is None:
            return set()
        return {str(code).zfill(6) for code in frame[code_column].dropna()}

    @staticmethod
    def _sina_symbol(symbol: str) -> str:
        if symbol.startswith(("5", "6")):
            return f"sh{symbol}"
        if symbol.startswith(("4", "8", "9")):
            return f"bj{symbol}"
        return f"sz{symbol}"
