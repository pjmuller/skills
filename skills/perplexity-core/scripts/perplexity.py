#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["perplexityai>=0.43"]
# ///
"""Web research through the Perplexity Agent API. See ../SKILL.md and --help.

Every call is paid. Search tools are passed explicitly: without them the model does not search and
hallucinates. URLs in a structured answer are kept only when they occur in the retrieved results.
"""
import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlsplit

DEFAULT_MODEL = "google/gemini-3.8-flash"
DEFAULT_CONTEXT = "medium"
DEFAULT_INSTRUCTIONS = (
    "You are a research assistant for a B2B software founder. Use the search tools and base every "
    "statement on retrieved sources; cite the source URL inline after the claim. Never invent URLs, "
    "facts, employers or titles. Say plainly when something is unknown. Be concise and factual; no "
    "citation markers like [1]."
)
_NULL_LITERALS = {"", "-", "n/a", "na", "null", "none", "nil", "unknown", "undisclosed"}
_NULL_PATTERN = re.compile(
    r"^(information\s+)?not\s+(publicly\s+|currently\s+)?"
    r"(disclosed|found|available|known|specified|listed|provided|public)", re.IGNORECASE)


def client():
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        sys.exit("PERPLEXITY_API_KEY is not set (mise env of the consuming repo)")
    from perplexity import Perplexity
    return Perplexity(api_key=key)


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def collect_result_urls(response: Any) -> Set[str]:
    """URLs the API actually retrieved (search / people / fetched pages)."""
    urls: Set[str] = set()
    for item in _field(response, "output") or []:
        if _field(item, "type") == "message":
            continue
        for bucket in ("results", "contents"):
            for entry in _field(item, bucket) or []:
                url = _field(entry, "url")
                if isinstance(url, str) and url:
                    urls.add(url)
    return urls


def normalize_url(url: str) -> str:
    candidate = url.strip()
    if "//" not in candidate:
        candidate = "//" + candidate
    parts = urlsplit(candidate)
    host = (parts.netloc or "").lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) > 2 and len(labels[0]) <= 3:  # nl.linkedin.com -> linkedin.com
        host = ".".join(labels[1:])
    return f"{host}{(parts.path or '').rstrip('/').lower()}"


def verify_url(url: Optional[str], result_urls: Iterable[str]) -> Optional[str]:
    """Keep `url` only if it (or an ancestor path) occurs in the retrieved results."""
    url = coerce_null(url)
    if not url or "." not in url:
        return None
    key = normalize_url(url)
    for result in result_urls:
        rk = normalize_url(result)
        if rk == key or rk.startswith(key + "/"):
            return url
    return None


def coerce_null(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    probe = value.strip().strip(" .\"'").lower()
    if probe in _NULL_LITERALS or _NULL_PATTERN.match(probe):
        return None
    return value.strip() or None


def strip_citations(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    cleaned = re.sub(r"\[\d+\](?:\[\d+\])*", "", text)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in cleaned.split("\n")]
    return "\n".join(lines).strip() or None


def harden_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Agent API structured output: every top-level field nullable and required, no extras."""
    props = schema.get("properties", {})
    for prop in props.values():
        prop.pop("default", None)
        prop.pop("title", None)
        if "anyOf" not in prop and "type" in prop and prop["type"] != "null":
            prop["type"] = [prop["type"], "null"] if isinstance(prop["type"], str) else prop["type"]
    schema["required"] = list(props)
    schema["additionalProperties"] = False
    return schema


def clean_structured(raw: Dict[str, Any], result_urls: Set[str]) -> Dict[str, Any]:
    """Null placeholders, strip citation markers, drop unverifiable *url* fields."""
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        if key.endswith("url") or key.endswith("_urls"):
            if isinstance(value, list):
                out[key] = [u for u in (verify_url(v, result_urls) for v in value) if u]
            else:
                out[key] = verify_url(value, result_urls)
        elif isinstance(value, str):
            out[key] = strip_citations(coerce_null(value))
        else:
            out[key] = value
    return out


def ask(query: str, *, instructions: str, model: str, context_size: str, people: bool,
        schema: Optional[Dict[str, Any]], schema_name: str = "Result") -> Any:
    tools: List[Dict[str, Any]] = [{"type": "web_search", "search_context_size": context_size}]
    if people:
        tools.append({"type": "people_search"})
    kwargs: Dict[str, Any] = dict(model=model, instructions=instructions, input=query, tools=tools)
    if schema is not None:
        kwargs["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": schema_name, "schema": harden_schema(schema)}}
    started = time.monotonic()
    response = client().responses.create(**kwargs)
    elapsed = time.monotonic() - started
    cost = getattr(getattr(response, "usage", None), "cost", None)
    print(f"perplexity: {model} ${getattr(cost, 'total_cost', 0) or 0:.4f} {elapsed:.1f}s", file=sys.stderr)
    return response


def render(response: Any, *, schema: Optional[Dict[str, Any]], as_json: bool) -> str:
    text = _field(response, "output_text") or ""
    urls = sorted(collect_result_urls(response))
    if schema is not None:
        data = clean_structured(json.loads(text or "{}"), set(urls))
        payload = {"data": data, "sources": urls}
        return json.dumps(payload if as_json else data, ensure_ascii=False, indent=2)
    if as_json:
        return json.dumps({"answer": strip_citations(text), "sources": urls}, ensure_ascii=False, indent=2)
    body = strip_citations(text) or "(empty answer)"
    return body + ("\n\nSources:\n" + "\n".join(f"- {u}" for u in urls) if urls else "")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Perplexity Agent API research CLI (paid per call).")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="one research question; markdown answer + retrieved source URLs")
    a.add_argument("query", help="the question, or '-' to read it from stdin")
    a.add_argument("--instructions", help="system instructions (default: sourced, concise research)")
    a.add_argument("--instructions-file")
    a.add_argument("--schema", help="JSON-schema file → structured JSON output (fields nullable; *url keys verified)")
    a.add_argument("--schema-name", default="Result")
    a.add_argument("--model", default=os.environ.get("PERPLEXITY_MODEL", DEFAULT_MODEL))
    a.add_argument("--context-size", default=os.environ.get("PERPLEXITY_CONTEXT_SIZE", DEFAULT_CONTEXT),
                   choices=["low", "medium", "high"])
    a.add_argument("--people-search", action="store_true", help="also enable the people_search tool")
    a.add_argument("--json", action="store_true", help="machine output: {answer|data, sources}")
    a.add_argument("--out", help="write the result to this file instead of stdout")
    sub.add_parser("check", help="verify key + SDK without spending")
    args = p.parse_args(argv)

    if args.cmd == "check":
        client()
        print("perplexity-core ready")
        return 0

    query = sys.stdin.read() if args.query == "-" else args.query
    instructions = args.instructions or DEFAULT_INSTRUCTIONS
    if args.instructions_file:
        with open(args.instructions_file, encoding="utf-8") as f:
            instructions = f.read()
    schema = None
    if args.schema:
        with open(args.schema, encoding="utf-8") as f:
            schema = json.load(f)
    response = ask(query.strip(), instructions=instructions, model=args.model, context_size=args.context_size,
                   people=args.people_search, schema=schema, schema_name=args.schema_name)
    text = render(response, schema=schema, as_json=args.json)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
