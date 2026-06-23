#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_selector.email_notify import send_today_stock_email_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Send daily A-share selector email.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date in YYYY-MM-DD format.")
    parser.add_argument("--report-path", type=Path, default=Path("reports/today_stock.md"))
    parser.add_argument("--log-dir", type=Path, default=Path("reports"))
    parser.add_argument("--fail-on-error", action="store_true", help="Return non-zero when email is not sent.")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date)
    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"email-send-{trade_date.isoformat()}.log"
    result = send_today_stock_email_from_env(report_path=args.report_path, trade_date=trade_date)
    extra_log = f"email_subject={_email_subject(args.report_path, trade_date)}\nmail_to={os.getenv('MAIL_TO', 'none')}\n"
    full_log = result.log_text + extra_log
    log_path.write_text(full_log, encoding="utf-8")
    print(full_log, end="")
    print(f"email_log={log_path}")
    if args.fail_on_error and not result.email_sent:
        return 1
    return 0


def _email_subject(report_path: Path, trade_date: date) -> str:
    prefix = ""
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        report_text = ""
    for line in report_text.splitlines():
        if line.startswith("数据来源：") and line != "数据来源：实时数据":
            prefix = "【缓存降级】"
            break
    return f"{prefix}A股自动选股日报 {trade_date.isoformat()}"


if __name__ == "__main__":
    raise SystemExit(main())
