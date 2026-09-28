"""Morning warm-up job: open every provider's usage window early via a daily t3-schedule job.

The five-hour clock starts on the first turn, so a 05:00 warm-up makes the first reset land by
mid-morning instead of five hours after you start working. The canonical definition ships in
`../warmup/`; `install` writes it into a repo's `.agents/schedules/` (you commit) and arms it on
this machine with `t3-schedule adopt`. Re-run `install` after a skill update to refresh the prompt.

    t3-usage-windows warmup install [--project REPO] [--at HH:MM] [--profile X] [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

NAME = "usage-window-warmup"
SHIPPED = Path(__file__).resolve().parent.parent / "warmup"
SCHEDULES_DIR = ".agents/schedules"  # t3-schedule's versioned-definition dir


def project_root(value: str | None) -> Path:
    if value:
        path = Path(value).expanduser().resolve()
    else:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode:
            raise SystemExit("--project REPO required outside a git repo (your personal setup repo)")
        path = Path(top.stdout.strip())
    if not path.is_dir():
        raise SystemExit(f"--project is not a directory: {path}")
    return path


def cmd_install(args: argparse.Namespace) -> int:
    if args.at and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", args.at):
        raise SystemExit(f"--at expects HH:MM, got {args.at!r}")
    project = project_root(args.project)
    dest = project / SCHEDULES_DIR
    spec_file, prompt_file = dest / f"{NAME}.json", dest / f"{NAME}.prompt.md"
    spec = json.loads((SHIPPED / f"{NAME}.json").read_text())
    try:  # a re-install refreshes defaults + prompt but keeps a time chosen earlier
        kept = json.loads(spec_file.read_text()).get("at")
    except (OSError, ValueError, AttributeError):
        kept = None
    spec["at"] = args.at or kept or spec["at"]
    body = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    prompt = (SHIPPED / f"{NAME}.prompt.md").read_text()
    adopt = ["t3-schedule", "adopt", str(spec_file)]
    adopt += ["--profile", args.profile] if args.profile else []
    adopt += ["--force"] if args.force else []
    if args.dry_run:
        print(f"--- {spec_file}\n{body}--- {prompt_file}\n{prompt}--- {' '.join(adopt)}")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    spec_file.write_text(body)
    prompt_file.write_text(prompt)
    result = subprocess.run(adopt, text=True, check=False)
    if result.returncode:
        return result.returncode
    print(f"commit   git -C {project} add {SCHEDULES_DIR}/{NAME}.json {SCHEDULES_DIR}/{NAME}.prompt.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="t3-usage-windows warmup", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help=f"write {SCHEDULES_DIR}/{NAME}.* into a repo and arm it (t3-schedule adopt)")
    install.add_argument("--project", help="repo that versions the job (default: current git repo)")
    install.add_argument("--at", help="HH:MM local (default: shipped 05:00, or the repo's existing time)")
    install.add_argument("--profile", help="machine-local T3 provider instance; omit → capacity routing")
    install.add_argument("--force", action="store_true", help="replace a same-named job armed from another repo")
    install.add_argument("--dry-run", action="store_true", help="print files + adopt command, write nothing")
    install.set_defaults(func=cmd_install)
    args = parser.parse_args(argv)
    return args.func(args)
