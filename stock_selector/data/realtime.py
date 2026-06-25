from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from stock_selector.data.baostock import BaoStockDataFetcher


class RealtimeMarketDataError(RuntimeError):
    """Raised when no live same-day market data source is usable."""


class RealtimeMainBoardFetcher:
    """Live-data fetcher that only uses local CSV for the main-board universe.

    Historical cached bars may be used for the lookback window, but the final
    bar for ``trade_date`` must come from a live quote source.
    """

    prefer_full_universe = False

    def __init__(
        self,
        *,
        trade_date: date,
        pool_path: Path | str = Path("data/mainboard_stock_pool.csv"),
        cache_dir: Path | str = Path(".cache/baostock"),
        client: Any | None = None,
    ) -> None:
        self.trade_date = trade_date
        self.pool_path = Path(pool_path)
        self.cache_dir = Path(cache_dir)
        self.daily_cache_dir = self.cache_dir / "daily"
        self.data_source_name = ""
        self.source_errors: list[str] = []
        self.data_warnings: list[str] = []
        self._spot_is_full_market = False
        self._spot: pd.DataFrame | None = None
        self._spot_by_code: dict[str, dict] = {}
        self._baostock = BaoStockDataFetcher(cache_dir=cache_dir)
        self._tushare_client = None
        if client is not None:
            self.client = client
        else:
            try:
                import akshare as ak
            except ImportError as exc:
                raise RealtimeMarketDataError("AkShare is required for Eastmoney/Sina realtime fallback") from exc
            self.client = ak

    def close(self) -> None:
        self._baostock.close()

    def market_spot(self) -> pd.DataFrame:
        pool = self._read_pool()
        spot = self._load_realtime_spot()
        frame = pool.merge(spot, on="代码", how="inner", suffixes=("_pool", ""))
        if frame.empty:
            raise RealtimeMarketDataError(
                f"实时行情源 {self.data_source_name or 'none'} 没有返回任何本地主板股票池代码"
            )
        if "名称_pool" in frame:
            if "名称" not in frame:
                frame["名称"] = frame["名称_pool"]
            else:
                live_name = frame["名称"].astype(str)
                pool_name = frame["名称_pool"].astype(str)
                frame["名称"] = pool_name.where(pool_name.ne("") & live_name.eq(frame["代码"].astype(str)), frame["名称"])
        if "所属板块_pool" in frame:
            if "所属板块" not in frame:
                frame["所属板块"] = frame["所属板块_pool"]
            else:
                live_sector = frame["所属板块"].astype(str)
                pool_sector = frame["所属板块_pool"].astype(str)
                frame["所属板块"] = pool_sector.where(pool_sector.ne("") & live_sector.isin(["未映射", "nan", "None"]), frame["所属板块"])
        for column in ("涨跌幅", "成交额", "换手率", "收盘价", "成交量"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame = frame.dropna(subset=["收盘价", "成交量", "涨跌幅"])
        if frame.empty:
            raise RealtimeMarketDataError("实时行情缺少当天收盘价、成交量或涨跌幅")
        self._spot_by_code = {str(row["代码"]).zfill(6): row.to_dict() for _, row in frame.iterrows()}
        return frame[["代码", "名称", "所属板块", "涨跌幅", "成交额", "换手率", "流通市值"]]

    def full_market_spot(self) -> pd.DataFrame:
        spot = self._load_realtime_spot()
        if not self._spot_is_full_market:
            raise RealtimeMarketDataError(f"{self.data_source_name or 'unknown'} 只提供部分股票行情，不能作为全A股大盘概况")
        frame = spot.copy()
        for column in ("涨跌幅", "成交额", "收盘价", "成交量"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame = frame.dropna(subset=["涨跌幅", "成交额", "收盘价", "成交量"])
        if frame.empty:
            raise RealtimeMarketDataError(f"{self.data_source_name or 'unknown'} 全A股行情缺少涨跌幅、成交额、收盘价或成交量")
        columns = ["代码", "名称", "涨跌幅", "成交额", "收盘价", "成交量"]
        for optional in ("涨停标记", "跌停标记"):
            if optional in frame:
                columns.append(optional)
        return frame[columns]

    def stock_history(self, symbol: str, end_date: date, days: int = 160) -> pd.DataFrame:
        if end_date != self.trade_date:
            return pd.DataFrame()
        code = str(symbol).zfill(6)
        live = self._spot_by_code.get(code)
        if live is None:
            return pd.DataFrame()
        current = _live_row(live, self.trade_date)
        if current.empty:
            return pd.DataFrame()
        start_date = end_date - timedelta(days=days * 2)
        cached = self._read_daily_cache(code)
        if not cached.empty:
            cached["trade_date"] = pd.to_datetime(cached["trade_date"], errors="coerce").dt.date
            cached = cached[(cached["trade_date"] >= start_date) & (cached["trade_date"] < end_date)].copy()
        combined = pd.concat([cached, current], ignore_index=True)
        combined = (
            combined.dropna(subset=["trade_date", "close", "vol", "pct_chg"])
            .drop_duplicates(subset=["trade_date"], keep="last")
            .sort_values("trade_date")
            .reset_index(drop=True)
        )
        if combined.empty or combined.iloc[-1]["trade_date"] != end_date:
            return pd.DataFrame()
        return combined

    def index_history(self, symbol: str, end_date: date, days: int = 30) -> pd.DataFrame:
        if self.data_source_name == "Tushare":
            try:
                return self._tushare_index_history(symbol, end_date, days)
            except Exception:
                return pd.DataFrame()
        try:
            return self._baostock.index_history(symbol, end_date, days=days)
        except Exception:
            return pd.DataFrame()

    def industry_boards(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["板块名称", "涨跌幅"])

    def industry_members(self, board_name: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["代码"])

    def concept_boards(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["板块名称", "涨跌幅"])

    def concept_members(self, board_name: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["代码"])

    def fund_flow_rank(self, indicator: str) -> pd.DataFrame:
        return pd.DataFrame()

    def sector_fund_flow_rank(self, sector_type: str = "行业资金流") -> pd.DataFrame:
        return pd.DataFrame()

    def risk_notice_codes(self, notice_date: date) -> set[str]:
        return set()

    def market_cap(self, symbol: str, close: float) -> float:
        return self._baostock.market_cap(symbol, close)

    def _read_pool(self) -> pd.DataFrame:
        if not self.pool_path.exists():
            raise RealtimeMarketDataError(f"主板股票池 CSV 不存在: {self.pool_path}")
        pool = pd.read_csv(self.pool_path)
        if "code" in pool:
            pool["代码"] = pool["code"].astype(str).str.extract(r"(\d{6})", expand=False).fillna(pool["code"].astype(str))
        if "代码" not in pool:
            raise RealtimeMarketDataError(f"主板股票池 CSV 缺少 code/代码 字段: {self.pool_path}")
        pool["代码"] = pool["代码"].astype(str).str.zfill(6)
        if "name" in pool and "名称" not in pool:
            pool["名称"] = pool["name"]
        if "sector" in pool and "所属板块" not in pool:
            pool["所属板块"] = pool["sector"]
        if "名称" not in pool:
            pool["名称"] = pool["代码"]
        if "所属板块" not in pool:
            pool["所属板块"] = "未映射"
        prefixes = ("600", "601", "603", "605", "000", "001", "002")
        pool = pool[pool["代码"].astype(str).str.startswith(prefixes)].copy()
        if pool.empty:
            raise RealtimeMarketDataError(f"主板股票池 CSV 没有主板代码: {self.pool_path}")
        return pool[["代码", "名称", "所属板块"]].drop_duplicates(subset=["代码"])

    def _load_realtime_spot(self) -> pd.DataFrame:
        if self._spot is not None:
            return self._spot
        providers = (
            ("Tushare", self._tushare_spot, True),
            ("Eastmoney", self._eastmoney_spot, True),
            ("Tencent", self._tencent_spot, False),
            ("AkShare-Sina", self._sina_spot, True),
        )
        for name, provider, is_full_market in providers:
            try:
                frame = provider()
                if not frame.empty:
                    self.data_source_name = name
                    self._spot_is_full_market = is_full_market
                    self._spot = frame
                    return frame
            except Exception as exc:
                self.source_errors.append(f"{name}: {type(exc).__name__}: {exc}")
        raise RealtimeMarketDataError("; ".join(self.source_errors) or "所有实时行情源均失败")

    def _eastmoney_spot(self) -> pd.DataFrame:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "6000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f2,f3,f5,f6,f8,f15,f16,f17,f21",
        }
        response = requests.get(url, params=params, timeout=12)
        response.raise_for_status()
        rows = response.json().get("data", {}).get("diff", [])
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise RealtimeMarketDataError("Eastmoney direct quote returned 0 rows")
        frame = frame.rename(
            columns={
                "f12": "代码",
                "f14": "名称",
                "f2": "收盘价",
                "f3": "涨跌幅",
                "f5": "成交量",
                "f6": "成交额",
                "f8": "换手率",
                "f15": "最高价",
                "f16": "最低价",
                "f17": "开盘价",
                "f21": "流通市值",
            }
        )
        return _normalize_realtime_spot(frame, source="Eastmoney")

    def _tushare_spot(self) -> pd.DataFrame:
        token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_PRO_TOKEN")
        if not token:
            raise RealtimeMarketDataError("TUSHARE_TOKEN is not configured")
        client = self._tushare()
        frame = client.daily(
            trade_date=self.trade_date.strftime("%Y%m%d"),
            fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
        ).copy()
        if frame.empty:
            raise RealtimeMarketDataError(f"Tushare daily returned 0 rows for {self.trade_date.isoformat()}")
        basic = client.daily_basic(
            trade_date=self.trade_date.strftime("%Y%m%d"),
            fields="ts_code,trade_date,turnover_rate,circ_mv,total_mv",
        ).copy()
        if basic.empty:
            raise RealtimeMarketDataError(f"Tushare daily_basic returned 0 rows for {self.trade_date.isoformat()}")
        frame = frame.merge(
            basic[["ts_code", "trade_date", "turnover_rate", "circ_mv"]],
            on=["ts_code", "trade_date"],
            how="left",
        )
        stock_basic = client.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,name,market,exchange",
        ).copy()
        if not stock_basic.empty:
            frame = frame.merge(stock_basic, on="ts_code", how="left")
        else:
            frame["name"] = ""
            frame["market"] = ""
            frame["exchange"] = ""
        frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")
        missing_turnover = int(frame["turnover_rate"].isna().sum())
        if missing_turnover:
            self.data_warnings.append(
                f"Tushare daily_basic missing turnover_rate for {missing_turnover} stock(s); dropped before selection"
            )
            frame = frame.dropna(subset=["turnover_rate"]).copy()
        if frame.empty:
            raise RealtimeMarketDataError("Tushare daily_basic did not provide any usable turnover_rate values")
        frame["代码"] = frame["ts_code"].astype(str).str.extract(r"(\d{6})", expand=False)
        frame["名称"] = frame["name"].fillna(frame["代码"]).astype(str)
        frame["收盘价"] = pd.to_numeric(frame["close"], errors="coerce")
        frame["开盘价"] = pd.to_numeric(frame["open"], errors="coerce")
        frame["最高价"] = pd.to_numeric(frame["high"], errors="coerce")
        frame["最低价"] = pd.to_numeric(frame["low"], errors="coerce")
        frame["成交量"] = pd.to_numeric(frame["vol"], errors="coerce") * 100
        frame["成交额"] = pd.to_numeric(frame["amount"], errors="coerce") * 1000
        frame["涨跌幅"] = pd.to_numeric(frame["pct_chg"], errors="coerce")
        frame["换手率"] = frame["turnover_rate"]
        frame["流通市值"] = pd.to_numeric(frame["circ_mv"], errors="coerce") * 10000
        limit_flags = frame.apply(_tushare_limit_flags, axis=1)
        frame["涨停标记"] = [item[0] for item in limit_flags]
        frame["跌停标记"] = [item[1] for item in limit_flags]
        return _normalize_realtime_spot(frame, source="Tushare")

    def _tushare(self):
        if self._tushare_client is not None:
            return self._tushare_client
        try:
            import tushare as ts
        except ImportError as exc:
            raise RealtimeMarketDataError("tushare package is not installed") from exc
        token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_PRO_TOKEN")
        if not token:
            raise RealtimeMarketDataError("TUSHARE_TOKEN is not configured")
        ts.set_token(token)
        self._tushare_client = ts.pro_api()
        return self._tushare_client

    def _tushare_index_history(self, symbol: str, end_date: date, days: int) -> pd.DataFrame:
        client = self._tushare()
        ts_code = "000001.SH" if symbol in {"sh000001", "000001", "sh.000001"} else symbol
        start_date = end_date - timedelta(days=days * 2)
        frame = client.index_daily(
            ts_code=ts_code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            fields="ts_code,trade_date,close",
        ).copy()
        if frame.empty:
            return pd.DataFrame()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce").dt.date
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        return frame[["trade_date", "close"]].dropna().sort_values("trade_date").reset_index(drop=True)

    def _sina_spot(self) -> pd.DataFrame:
        frame = self.client.stock_zh_a_spot().copy()
        return _normalize_realtime_spot(frame, source="Sina")

    def _tencent_spot(self) -> pd.DataFrame:
        pool = self._read_pool()
        symbols = [_tencent_symbol(code) for code in pool["代码"].astype(str)]
        rows = []
        for batch in _chunks(symbols, 120):
            response = requests.get("https://qt.gtimg.cn/q=" + ",".join(batch), timeout=12)
            response.raise_for_status()
            rows.extend(_parse_tencent_response(response.text))
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise RealtimeMarketDataError("Tencent quote returned 0 rows")
        return _normalize_realtime_spot(frame, source="Tencent")

    def _read_daily_cache(self, symbol: str) -> pd.DataFrame:
        path = self.daily_cache_dir / f"{symbol}.csv"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)


def _normalize_realtime_spot(frame: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    rename = {
        "代码": "代码",
        "名称": "名称",
        "最新价": "收盘价",
        "收盘": "收盘价",
        "今开": "开盘价",
        "开盘": "开盘价",
        "最高": "最高价",
        "最低": "最低价",
        "成交量": "成交量",
        "成交额": "成交额",
        "涨跌幅": "涨跌幅",
        "换手率": "换手率",
        "流通市值": "流通市值",
    }
    normalized = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns}).copy()
    if "代码" not in normalized:
        raise RealtimeMarketDataError(f"{source} 实时行情缺少代码字段")
    normalized["代码"] = normalized["代码"].astype(str).str.replace(r"^(sh|sz|bj)", "", regex=True).str.zfill(6)
    for column in ("收盘价", "开盘价", "最高价", "最低价", "成交量", "成交额", "涨跌幅", "换手率", "流通市值"):
        if column not in normalized:
            normalized[column] = 0.0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "名称" not in normalized:
        normalized["名称"] = normalized["代码"]
    if "所属板块" not in normalized:
        normalized["所属板块"] = "未映射"
    normalized = normalized.dropna(subset=["收盘价", "成交量", "涨跌幅"])
    normalized = normalized[normalized["收盘价"] > 0].copy()
    columns = ["代码", "名称", "所属板块", "涨跌幅", "成交额", "换手率", "流通市值", "收盘价", "开盘价", "最高价", "最低价", "成交量"]
    for optional in ("涨停标记", "跌停标记"):
        if optional in normalized:
            normalized[optional] = pd.to_numeric(normalized[optional], errors="coerce")
            columns.append(optional)
    return normalized[columns]


def _tushare_limit_flags(row) -> tuple[float | None, float | None]:
    ts_code = str(row.get("ts_code") or "")
    code = str(row.get("代码") or "").zfill(6)
    exchange = str(row.get("exchange") or "").upper()
    name = str(row.get("name") or "").upper()
    if ts_code.endswith(".BJ") or exchange == "BSE":
        return None, None
    pre_close = _number(row.get("pre_close"))
    close = _number(row.get("close"))
    pct = _number(row.get("pct_chg"))
    if pre_close <= 0 or close <= 0:
        return None, None
    if "ST" in name:
        ratio = 0.05
    elif code.startswith(("300", "301", "688", "689")):
        ratio = 0.20
    else:
        ratio = 0.10
    up_price = _rounded_limit_price(pre_close, ratio, 1)
    down_price = _rounded_limit_price(pre_close, ratio, -1)
    return float(close >= up_price and pct > 0), float(close <= down_price and pct < 0)


def _rounded_limit_price(pre_close: float, ratio: float, direction: int) -> float:
    value = Decimal(str(pre_close)) * (Decimal("1") + Decimal(str(ratio * direction)))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _normalize_tushare_history(frame: pd.DataFrame, end_date: date) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    normalized = frame.copy()
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], format="%Y%m%d", errors="coerce").dt.date
    normalized["open"] = pd.to_numeric(normalized["open"], errors="coerce")
    normalized["high"] = pd.to_numeric(normalized["high"], errors="coerce")
    normalized["low"] = pd.to_numeric(normalized["low"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized["vol"] = pd.to_numeric(normalized["vol"], errors="coerce") * 100
    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce") * 1000
    normalized["turnover_rate"] = 0.0
    normalized["pct_chg"] = pd.to_numeric(normalized["pct_chg"], errors="coerce")
    normalized["is_st"] = 0
    normalized = normalized[
        ["trade_date", "open", "high", "low", "close", "vol", "amount", "turnover_rate", "pct_chg", "is_st"]
    ].dropna(subset=["trade_date", "close", "vol", "pct_chg"])
    normalized = normalized.sort_values("trade_date").reset_index(drop=True)
    if normalized.empty or normalized.iloc[-1]["trade_date"] != end_date:
        return pd.DataFrame()
    return normalized


def _live_row(row: dict, trade_date: date) -> pd.DataFrame:
    close = _number(row.get("收盘价"))
    volume = _number(row.get("成交量"))
    pct = _number(row.get("涨跌幅"))
    if close <= 0 or volume <= 0:
        return pd.DataFrame()
    open_price = _number(row.get("开盘价")) or close
    high = _number(row.get("最高价")) or max(open_price, close)
    low = _number(row.get("最低价")) or min(open_price, close)
    amount = _number(row.get("成交额"))
    turnover = _number(row.get("换手率"))
    return pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "vol": volume,
                "amount": amount,
                "turnover_rate": turnover,
                "pct_chg": pct,
                "is_st": 0,
            }
        ]
    )


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tencent_symbol(code: str) -> str:
    normalized = str(code).zfill(6)
    return f"sh{normalized}" if normalized.startswith(("5", "6")) else f"sz{normalized}"


def _chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _parse_tencent_response(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if '="' not in line:
            continue
        payload = line.split('="', 1)[1].rstrip('";')
        fields = payload.split("~")
        if len(fields) < 39 or fields[0] == "v_pv_none_match":
            continue
        code = fields[2]
        close = _number(fields[3])
        previous_close = _number(fields[4])
        pct = _number(fields[32]) if len(fields) > 32 else 0.0
        if pct == 0.0 and close > 0 and previous_close > 0:
            pct = (close / previous_close - 1) * 100
        rows.append(
            {
                "代码": code,
                "名称": fields[1],
                "收盘价": close,
                "开盘价": _number(fields[5]),
                "最高价": _number(fields[33]) if len(fields) > 33 else close,
                "最低价": _number(fields[34]) if len(fields) > 34 else close,
                "成交量": _number(fields[36]) if len(fields) > 36 else _number(fields[6]),
                "成交额": _number(fields[37]) * 10000 if len(fields) > 37 else 0.0,
                "涨跌幅": pct,
                "换手率": _number(fields[38]) if len(fields) > 38 else 0.0,
                "流通市值": _number(fields[44]) * 100000000 if len(fields) > 44 else 0.0,
            }
        )
    return rows
