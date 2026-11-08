"""A scripted, offline stand-in for the model API (OpenAI-compatible /chat/completions).

It replays the demo fix step by step, so the harness can be tested without an
API key, and the live demo has a backup if the network fails:

    python tests/fake_model.py &                     # serves http://127.0.0.1:8765
    cd demo_project
    MINI_BASE_URL=http://127.0.0.1:8765 python ../mini_harness.py "Fix the failing tests"
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

OLD_IFS = '''    if score > 90:
        return "A"
    if score > 80:
        return "B"
    if score > 70:
        return "C"
    if score > 60:'''
NEW_IFS = OLD_IFS.replace(">", ">=")

SCRIPT = [
    ("Let me run the tests first.", "bash", {"command": "python3 -m unittest -v"}),
    ("All three errors come from int() in loader.py. Let me read it.", "read_file", {"path": "loader.py"}),
    ("Scores like 92.5 are not whole numbers, so int() crashes. Parse them as floats.", "edit_file",
     {"path": "loader.py", "old_string": "int(value)", "new_string": "float(value)"}),
    ("Re-running the tests.", "bash", {"command": "python3 -m unittest -v"}),
    ("Loading works now, but Linus gets a B for exactly 90.0. Let me find the grading rule.", "search",
     {"pattern": "def letter_grade"}),
    ("It's in grades.py.", "read_file", {"path": "grades.py"}),
    ("The docstring says 90 and up is an A, but the code uses >. Use >= instead.", "edit_file",
     {"path": "grades.py", "old_string": OLD_IFS, "new_string": NEW_IFS}),
    ("Re-running the tests.", "bash", {"command": "python3 -m unittest -v"}),
]
DONE = ("All 4 tests pass. I fixed two bugs:\n"
        "1. loader.py parsed scores with int(), which crashed on 92.5. It now uses float().\n"
        "2. grades.py used > instead of >=, so an average of exactly 90.0 got a B.")


def next_reply(messages, has_tools):
    if not has_tools:
        return {"role": "assistant", "content": "The error says int() can't parse '92.5'. "
                "In loader.py, change int(value) to float(value), then run the tests again."}
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    turn = messages[last_user + 1:]
    if turn and turn[-1]["role"] == "tool" and "denied" in turn[-1]["content"]:
        return {"role": "assistant", "content": "Okay, I won't do that. What would you like instead?"}
    step = sum(1 for m in turn if m["role"] == "assistant")
    if step >= len(SCRIPT):
        return {"role": "assistant", "content": DONE}
    text, name, args = SCRIPT[step]
    return {"role": "assistant", "content": text, "tool_calls": [{
        "id": f"call_{step}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply = next_reply(body["messages"], bool(body.get("tools")))
        data = json.dumps({"choices": [{"message": reply}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def serve(port=8765):
    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"fake model listening on http://127.0.0.1:{port}")
    serve(port).serve_forever()
