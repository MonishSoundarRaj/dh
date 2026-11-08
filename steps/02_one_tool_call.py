"""Step 2: give the brain one hand. The model *asks* for a tool; our code *runs* it.

This is function calling (OpenAI added it to their API on June 13, 2023).
The model never touches your computer. It sends back JSON like
    {"name": "bash", "arguments": "{\"command\": \"ls\"}"}
and the harness decides whether to run it, runs it, and sends the output back.

    cd demo_project
    python3 ../steps/02_one_tool_call.py "What files are in this folder?"
"""
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

ENV_FILE = pathlib.Path(__file__).resolve().parent.parent / ".env"   # your key and model; git-ignored
for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
    key, sep, value = line.strip().removeprefix("export ").partition("=")
    if sep and not key.startswith("#"):
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))   # real env vars win
BASE_URL = os.environ.get("MINI_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_KEY = os.environ.get("MINI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("MINI_MODEL", "deepseek-v4-flash")
EFFORT = os.environ.get("MINI_EFFORT")  # optional thinking effort: low, medium, high

# The tool's description is the model's only documentation for it.
BASH_TOOL = {"type": "function", "function": {
    "name": "bash",
    "description": "Run a shell command and return its output.",
    "parameters": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The command to run."}},
        "required": ["command"],
    },
}}


def call_model(messages, tools=None):
    body = {"model": MODEL, "messages": messages, "max_tokens": 8192}
    if EFFORT:
        body["reasoning_effort"] = EFFORT
    if tools:
        body["tools"] = tools
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]


messages = [{"role": "user", "content": " ".join(sys.argv[1:]) or "What files are in this folder?"}]
reply = call_model(messages, [BASH_TOOL])
messages.append(reply)

# 1. The model replied with a *request*, not an answer.
for call in reply.get("tool_calls") or []:
    command = json.loads(call["function"]["arguments"])["command"]
    print(f"model asked to run: {command}")
    # 2. The harness runs it (a real harness would ask permission first).
    output = subprocess.run(command, shell=True, capture_output=True, text=True).stdout
    print(f"output:\n{output}")
    # 3. The result goes back into the conversation, tied to the call's id.
    messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})

# 4. Ask again. Now the model can answer from what it "saw".
print("answer:", call_model(messages, [BASH_TOOL])["content"])
