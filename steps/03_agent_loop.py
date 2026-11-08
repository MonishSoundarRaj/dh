"""Step 3: put it in a loop. That's an agent.

Keep calling the model. Every time it asks for tools, run them and feed the results
back. Stop when it answers without asking for anything. The core of Claude Code,
Codex, and DeepSeek Harness is this same loop. Everything else is built around it.

    cd demo_project
    python3 ../steps/03_agent_loop.py "Run the tests, find the bugs, and fix them."

WARNING: no permission checks yet, so the model can run any command. Step 4
(mini_harness.py) adds them.
"""
import json
import os
import subprocess
import sys
import urllib.request

BASE_URL = os.environ.get("MINI_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_KEY = os.environ.get("MINI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("MINI_MODEL", "deepseek-v4-flash")
EFFORT = os.environ.get("MINI_EFFORT")  # optional thinking effort: low, medium, high


def bash(command):
    done = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
    return f"{done.stdout}{done.stderr}\n[exit code {done.returncode}]"


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote {path}."


TOOLS = {"bash": bash, "write_file": write_file}
SCHEMAS = [
    {"type": "function", "function": {
        "name": "bash", "description": "Run a shell command; use it to list, read (cat), and test.",
        "parameters": {"type": "object", "required": ["command"],
                       "properties": {"command": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Overwrite a file with new content.",
        "parameters": {"type": "object", "required": ["path", "content"],
                       "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}}},
]


def call_model(messages):
    body = {"model": MODEL, "messages": messages, "tools": SCHEMAS, "max_tokens": 8192}
    if EFFORT:
        body["reasoning_effort"] = EFFORT
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]


messages = [
    {"role": "system", "content": "You are a coding agent. Use your tools to inspect and change files."},
    {"role": "user", "content": " ".join(sys.argv[1:]) or "Run the tests, find the bugs, and fix them."},
]

while True:                                                  # ← the agent loop
    reply = call_model(messages)
    messages.append(reply)
    if reply.get("content"):
        print(reply["content"])
    if not reply.get("tool_calls"):
        break                                                # no tool requested: done
    for call in reply["tool_calls"]:
        name, args = call["function"]["name"], json.loads(call["function"]["arguments"])
        print(f"  -> {name} {args}")
        result = TOOLS[name](**args)
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
