"""List Codex banked rate-limit resets or consume the earliest expiry."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from datetime import datetime


class AppServer:
    def __init__(self) -> None:
        codex = shutil.which("codex")
        if not codex:
            raise SystemExit("codex CLI not found on PATH")
        self.process = subprocess.Popen(
            [codex, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.next_id = 1
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "t3-usage-windows", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send({"method": "initialized"})

    def send(self, message: dict) -> None:
        assert self.process.stdin
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        request_id = self.next_id
        self.next_id += 1
        message = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        assert self.process.stdout
        while line := self.process.stdout.readline():
            response = json.loads(line)
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]
        assert self.process.stderr
        raise RuntimeError(self.process.stderr.read() or "Codex app-server exited")

    def close(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=5)


def available_credits(snapshot: dict) -> list[dict]:
    inventory = snapshot.get("rateLimitResetCredits") or {}
    return sorted(
        [
            credit
            for credit in inventory.get("credits") or []
            if credit.get("status") == "available"
            and credit.get("expiresAt") is not None
        ],
        key=lambda credit: credit["expiresAt"],
    )


def present_credit(credit: dict) -> dict:
    expiry = datetime.fromtimestamp(credit["expiresAt"]).astimezone()
    return {
        "id": credit["id"],
        "title": credit.get("title") or "Reset",
        "expires_at": expiry.isoformat(),
        "expires_local": expiry.strftime("%a %d %b %Y %H:%M %Z"),
    }


def credit_inventory(snapshot: dict) -> dict:
    raw = snapshot.get("rateLimitResetCredits") or {}
    return {
        "account_id": snapshot.get("accountId"),
        "available_count": raw.get("availableCount", 0),
        "resets": [present_credit(credit) for credit in available_credits(snapshot)],
    }


def format_markdown(inventory: dict) -> str:
    count = inventory["available_count"]
    lines = ["### Codex banked resets", "", f"**{count} available.**"]
    if inventory["resets"]:
        lines += ["", "| Reset | Expires |", "|---|---|"]
        lines += [
            f"| {reset['title']} | {reset['expires_local']} |"
            for reset in inventory["resets"]
        ]
    elif count:
        lines += ["", "Expiration details are unavailable for this account."]
    return "\n".join(lines)


def read_limits(server: AppServer) -> dict:
    return server.request(
        "account/rateLimits/read", {"supportsLunaReserve": True}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="t3-usage-windows reset",
        description="List Codex reset credits; --apply consumes the earliest expiry.",
    )
    parser.add_argument("--apply", action="store_true")
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument("--json", action="store_true")
    formats.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    if args.apply and args.markdown:
        parser.error("--markdown is read-only; use --apply alone or with --json")

    server = AppServer()
    try:
        before = read_limits(server)
        inventory = credit_inventory(before)
        credits = available_credits(before)
        if args.apply and not credits:
            raise SystemExit("no detailed, available Codex reset credit found")
        output = {**inventory, "applied": False}
        if args.apply:
            credit = credits[0]
            response = server.request(
                "account/rateLimitResetCredit/consume",
                {"creditId": credit["id"], "idempotencyKey": str(uuid.uuid4())},
            )
            output["outcome"] = response["outcome"]
            output["applied"] = response["outcome"] in {"reset", "alreadyRedeemed"}
            output["consumed_credit_id"] = credit["id"]
            after = read_limits(server)
            output["available_after"] = (
                after.get("rateLimitResetCredits") or {}
            ).get("availableCount")
            primary = (after.get("rateLimits") or {}).get("primary") or {}
            output["weekly_used_percent_after"] = primary.get("usedPercent")
            output["weekly_resets_at_after"] = primary.get("resetsAt")
    finally:
        server.close()

    if args.markdown:
        print(format_markdown(inventory))
    elif args.json:
        print(json.dumps(output, indent=2))
    elif args.apply:
        print(
            f"{output['outcome']}: {output['available_count']} -> "
            f"{output['available_after']} resets; weekly usage "
            f"{output['weekly_used_percent_after']}%"
        )
    else:
        print(format_markdown(inventory))
    return 0
