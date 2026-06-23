from __future__ import annotations

from datetime import date
import os
from typing import Any

import pandas as pd


class TushareDataFetcher:
    """Tushare Pro data source for A-share stock lists and daily bars."""

    def __init__(self, token: str | None = None, client: Any | None = None) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
        if client is not None:
            self.client = client
            return
        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("Install tushare with: python3 -m pip install --user tushare") from exc
        if not self.token:
            raise RuntimeError("Tushare Pro requires TUSHARE_TOKEN or TUSHARE_PRO_TOKEN.")
        ts.set_token(self.token)
        self.client = ts.pro_api()

    @staticmethod
    def token_configured() -> bool:
        return bool(os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN"))

    def stock_basic(self) -> pd.DataFrame:
        return self.client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        ).copy()

    def stock_history(self, ts_code: str, start_date: date, end_date: date) -> pd.DataFrame:
        frame = self.client.daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        ).copy()
        if frame.empty:
            return frame
        frame = frame.rename(
            columns={
                "trade_date": "trade_date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "vol": "vol",
                "amount": "amount",
            }
        )
        columns = ["trade_date", "open", "high", "low", "close", "vol", "amount"]
        return frame[columns].sort_values("trade_date").reset_index(drop=True)
