#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stock_selector.email_notify import email_audit_fields, send_today_stock_email_from_env


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
    audit = _audit_fields(args.report_path)
    extra_log = (
        f"report_path={args.report_path}\n"
        f"report_size_bytes={_report_size(args.report_path)}\n"
        f"git_commit={audit['Git Commit']}\n"
        f"workflow_run_id={audit['Workflow Run ID']}\n"
        f"today_stock_sha256={audit['today_stock.md SHA256']}\n"
        f"email_body_sha256={audit['Email Body SHA256']}\n"
        f"body_matches_today_stock={audit['Body matches today_stock']}\n"
        f"email_subject={_email_subject(args.report_path, trade_date)}\n"
        f"mail_to={os.getenv('MAIL_TO', 'none')}\n"
    )
    full_log = result.log_text + extra_log
    log_path.write_text(full_log, encoding="utf-8")
    print(full_log, end="")
    print(f"email_log={log_path}")
    if args.fail_on_error and not result.email_sent:
        return 1
    return 0


def _email_subject(report_path: Path, trade_date: date) -> str:
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        report_text = ""
    suffix = "【实时数据】"
    if not (
        "数据来源：实时数据" in report_text
        and "是否实时数据：是" in report_text
        and "是否允许作为正式选股依据：是" in report_text
    ):
        suffix = "【实时数据获取失败】"
    return f"A股自动选股日报 {trade_date.isoformat()}{suffix}"


def _report_size(report_path: Path) -> int:
    try:
        return report_path.stat().st_size
    except FileNotFoundError:
        return 0


def _audit_fields(report_path: Path) -> dict[str, str]:
    try:
        return email_audit_fields(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "Git Commit": os.getenv("GITHUB_SHA") or os.getenv("GIT_COMMIT") or "unknown",
            "Workflow Run ID": os.getenv("GITHUB_RUN_ID") or "local",
            "today_stock.md SHA256": "missing",
            "Email Body SHA256": "missing",
            "Body matches today_stock": "False",
        }


if __name__ == "__main__":
    raise SystemExit(main())
