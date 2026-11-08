#!/usr/bin/env python3
"""mini-harness: a coding-agent harness in one file, modeled on DeepSeek Harness (dsh).

The model is the brain. This file is the body around it:
  hands   -> tools (read, write, edit, search, bash)
  eyes    -> tool results fed back into the conversation
  memory  -> the message list + an append-only session log
  reflexes-> hooks that run before/after every tool (permissions, guards)

Every numbered section names the DeepSeek Harness package it is a tiny version of,
so you can open the real thing (github.com/deepseek-ai/deepseek-harness) and compare.

Usage:
  python mini_harness.py                    # interactive chat
  python mini_harness.py "fix the tests"    # one task, then exit
  python mini_harness.py --yes "..."        # auto-approve risky tools (careful!)

Config (environment variables, or KEY=value lines in a .env file next to this file):
  DEEPSEEK_API_KEY   your API key (or MINI_API_KEY for any other provider)
  MINI_BASE_URL      any OpenAI-compatible server   (default https://api.deepseek.com)
  MINI_MODEL         model name                     (default deepseek-v4-flash)
  MINI_EFFORT        optional thinking effort: low, medium, or high
"""
import datetime
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── 0. Config ─────────────────────────────────────────────────────────────────
ENV_FILE = pathlib.Path(__file__).resolve().parent / ".env"   # your key and model; git-ignored
for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
    key, sep, value = line.strip().removeprefix("export ").partition("=")
    if sep and not key.startswith("#"):
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))   # real env vars win
BASE_URL = os.environ.get("MINI_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_KEY = os.environ.get("MINI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("MINI_MODEL", "deepseek-v4-flash")
EFFORT = os.environ.get("MINI_EFFORT")                      # how hard the model thinks: low / medium / high
WORKSPACE = pathlib.Path.cwd().resolve()
MAX_STEPS = 30                                              # model calls per turn
MAX_OUTPUT = 8_000                                          # chars of tool output the model sees
COMPACT_AT = int(os.environ.get("MINI_COMPACT_AT", 200_000))  # chars of history before summarizing
AUTO_APPROVE = False

COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
def paint(text, code): return f"\033[{code}m{text}\033[0m" if COLOR else text
def dim(t): return paint(t, "2")
def cyan(t): return paint(t, "36")
def yellow(t): return paint(t, "33")


# ── 1. Model adapter  (dsh: packages/llm/llm-deepseek) ────────────────────────
# The only place that knows how to talk to the brain. Swap this, swap the model.
def call_model(messages, tools=None):
    body = {"model": MODEL, "messages": messages, "max_tokens": 8192}   # Claude requires max_tokens
    if EFFORT:
        body["reasoning_effort"] = EFFORT
    if tools:
        body["tools"] = tools
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    for attempt in range(3):                                # dsh: packages/llm/llm-retry
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.load(response)["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"Model API error {e.code}: {e.read().decode(errors='replace')[:500]}")
        except urllib.error.URLError as e:
            sys.exit(f"Could not reach {BASE_URL}: {e.reason}")


# ── 2. Tool registry  (dsh: packages/core/tools) ──────────────────────────────
# A tool = a Python function + a JSON schema the model reads to know it exists.
TOOLS = {}

def tool(description, risky=False, **params):
    """Register a function as a model-facing tool. Every param is a required string."""
    def register(fn):
        TOOLS[fn.__name__] = {
            "fn": fn,
            "risky": risky,
            "schema": {"type": "function", "function": {
                "name": fn.__name__,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {p: {"type": "string", "description": d} for p, d in params.items()},
                    "required": list(params),
                },
            }},
        }
        return fn
    return register


# ── 3. Tools  (dsh: packages/fs/tool-fs, fs/tool-fs-search, shell/tool-bash) ──
files_read = set()   # dsh: packages/fs/fs-observation-policy (read before you edit)

def inside_workspace(path):
    """Sandbox fence (dsh: packages/sandbox): file tools may not leave the workspace."""
    full = (WORKSPACE / path).resolve()
    if not full.is_relative_to(WORKSPACE):
        raise PermissionError(f"{path} is outside the workspace {WORKSPACE}")
    return full

@tool("Read a UTF-8 text file and return its lines, numbered.",
      path="File path, relative to the workspace.")
def read_file(path):
    full = inside_workspace(path)
    files_read.add(full)
    lines = full.read_text().splitlines()
    return "\n".join(f"{n:4} | {line}" for n, line in enumerate(lines, 1)) or "(empty file)"

@tool("Create a new file, or overwrite one you have already read.", risky=True,
      path="File path, relative to the workspace.", content="The complete new file content.")
def write_file(path, content):
    full = inside_workspace(path)
    if full.exists() and full not in files_read:
        return f"Error: read {path} before overwriting it."
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    files_read.add(full)
    return f"Wrote {len(content)} characters to {path}."

@tool("Replace one exact snippet of text in a file. old_string must appear exactly once.", risky=True,
      path="File path, relative to the workspace.",
      old_string="Exact text to find, including indentation.",
      new_string="Text to put in its place.")
def edit_file(path, old_string, new_string):
    full = inside_workspace(path)
    if full not in files_read:
        return f"Error: read {path} before editing it."
    text = full.read_text()
    count = text.count(old_string)
    if count != 1:
        return f"Error: old_string appears {count} times in {path}; it must appear exactly once."
    full.write_text(text.replace(old_string, new_string))
    return f"Edited {path}."

@tool("Search every file in the workspace for a regular expression. Returns path:line: text.",
      pattern="Python regular expression to search for.")
def search(pattern):
    regex, hits = re.compile(pattern), []
    for file in sorted(WORKSPACE.rglob("*")):
        if not file.is_file() or any(part.startswith(".") for part in file.relative_to(WORKSPACE).parts):
            continue
        try:
            for n, line in enumerate(file.read_text().splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{file.relative_to(WORKSPACE)}:{n}: {line.strip()}")
        except (UnicodeDecodeError, OSError):
            continue                                          # skip binary / unreadable files
    return "\n".join(hits) or "No matches."

@tool("Run a shell command in the workspace and return its output and exit code.", risky=True,
      command="The shell command to run, e.g. `python3 -m unittest -v`.")
def bash(command):
    try:
        done = subprocess.run(command, shell=True, cwd=WORKSPACE, capture_output=True,
                              text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120 seconds."
    return f"{done.stdout}{done.stderr}\n[exit code {done.returncode}]"


# ── 4. Hooks  (dsh: tools/pre-execute + tools/post-execute events) ────────────
# The harness's "reflexes". A pre_tool hook returns a string to BLOCK the call;
# a post_tool hook gets the result and returns a (possibly changed) result.
HOOKS = {"pre_tool": [], "post_tool": []}

def hook(event):
    def register(fn):
        HOOKS[event].append(fn)
        return fn
    return register

@hook("pre_tool")
def ask_permission(name, args):
    """Human approval for anything that changes the world (dsh: approval policy)."""
    if not TOOLS[name]["risky"] or AUTO_APPROVE:
        return None
    preview = args.get("command") or args.get("path", "")
    if name == "edit_file":
        preview += f"\n  - {args.get('old_string', '')!r}\n  + {args.get('new_string', '')!r}"
    answer = input(yellow(f"  allow {name}: {preview}\n  [y/N] > ")).strip().lower()
    return None if answer == "y" else "The user denied this action. Ask them what to do instead."

@hook("post_tool")
def cap_output(name, args, result):
    """Keep huge outputs from flooding the context window (dsh: packages/spill)."""
    if len(result) <= MAX_OUTPUT:
        return result
    half = MAX_OUTPUT // 2
    return f"{result[:half]}\n... [{len(result) - MAX_OUTPUT} characters cut] ...\n{result[-half:]}"

repeat_counts = {}

@hook("post_tool")
def repeat_guard(name, args, result):
    """Nudge the model out of loops (dsh: packages/guard/repeat-tool-reminder)."""
    key = name + json.dumps(args, sort_keys=True)
    repeat_counts[key] = repeat_counts.get(key, 0) + 1
    if repeat_counts[key] in (3, 5, 8):
        result += (f"\n[harness] You have made this exact call {repeat_counts[key]} times. "
                   "Look at the result above and change your approach, or finish.")
    return result

def execute(call):
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError:
        return "Error: tool arguments were not valid JSON."
    if name not in TOOLS:
        return f"Error: there is no tool named {name}."
    print(cyan(f"  ⏺ {name}({', '.join(f'{k}={v!r:.60}' for k, v in args.items())})"))
    for check in HOOKS["pre_tool"]:
        blocked = check(name, args)
        if blocked:
            print(dim(f"    ⎿ blocked: {blocked}"))
            return blocked
    try:
        result = TOOLS[name]["fn"](**args)
    except Exception as e:                                    # errors are results, not crashes
        result = f"Error: {type(e).__name__}: {e}"
    for after in HOOKS["post_tool"]:
        result = after(name, args, result)
    print(dim("    ⎿ " + result.strip("\n").replace("\n", "\n      ")[:400]))
    return result


# ── 5. System prompt  (dsh: packages/core/system-prompt) ─────────────────────
def system_prompt():
    parts = [
        "You are mini-harness, a coding agent working in the user's project.",
        "Use the tools to look before you act: search and read files, run commands, then edit. "
        "After changing code, run the tests to check your work. Keep answers short.",
        f"Workspace: {WORKSPACE}\nOS: {platform.system()}\nDate: {datetime.date.today()}",
    ]
    for name in ("AGENTS.md", "CLAUDE.md"):                  # project instructions, like Claude Code
        file = WORKSPACE / name
        if file.exists():
            parts.append(f"Project instructions from {name}:\n{file.read_text()}")
    return "\n\n".join(parts)


# ── 6. Session log  (dsh: packages/core/session) ─────────────────────────────
# Append-only. Everything the model saw can be rebuilt from this file.
LOG = None

def remember(messages, message):
    messages.append(message)
    if LOG:
        with LOG.open("a") as f:
            f.write(json.dumps({"time": time.time(), "message": message}) + "\n")


# ── 7. Compaction  (dsh: packages/compaction/compaction-basic) ───────────────
# When history gets too long, ask the model to summarize the middle of it.
def maybe_compact(messages):
    if len(json.dumps(messages)) < COMPACT_AT:
        return messages
    # Keep the system prompt + first task, and the newest ~10 messages. Cut at an
    # assistant message so no tool result is separated from the call that asked for it.
    cut = next((i for i in range(max(2, len(messages) - 10), len(messages))
                if messages[i]["role"] == "assistant"), None)
    if cut is None or cut <= 2:
        return messages
    old = "\n".join(f"{m['role']}: {str(m.get('content'))[:2000]}" for m in messages[2:cut])
    summary = call_model([
        {"role": "system", "content": "Summarize this agent transcript: goal, what was done, "
                                      "files touched, what is left. Be brief and concrete."},
        {"role": "user", "content": old},
    ])["content"]
    print(dim(f"  [harness] compacted {cut - 2} old messages into a summary"))
    note = {"role": "user", "content": f"[Summary of earlier work]\n{summary}"}
    if LOG:
        with LOG.open("a") as f:
            f.write(json.dumps({"time": time.time(), "compacted": cut - 2, "message": note}) + "\n")
    return messages[:2] + [note] + messages[cut:]


# ── 8. The agent loop  (dsh: packages/core/agent-loop) ───────────────────────
# This is the whole trick: call the model, run the tools it asks for, feed the
# results back, repeat until it answers without asking for a tool.
def run_turn(messages, user_text):
    remember(messages, {"role": "user", "content": user_text})
    try:
        for _ in range(MAX_STEPS):
            messages[:] = maybe_compact(messages)
            reply = call_model(messages, [t["schema"] for t in TOOLS.values()])
            message = {"role": "assistant", "content": reply.get("content") or ""}
            if reply.get("reasoning_content"):                # DeepSeek thinking mode wants it echoed back
                message["reasoning_content"] = reply["reasoning_content"]
            if reply.get("tool_calls"):
                message["tool_calls"] = reply["tool_calls"]
            remember(messages, message)
            if message["content"]:
                print(f"\n{message['content']}\n")
            if not reply.get("tool_calls"):
                return                                        # no tool requested: the turn is over
            for call in reply["tool_calls"]:
                remember(messages, {"role": "tool", "tool_call_id": call["id"], "content": execute(call)})
        print(yellow(f"[harness] stopped after {MAX_STEPS} steps"))
    except KeyboardInterrupt:
        print(yellow("\n[harness] interrupted"))
        answer_missing_tool_calls(messages)

def answer_missing_tool_calls(messages):
    """Every tool call needs a result or the API rejects the history (dsh does this too)."""
    last = next((m for m in reversed(messages) if m["role"] == "assistant"), None)
    answered = {m.get("tool_call_id") for m in messages if m["role"] == "tool"}
    for call in (last or {}).get("tool_calls", []):
        if call["id"] not in answered:
            remember(messages, {"role": "tool", "tool_call_id": call["id"], "content": "Interrupted by the user."})


# ── 9. Entry point  (dsh: apps/cli, the "headless" and interactive profiles) ──
def main():
    global AUTO_APPROVE, LOG
    args = sys.argv[1:]
    if "--yes" in args:
        AUTO_APPROVE = True
        args.remove("--yes")
    if not API_KEY and "localhost" not in BASE_URL and "127.0.0.1" not in BASE_URL:
        sys.exit(f"No API key. Copy .env.example to {ENV_FILE} and put your own key in it.")
    log_dir = WORKSPACE / ".mini-harness"
    log_dir.mkdir(exist_ok=True)
    LOG = log_dir / f"session-{datetime.datetime.now():%Y%m%d-%H%M%S}.jsonl"

    messages = []
    remember(messages, {"role": "system", "content": system_prompt()})
    print(dim(f"mini-harness · {MODEL} · {WORKSPACE} · {len(TOOLS)} tools · log: {LOG.name}"))
    if args:                                                  # one-shot mode
        run_turn(messages, " ".join(args))
        return
    while True:                                               # interactive mode
        try:
            text = input(paint("\nyou › ", "1")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text in ("exit", "quit", "/exit"):
            return
        if text:
            run_turn(messages, text)


if __name__ == "__main__":
    main()
