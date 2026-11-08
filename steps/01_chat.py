"""Step 1: a chat window. The model is smart, but you do all the work around it.

This is how most people use a model: paste in an error, read the answer, make the
edit yourself, run the code again, paste the next error. The model can fix the bugs
in demo_project/, but *you* run the tests, choose which files to show it, and apply
every change. You are the harness.

    cd demo_project
    python3 ../steps/01_chat.py

Paste or type a message, then type END on its own line to send it. Ctrl-C quits.
"""
import json
import os
import pathlib
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


def call_model(messages):
    body = {"model": MODEL, "messages": messages, "max_tokens": 8192}
    if EFFORT:
        body["reasoning_effort"] = EFFORT
    request = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)["choices"][0]["message"]


def read_message():
    lines = []
    while (line := input()) != "END":
        lines.append(line)
    return "\n".join(lines)


# The whole "memory" is this list. Every request re-sends all of it.
messages = []
pastes = 0
try:
    while True:
        print("\nyou (type END to send) ›")
        messages.append({"role": "user", "content": read_message()})
        pastes += 1
        reply = call_model(messages)
        messages.append({"role": "assistant", "content": reply["content"]})
        print(f"\nmodel › {reply['content']}")
except (KeyboardInterrupt, EOFError):
    print(f"\nMessages you sent: {pastes}. Every file it saw, you pasted. Every test run, you ran.")
