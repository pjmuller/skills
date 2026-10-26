"""Which agent skills this machine's T3 threads actually use (`t3-my-prompts --skills`).

A thread uses a skill when one of its tool calls (the invocation, never its output) reads
`<name>/SKILL.md`, invokes the Skill tool with that name, or runs a command the skill ships (an
executable in its `scripts/`) as a program, not merely as an argument (`rg alpha-cmd` does not count). Threads whose
workspace contains the skill's own source are maintenance, counted apart, so editing a skill does
not look like using it. Counts are distinct threads; skills with zero use are listed too.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from datetime import datetime
import json
import os
from pathlib import Path
import re

from t3_store import connect_readonly, iso

NOT_COMMANDS = {"install", "release"}


@dataclass
class Skill:
    name: str
    path: Path
    used: set[str] = field(default_factory=set)
    maintained: set[str] = field(default_factory=set)


def skill_roots(workspaces: list[str]) -> list[Path]:
    home = Path.home()
    roots = [home / ".agents/skills", home / ".codex/skills", *home.glob(".claude*/skills")]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        roots.append(Path(os.environ["CLAUDE_CONFIG_DIR"]) / "skills")
    for workspace in workspaces:
        roots += [Path(workspace) / ".agents/skills", Path(workspace) / ".claude/skills", Path(workspace) / "skills"]
    return roots


SKILL_FILE = re.compile(r"/([\w.-]+)/SKILL\.md")
# Words that run the next word: `uv run x`, `timeout 60 x`, `bash x.sh`, `FOO=1 x`.
WRAPPERS = {"sudo", "time", "env", "exec", "nohup", "command", "timeout", "bash", "sh", "zsh", "uv", "run",
            "python", "python3", "mise", "then", "do", "else", "!", "{"}


def discover(workspaces: list[str]) -> tuple[dict[str, Skill], dict[str, str]]:
    """Skills by name (the first root wins: copies of one core count once) and command → skill."""
    skills: dict[str, Skill] = {}
    commands: dict[str, str] = {}
    for root in skill_roots(workspaces):
        for entry in sorted(root.glob("*/SKILL.md")) if root.is_dir() else []:
            name = entry.parent.name
            if name in skills:
                continue
            skills[name] = Skill(name, entry.parent.resolve())
            scripts = entry.parent / "scripts"
            for command in sorted(scripts.iterdir()) if scripts.is_dir() else []:
                if (command.is_file() and os.access(command, os.X_OK) and command.suffix in ("", ".py", ".sh")
                        and command.name not in NOT_COMMANDS and not command.name.startswith("test_")):
                    commands.setdefault(command.name, name)
    return skills, commands


def segments(shell: str) -> list[list[str]]:
    """Words of each command segment; quotes stripped. Segments end at unquoted `; & | newline ( )`.
    A `$(…)` or backtick substitution (also inside double quotes) is its own nested command line:
    its segments are emitted and the outer word continues, so outer arguments stay arguments."""
    out: list[list[str]] = []
    stack: list[tuple] = []
    words: list[str] = []
    word, quote, closer, depth = "", None, None, 0

    def end_segment() -> None:
        nonlocal words, word
        if word:
            words.append(word)
            word = ""
        if words:
            out.append(words)
            words = []

    i = 0
    while i < len(shell):
        c, nxt = shell[i], shell[i + 1:i + 2]
        if quote != "'" and (c == "$" and nxt == "(" or c == "`" and closer != "`"):
            stack.append((words, word, quote, closer, depth))
            words, word, quote, closer, depth = [], "", None, ")" if c == "$" else "`", 0
            i += 2 if c == "$" else 1
            continue
        if quote is None and stack and c == closer and not (c == ")" and depth):
            end_segment()
            words, word, quote, closer, depth = stack.pop()
            word += "$()"
        elif quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and nxt:
                word, i = word + nxt, i + 1
            else:
                word += c
        elif c in "'\"":
            quote = c
        elif c == "\\" and nxt:
            word, i = word + nxt, i + 1
        elif c in ";&|\n()":
            depth += {"(": 1, ")": -1 if depth else 0}.get(c, 0)
            end_segment()
        elif c.isspace():
            if word:
                words.append(word)
                word = ""
        else:
            word += c
        i += 1
    end_segment()
    while stack:  # unterminated substitution: close the outer lines too
        words, word, quote, closer, depth = stack.pop()
        end_segment()
    return out


def executed(shell: str) -> set[str]:
    """Basenames of the programs a shell command line runs (first word of each segment), not its arguments."""
    names = set()
    for words in segments(shell):
        for word in words:
            if word in WRAPPERS or word.startswith(("-", "$")) or word.isdigit() or re.match(r"^\w+=", word):
                continue
            names.add(word.rsplit("/", 1)[-1])
            break
    return names


def used_skills(kind: str, invocation: str, skills: dict[str, Skill], commands: dict[str, str]) -> set[str]:
    """Skills one tool call invoked: a SKILL.md read, or (shell calls) running a shipped command."""
    names = {m[1] for m in SKILL_FILE.finditer(invocation)}
    if kind == "command_execution":
        names |= {commands[c] for c in executed(invocation) if c in commands}
    return {n for n in names if n in skills}


@cache
def resolved(workspace: str) -> Path:
    return Path(workspace).resolve()


def count(store: Path, since: datetime, until: datetime) -> tuple[dict[str, Skill], int]:
    with connect_readonly(store) as conn:
        workspaces = {row["thread_id"]: row["workspace_root"] or "" for row in conn.execute(
            "SELECT t.thread_id, p.workspace_root FROM orchestration_v2_projection_threads t "
            "LEFT JOIN projection_projects p ON p.project_id = t.project_id")}
        skills, commands = discover(sorted(set(workspaces.values()) - {""}))
        threads: set[str] = set()
        for row in conn.execute(
                "SELECT thread_id, type, json_extract(payload_json, '$.toolName') AS tool, "
                "json_extract(payload_json, '$.input') AS invocation FROM orchestration_v2_projection_turn_items "
                "WHERE type IN ('command_execution', 'dynamic_tool') AND updated_at >= ? AND updated_at < ?",
                (iso(since), iso(until))):
            thread, invocation = row["thread_id"], row["invocation"] or ""
            threads.add(thread)
            names = used_skills(row["type"], invocation, skills, commands)
            if row["tool"] == "Skill":
                names.add(json.loads(invocation).get("skill", "") if invocation.startswith("{") else invocation)
            workspace = workspaces.get(thread, "")
            for name in names & skills.keys():
                skill = skills[name]
                own = bool(workspace) and skill.path.is_relative_to(resolved(workspace))
                (skill.maintained if own else skill.used).add(thread)
    return skills, len(threads)


def render(skills: dict[str, Skill], thread_count: int, since: datetime, until: datetime, as_json: bool) -> str:
    rows = sorted(skills.values(), key=lambda s: (-len(s.used), -len(s.maintained), s.name))
    if as_json:
        return json.dumps({"since": iso(since), "until": iso(until), "threads_with_tools": thread_count,
                           "skills": [{"name": s.name, "used": len(s.used), "maintenance": len(s.maintained),
                                       "path": str(s.path)} for s in rows]}, indent=1) + "\n"
    lines = [f"# Skill usage {since:%Y-%m-%d} → {until:%Y-%m-%d} ({thread_count} threads with tool calls)", "",
             "| skill | threads using it | maintenance threads |", "| --- | ---: | ---: |"]
    lines += [f"| {s.name} | {len(s.used)} | {len(s.maintained)} |" for s in rows]
    return "\n".join(lines) + "\n"
