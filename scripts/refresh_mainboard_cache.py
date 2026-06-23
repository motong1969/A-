#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from stock_selector.data.baostock import BaoStockDataFetcher


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh a lightweight main-board stock cache.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()

    run_date = date.fromisoformat(args.date)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.output_dir / f"mainboard-cache-{run_date.isoformat()}.csv"
    status_path = args.output_dir / "data-source-status.txt"

    try:
        fetcher = BaoStockDataFetcher()
        try:
            frame = fetcher._query_all_stock_with_fallback(run_date)
        finally:
            fetcher.close()
        if not frame.empty:
            frame.to_csv(cache_path, index=False, encoding="utf-8-sig")
            status_path.write_text("实时数据\n", encoding="utf-8")
            print(f"data_source=实时数据")
            print(f"mainboard_cache={cache_path}")
            return 0
    except Exception as exc:
        print(f"mainboard_cache_refresh_failed={type(exc).__name__}: {exc}")

    latest = _latest_cache(args.output_dir)
    if latest is not None:
        status_path.write_text("缓存数据\n", encoding="utf-8")
        print("data_source=缓存数据")
        print(f"mainboard_cache={latest}")
        return 0

    status_path.write_text("降级报告\n", encoding="utf-8")
    print("data_source=降级报告")
    print("mainboard_cache=none")
    return 0


def _latest_cache(output_dir: Path) -> Path | None:
    caches = sorted(output_dir.glob("mainboard-cache-*.csv"), reverse=True)
    return caches[0] if caches else None


if __name__ == "__main__":
    raise SystemExit(main())
