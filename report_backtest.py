#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stock_selector.history_validation import generate_backtest_report


if __name__ == "__main__":
    report_path = Path("reports/backtest-report.md")
    report = generate_backtest_report(output_path=report_path)
    print(report)
    print(f"Backtest report: {report_path}")
