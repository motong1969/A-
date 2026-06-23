#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import sys


def main() -> int:
    try:
        import baostock as bs
    except Exception as exc:
        print(f"BaoStock import failed: {exc}")
        return 1

    today = date.today().isoformat()
    login = bs.login()
    if getattr(login, "error_code", "0") != "0":
        print(f"BaoStock login failed: {getattr(login, 'error_msg', 'unknown error')}")
        return 1
    try:
        result = bs.query_trade_dates(start_date=today, end_date=today)
        rows: list[list[str]] = []
        while getattr(result, "error_code", "1") == "0" and result.next():
            rows.append(result.get_row_data())
    finally:
        try:
            bs.logout()
        except Exception:
            pass

    if not rows:
        print("No trade-date rows returned.")
        return 1
    is_trading_day = str(rows[0][1]) == "1"
    print(f"trade_date={today} trading_day={is_trading_day}")
    return 0 if is_trading_day else 2


if __name__ == "__main__":
    sys.exit(main())
