from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import signal
from typing import Any

import pandas as pd


class BaoStockDataFetcher:
    """BaoStock-backed free data source with local daily-bar cache."""

    prefer_full_universe = False

    def __init__(self, *, cache_dir: Path | str = ".cache/baostock", client: Any | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.daily_cache_dir = self.cache_dir / "daily"
        self.empty_cache_dir = self.cache_dir / "empty"
        self.all_stock_cache_path = self.cache_dir / "all_stock.csv"
        self.daily_cache_dir.mkdir(parents=True, exist_ok=True)
        self.empty_cache_dir.mkdir(parents=True, exist_ok=True)
        if client is not None:
            self.client = client
        else:
            try:
                import baostock as bs
            except ImportError as exc:
                raise RuntimeError("Install BaoStock with: python3 -m pip install --user baostock") from exc
            self.client = bs
        login = self.client.login()
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock login failed: {getattr(login, 'error_msg', 'unknown error')}")
        self._set_socket_timeout(8)

    def close(self) -> None:
        try:
            self._call_with_timeout(self.client.logout, timeout_seconds=2, label="logout")
        except Exception:
            pass

    @staticmethod
    def _set_socket_timeout(seconds: int) -> None:
        try:
            import baostock.common.context as context

            socket = getattr(context, "default_socket", None)
            if socket is not None:
                socket.settimeout(seconds)
        except Exception:
            pass

    def market_spot(self) -> pd.DataFrame:
        stocks = self._query_all_stock_with_fallback(date.today())
        if stocks.empty:
            return pd.DataFrame(columns=["代码", "名称", "涨跌幅", "成交额", "换手率", "流通市值"])
        frame = stocks.copy()
        frame = frame[frame["code"].astype(str).map(_is_main_board_baostock_code)].copy()
        frame["代码"] = frame["code"].map(_plain_code)
        frame["名称"] = frame["code_name"].astype(str)
        industries = self._stock_industry_map()
        frame["所属板块"] = frame["code"].map(industries).fillna("未映射")
        frame["涨跌幅"] = 0.0
        frame["成交额"] = 0.0
        frame["换手率"] = 0.0
        frame["流通市值"] = 0.0
        snapshots = self._latest_cached_snapshots()
        if not snapshots.empty:
            frame = frame.merge(snapshots, on="代码", how="left", suffixes=("", "_cached"))
            for column in ("涨跌幅", "成交额", "换手率"):
                cached = f"{column}_cached"
                frame[column] = pd.to_numeric(frame[cached], errors="coerce").fillna(frame[column])
            frame = frame[["代码", "名称", "所属板块", "涨跌幅", "成交额", "换手率", "流通市值"]]
        return frame[["代码", "名称", "所属板块", "涨跌幅", "成交额", "换手率", "流通市值"]]

    def stock_history(self, symbol: str, end_date: date, days: int = 160) -> pd.DataFrame:
        code = _baostock_code(symbol)
        start_date = end_date - timedelta(days=days * 2)
        empty_marker = self.empty_cache_dir / f"{symbol}-{end_date.isoformat()}.empty"
        if empty_marker.exists():
            return pd.DataFrame()
        cached = self._read_daily_cache(symbol)
        if not cached.empty:
            cached["trade_date"] = pd.to_datetime(cached["trade_date"], errors="coerce").dt.date
            if cached["trade_date"].max() >= end_date:
                return _window(cached, start_date, end_date)
            if cached["trade_date"].max() >= end_date - timedelta(days=5):
                return _window(cached, start_date, cached["trade_date"].max())
            fetch_start = cached["trade_date"].max() + timedelta(days=1)
        else:
            if self._cache_is_established():
                empty_marker.write_text("uncached_after_initial_warmup\n", encoding="utf-8")
                return pd.DataFrame()
            fetch_start = start_date
        try:
            fresh = self._query_history_with_timeout(code, fetch_start, end_date)
        except TimeoutError:
            empty_marker.write_text("timeout\n", encoding="utf-8")
            return pd.DataFrame()
        combined = pd.concat([cached, fresh], ignore_index=True)
        if combined.empty:
            empty_marker.write_text("empty\n", encoding="utf-8")
            return combined
        combined = (
            combined.dropna(subset=["trade_date"])
            .drop_duplicates(subset=["trade_date"], keep="last")
            .sort_values("trade_date")
            .reset_index(drop=True)
        )
        self._write_daily_cache(symbol, combined)
        return _window(combined, start_date, end_date)

    def index_history(self, symbol: str, end_date: date, days: int = 30) -> pd.DataFrame:
        code = "sh.000001" if symbol in {"sh000001", "000001", "sh.000001"} else _baostock_code(symbol)
        start_date = end_date - timedelta(days=days * 2)
        frame = self._query_history(code, start_date, end_date)
        return frame[["trade_date", "close"]] if not frame.empty else frame

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
        code = _baostock_code(symbol)
        shares = self._total_share(code)
        return shares * close if shares > 0 and close > 0 else 0.0

    def _query_all_stock_with_fallback(self, target_date: date) -> pd.DataFrame:
        day = target_date
        try:
            frame = self._call_with_timeout(
                lambda: _result_to_frame(self.client.query_all_stock(day=day.isoformat())),
                timeout_seconds=5,
                label=f"query_all_stock({day.isoformat()})",
            )
        except TimeoutError:
            frame = pd.DataFrame()
        if not frame.empty:
            try:
                frame.to_csv(self.all_stock_cache_path, index=False)
            except Exception:
                pass
            return frame
        cached = self._cached_stock_universe()
        if not cached.empty:
            return cached
        return pd.DataFrame(columns=["code", "tradeStatus", "code_name"])

    def _query_history(self, code: str, start_date: date, end_date: date) -> pd.DataFrame:
        if start_date > end_date:
            return pd.DataFrame()
        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "adjustflag,turn,tradestatus,pctChg,isST"
        )
        result = self.client.query_history_k_data_plus(
            code,
            fields,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            frequency="d",
            adjustflag="3",
        )
        frame = _result_to_frame(result)
        if frame.empty:
            return pd.DataFrame()
        frame = frame.rename(
            columns={
                "date": "trade_date",
                "volume": "vol",
                "turn": "turnover_rate",
                "pctChg": "pct_chg",
                "isST": "is_st",
            }
        )
        for column in ("open", "high", "low", "close", "preclose", "vol", "amount", "turnover_rate", "pct_chg"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
        frame["is_st"] = pd.to_numeric(frame["is_st"], errors="coerce").fillna(0).astype(int)
        return frame[
            [
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "vol",
                "amount",
                "turnover_rate",
                "pct_chg",
                "is_st",
            ]
        ].sort_values("trade_date").reset_index(drop=True)

    def _query_history_with_timeout(self, code: str, start_date: date, end_date: date) -> pd.DataFrame:
        return self._call_with_timeout(
            lambda: self._query_history(code, start_date, end_date),
            timeout_seconds=8,
            label=f"history({code})",
        )

    def _read_daily_cache(self, symbol: str) -> pd.DataFrame:
        path = self.daily_cache_dir / f"{symbol}.csv"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def _write_daily_cache(self, symbol: str, frame: pd.DataFrame) -> None:
        path = self.daily_cache_dir / f"{symbol}.csv"
        frame.to_csv(path, index=False)

    def _cache_is_established(self) -> bool:
        return sum(1 for _ in self.daily_cache_dir.glob("*.csv")) >= 1000

    def _latest_cached_snapshots(self) -> pd.DataFrame:
        rows = []
        for path in self.daily_cache_dir.glob("*.csv"):
            try:
                frame = pd.read_csv(path)
            except Exception:
                continue
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            rows.append(
                {
                    "代码": path.stem.zfill(6),
                    "涨跌幅": latest.get("pct_chg", 0.0),
                    "成交额": latest.get("amount", 0.0),
                    "换手率": latest.get("turnover_rate", 0.0),
                }
            )
        return pd.DataFrame(rows)

    def _cached_stock_universe(self) -> pd.DataFrame:
        if self.all_stock_cache_path.exists():
            try:
                cached = pd.read_csv(self.all_stock_cache_path)
                required = {"code", "code_name"}
                if required.issubset(set(cached.columns)):
                    if "tradeStatus" not in cached.columns:
                        cached["tradeStatus"] = "1"
                    return cached[["code", "tradeStatus", "code_name"]].copy()
            except Exception:
                pass
        rows = []
        for path in self.daily_cache_dir.glob("*.csv"):
            code = path.stem.zfill(6)
            bs_code = _baostock_code(code)
            rows.append({"code": bs_code, "tradeStatus": "1", "code_name": code})
        return pd.DataFrame(rows, columns=["code", "tradeStatus", "code_name"])

    def _stock_industry_map(self) -> dict[str, str]:
        path = self.cache_dir / "stock_industry.csv"
        if path.exists():
            try:
                cached = pd.read_csv(path)
                return {str(row["code"]): str(row["industry"]) for _, row in cached.iterrows()}
            except Exception:
                pass
        try:
            frame = self._call_with_timeout(
                lambda: _result_to_frame(self.client.query_stock_industry()),
                timeout_seconds=8,
                label="query_stock_industry",
            )
        except TimeoutError:
            return {}
        if frame.empty:
            return {}
        frame = frame[["code", "industry"]].copy()
        frame.to_csv(path, index=False)
        return {str(row["code"]): str(row["industry"]) for _, row in frame.iterrows()}

    def _total_share(self, code: str) -> float:
        path = self.cache_dir / "total_share.csv"
        if path.exists():
            try:
                cached = pd.read_csv(path)
                matches = cached[cached["code"].astype(str) == code]
                if not matches.empty:
                    return float(matches.iloc[-1]["totalShare"])
            except Exception:
                pass
        rows = []
        if path.exists():
            try:
                rows = pd.read_csv(path).to_dict("records")
            except Exception:
                rows = []
        for year in (date.today().year, date.today().year - 1):
            for quarter in (4, 3, 2, 1):
                try:
                    frame = self._call_with_timeout(
                        lambda: _result_to_frame(
                            self.client.query_profit_data(code=code, year=year, quarter=quarter)
                        ),
                        timeout_seconds=5,
                        label=f"query_profit_data({code},{year}Q{quarter})",
                    )
                except Exception:
                    continue
                if frame.empty or "totalShare" not in frame:
                    continue
                value = pd.to_numeric(frame["totalShare"], errors="coerce").dropna()
                if value.empty:
                    continue
                total_share = float(value.iloc[-1])
                rows.append({"code": code, "totalShare": total_share})
                pd.DataFrame(rows).drop_duplicates(subset=["code"], keep="last").to_csv(path, index=False)
                return total_share
        return 0.0

    @staticmethod
    def _call_with_timeout(callback, *, timeout_seconds: int, label: str):
        def _raise_timeout(signum, frame):
            raise TimeoutError(f"BaoStock request timed out: {label}")

        previous = signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(timeout_seconds)
        try:
            return callback()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)


def _result_to_frame(result: Any) -> pd.DataFrame:
    if getattr(result, "error_code", "0") != "0":
        raise RuntimeError(getattr(result, "error_msg", "BaoStock query failed"))
    rows = []
    while result.next():
        rows.append(result.get_row_data())
    return pd.DataFrame(rows, columns=result.fields)


def _plain_code(code: str) -> str:
    return str(code).split(".")[-1].zfill(6)


def _baostock_code(symbol: str) -> str:
    normalized = str(symbol).lower().replace(".", "")
    if normalized.startswith(("sh", "sz", "bj")):
        prefix, code = normalized[:2], normalized[2:]
        return f"{prefix}.{code.zfill(6)}"
    code = normalized.zfill(6)
    prefix = "sh" if code.startswith("6") else "sz"
    return f"{prefix}.{code}"


def _is_main_board_baostock_code(code: str) -> bool:
    normalized = str(code).lower()
    return normalized.startswith(("sh.600", "sh.601", "sh.603", "sh.605", "sz.000", "sz.001", "sz.002"))


def _window(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
    return frame[(dates >= start_date) & (dates <= end_date)].sort_values("trade_date").reset_index(drop=True)
