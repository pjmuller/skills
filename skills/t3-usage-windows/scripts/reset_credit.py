"""Preview or consume the earliest-expiring Codex banked rate-limit reset."""

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


def earliest_credit(snapshot: dict) -> dict | None:
    inventory = snapshot.get("rateLimitResetCredits") or {}
    available = [
        credit
        for credit in inventory.get("credits") or []
        if credit.get("status") == "available" and credit.get("expiresAt") is not None
    ]
    return min(available, key=lambda credit: credit["expiresAt"], default=None)


def read_limits(server: AppServer) -> dict:
    return server.request(
        "account/rateLimits/read", {"supportsLunaReserve": True}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="t3-usage-windows reset",
        description="Preview the earliest Codex reset credit; --apply consumes it.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    server = AppServer()
    try:
        before = read_limits(server)
        credit = earliest_credit(before)
        if not credit:
            raise SystemExit("no detailed, available Codex reset credit found")
        output = {
            "applied": False,
            "account_id": before.get("accountId"),
            "available_before": (before.get("rateLimitResetCredits") or {}).get(
                "availableCount"
            ),
            "credit_id": credit["id"],
            "expires_at": datetime.fromtimestamp(credit["expiresAt"])
            .astimezone()
            .isoformat(),
        }
        if args.apply:
            response = server.request(
                "account/rateLimitResetCredit/consume",
                {"creditId": credit["id"], "idempotencyKey": str(uuid.uuid4())},
            )
            output["outcome"] = response["outcome"]
            output["applied"] = response["outcome"] in {"reset", "alreadyRedeemed"}
            after = read_limits(server)
            output["available_after"] = (
                after.get("rateLimitResetCredits") or {}
            ).get("availableCount")
            primary = (after.get("rateLimits") or {}).get("primary") or {}
            output["weekly_used_percent_after"] = primary.get("usedPercent")
            output["weekly_resets_at_after"] = primary.get("resetsAt")
    finally:
        server.close()

    if args.json:
        print(json.dumps(output, indent=2))
    elif args.apply:
        print(
            f"{output['outcome']}: {output['available_before']} -> "
            f"{output['available_after']} resets; weekly usage "
            f"{output['weekly_used_percent_after']}%"
        )
    else:
        print(
            f"earliest reset expires {output['expires_at']} "
            f"({output['available_before']} available); pass --apply to consume"
        )
    return 0
