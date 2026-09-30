#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compact client for the treg.to tool catalog. See ../SKILL.md and --help.

`search` and `get` are free and need no token. `call` spends the team's prepaid balance: what was
charged is printed on stderr, the provider's answer goes to stdout untouched.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("TREG_BASE_URL", "https://treg.to").rstrip("/")
# treg's own ceiling for a routed call is $1; one lookup should never get near that.
DEFAULT_MAX_COST = "0.05"


def auth_headers(env=os.environ):
    token = env.get("TREG_TOKEN")
    if not token:
        sys.exit("TREG_TOKEN not in env: add it to the repo's ~/.config/mise-env/<org>/<repo>.env")
    headers = {"X-Treg-Token": token}
    if env.get("TREG_ORG"):  # identity tokens name the team; per-org API keys bake it in
        headers["X-Treg-Org"] = env["TREG_ORG"]
    return headers


def request(path, method="GET", headers=None, body=None, timeout=180):
    """-> (status, response headers, bytes). HTTP errors are returned, not raised."""
    data = None if body is None else json.dumps(body).encode()
    all_headers = {"User-Agent": "data-enrichment-skill", **(headers or {})}
    if data is not None:
        all_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=all_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def get_json(path, headers=None):
    status, _, raw = request(path, headers=headers)
    if status >= 400:
        sys.exit(f"{status} {path}: {raw.decode(errors='replace')[:300]}")
    return json.loads(raw)


def usd(value):
    return "?" if value is None else "free" if value == 0 else f"${value:.6f}".rstrip("0")


def row(endpoint):
    """One catalog search hit as a single line: id, price, observed reliability, what it does."""
    cost = endpoint.get("cost") or {}
    seen = endpoint.get("observed") or {}
    works = "untested" if seen.get("ok_rate") is None else f"{seen['ok_rate']:.0%} of {seen.get('samples', 0)}"
    price = f"{usd(cost.get('usd'))}/{cost.get('unit') or 'call'}"
    return f"{endpoint['id']} | {price} | {works} | {endpoint.get('summary', '')[:110]}"


def cmd_search(args):
    query = urllib.parse.urlencode({"q": args.job, "limit": args.limit})
    found = get_json(f"/catalog/search?{query}")
    for endpoint in found["results"]:
        print(row(endpoint))
    print(f"{found['count']} of {found['total']} shown; `get <id>` for parameters and the full price note",
          file=sys.stderr)


def cmd_get(args):
    endpoint = get_json(f"/catalog/endpoints/{urllib.parse.quote(args.id)}")["endpoint"]
    keep = ("id", "summary", "method", "kind", "cost", "input", "miss", "async", "routed_children",
            "test_request", "docs_url", "observed", "status_note")
    print(json.dumps({k: endpoint[k] for k in keep if endpoint.get(k) not in (None, "", [])},
                     indent=1, ensure_ascii=False))


def balance(headers):
    team = next((o for o in get_json("/orgs", headers) if o.get("active")), None)
    if not team:
        sys.exit("token has no active team")
    micro = get_json(f"/orgs/{team['org_id']}/balance", headers).get("balance_micro")
    return team["slug"], micro


def cmd_balance(args):
    slug, micro = balance(auth_headers())
    print(f"{slug}: {'unknown' if micro is None else f'${micro / 1e6:.4f}'}")


def cmd_call(args):
    headers = auth_headers() | {"X-Treg-Route-Max-Cost": args.max_cost}
    if args.idempotency_key:
        headers["Idempotency-Key"] = args.idempotency_key
    body = None
    if args.data is not None:
        text = sys.stdin.read() if args.data == "-" else open(args.data[1:]).read() if args.data.startswith("@") else args.data
        body = json.loads(text)
    method = args.method or get_json(f"/catalog/endpoints/{urllib.parse.quote(args.id)}")["endpoint"]["method"]
    path = f"/call/{args.id}"
    if args.query:
        path += "?" + urllib.parse.urlencode([tuple(pair.split("=", 1)) for pair in args.query])
    status, response_headers, raw = request(path, method=method, headers=headers, body=body)
    charged = int(response_headers.get("X-Treg-Cost-Micro") or 0)
    print(f"status {status} · charged ${charged / 1e6:.6f} · served by "
          f"{response_headers.get('X-Treg-Served-By') or args.id} · call {response_headers.get('X-Treg-Call-Id', '?')}",
          file=sys.stderr)
    if args.out:
        with open(args.out, "wb") as handle:
            handle.write(raw)
    else:
        sys.stdout.buffer.write(raw)
    return 0 if status < 400 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="find endpoints by the job to do (free, no token)")
    search.add_argument("job", help='what you want done, e.g. "find work email"')
    search.add_argument("--limit", type=int, default=8)
    search.set_defaults(run=cmd_search)
    get = sub.add_parser("get", help="one endpoint: parameters, price note, providers (free, no token)")
    get.add_argument("id")
    get.set_defaults(run=cmd_get)
    sub.add_parser("balance", help="team and prepaid balance (free)").set_defaults(run=cmd_balance)
    call = sub.add_parser("call", help="call an endpoint: PAID unless the catalog says free")
    call.add_argument("id")
    call.add_argument("--data", help="JSON body: literal, @file or - for stdin")
    call.add_argument("--query", action="append", metavar="KEY=VALUE", help="query parameter, repeatable")
    call.add_argument("--method", help="override the catalog's HTTP method")
    call.add_argument("--max-cost", default=DEFAULT_MAX_COST, help=f"USD ceiling for a routed call (default {DEFAULT_MAX_COST})")
    call.add_argument("--idempotency-key", help="same key on a retry = stored answer, no second charge")
    call.add_argument("--out", help="write the response body to this file")
    call.set_defaults(run=cmd_call)
    args = parser.parse_args(argv)
    return args.run(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
