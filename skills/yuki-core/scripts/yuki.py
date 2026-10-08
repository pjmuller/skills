#!/usr/bin/env python3
"""Yuki "Aan te leveren aankoopfacturen" for one quarter: CSV, or append-only into the quarter tab.

  uv run --project <core> <core>/scripts/yuki.py --config <wrapper>/yuki.json outstanding [--quarter 2026-Q3] [--csv PATH]
  uv run --project <core> <core>/scripts/yuki.py --config <wrapper>/yuki.json sheet-push [--quarter 2026-Q3] [--dry-run]
  uv run --project <core> <core>/scripts/yuki.py --config <wrapper>/yuki.json discover

--quarter defaults to the last closed quarter. The API key is read from the env var named by
the config's `api_key_env` (run through `mise exec --` in the wrapper's repository).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from yuki_core import outstanding, sheet

REQUIRED = ("company_label", "domain_id", "administration_id", "api_key_env")


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if not config.get(k)]
    if missing:
        raise SystemExit(f"{path}: missing {', '.join(missing)}")
    config["_dir"] = path.resolve().parent
    return config


def resolve(config: dict, value: str | None) -> Path | None:
    """Config paths may be absolute, ~-relative, or relative to the yuki.json directory."""
    return config["_dir"] / Path(value).expanduser() if value else None


def connect(config: dict):
    from yuki_core.client import YukiClient  # zeep only when talking to Yuki

    key = os.environ.get(config["api_key_env"])
    if not key:
        raise SystemExit(f"${config['api_key_env']} is not set; run via `mise exec --` in the wrapper's repository")
    print(f"Connecting to Yuki ({config['company_label']})...", file=sys.stderr)
    return YukiClient(key).connect(config["domain_id"])


def fetch(config: dict, quarter: str) -> list[dict]:
    raw = connect(config).outstanding_creditor_items(config["administration_id"])
    rows = outstanding.select(outstanding.parse_items(raw), quarter)
    print(f"{config['company_label']} {quarter}: {len(rows)} rows", file=sys.stderr)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path("yuki.json"), help="wrapper yuki.json (default: ./yuki.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    quarter = argparse.ArgumentParser(add_help=False)
    quarter.add_argument("--quarter", default=outstanding.last_closed_quarter(date.today()))
    out = sub.add_parser("outstanding", parents=[quarter], help="print or write the quarter's rows as CSV")
    out.add_argument("--csv", type=Path, help="write here instead of stdout")
    push = sub.add_parser("sheet-push", parents=[quarter], help="append unseen rows to the quarter tab")
    push.add_argument("--dry-run", action="store_true", help="show what would be appended, write nothing")
    push.add_argument("--tab", help="target tab name (default: the quarter), e.g. for a test push")
    push.add_argument("--gws", type=Path, help="override config gws.script (google-workspace-core gws.py)")
    push.add_argument("--gws-config", type=Path, help="override config gws.config (workspace.json)")
    sub.add_parser("discover", help="list the domains and administrations this API key sees")
    args = parser.parse_args()
    config = load_config(args.config)

    if args.cmd == "discover":
        client = connect(config)
        print(client.domains())
        print(client.administrations())
        return
    outstanding.quarter_bounds(args.quarter)  # validate before spending Yuki calls
    if args.cmd == "outstanding":
        text = outstanding.to_csv(fetch(config, args.quarter))
        if args.csv:
            args.csv.write_text(text, encoding="utf-8")
            print(f"Written to {args.csv}", file=sys.stderr)
        else:
            sys.stdout.write(text)
        return

    target, gws = config.get("sheet"), config.get("gws") or {}
    if not target:
        raise SystemExit(f"{args.config}: no `sheet` configured; use `outstanding --csv` instead")
    script = args.gws or resolve(config, gws.get("script"))
    gws_config = args.gws_config or resolve(config, gws.get("config"))
    if not script or not gws_config:
        raise SystemExit("set gws.script and gws.config in the wrapper config, or pass --gws/--gws-config")
    rows = fetch(config, args.quarter)
    summary = sheet.push(sheet.gws_runner(script, gws_config), target["spreadsheet_id"],
                         target["manual_columns"], args.quarter, rows, dry_run=args.dry_run,
                         formulas=target.get("formula_columns"), tab=args.tab)
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, PermissionError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
