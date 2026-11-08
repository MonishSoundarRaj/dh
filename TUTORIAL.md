# Tutorial: build a coding agent harness in four steps

This is the written version of the demo from our tech talk. Go at your own pace. Each step is a runnable file, and each one adds a single idea to the one before.

| Step | File | Idea | Lines |
|---|---|---|---|
| 1 | `steps/01_chat.py` | A chat window: the model is smart, but you do the work | 55 |
| 2 | `steps/02_one_tool_call.py` | The model *asks* for a tool; your code *runs* it | 64 |
| 3 | `steps/03_agent_loop.py` | Put that in a loop and you have an agent | 78 |
| 4 | `mini_harness.py` | Make the loop safe, informed, and durable | 358 |

## Step 0: Set up

You need Python 3.9+ and git. Nothing to `pip install`.

```sh
git clone https://github.com/MonishSoundarRaj/dh
cd dh
python3 -m unittest discover tests      # 16 tests pass, no key needed
```

Get **your own** API key and export it. Never commit it or share it. We used Claude Opus 5.5 with medium thinking in class (key from console.anthropic.com; a Claude.ai subscription doesn't include API access):

```sh
export MINI_BASE_URL=https://api.anthropic.com/v1
export MINI_MODEL=claude-opus-5-5     # cheaper: claude-sonnet-5-5
export MINI_EFFORT=medium             # optional: low, medium, or high
export MINI_API_KEY=sk-ant-...        # your own key
```

DeepSeek is the default and cheaper. With a key from platform.deepseek.com you only need one line:

```sh
export DEEPSEEK_API_KEY=sk-...          # macOS / Linux
$env:DEEPSEEK_API_KEY="sk-..."          # Windows PowerShell
```

Any OpenAI-compatible server also works: set `MINI_BASE_URL` and `MINI_MODEL` (and `MINI_API_KEY` if it needs one). For a free local model, install [Ollama](https://ollama.com), pull a model that supports tool calling, and use `MINI_BASE_URL=http://localhost:11434/v1`.

No key and no Ollama? Use the scripted fake model. It only knows the demo fix, but it exercises the real harness:

```sh
python3 tests/fake_model.py &
export MINI_BASE_URL=http://127.0.0.1:8765
```

Look at the project we will fix:

```sh
cd demo_project
cat AGENTS.md
python3 -m unittest -v                  # 3 errors
```

It's a small gradebook: `loader.py` reads `roster.csv`, `grades.py` has the grading rules, and `report.py` prints each student's average and letter grade. It has two bugs, and the tests only show the first one. The second appears once the first is fixed. Don't read ahead; finding it is the point of step 1.

All the commands below run from `demo_project/`. To put the bugs back at any time: `git checkout -- .`

## Step 1: A chat window

```sh
python3 ../steps/01_chat.py
```

Fix the bugs the way most people use a model. Run `python3 -m unittest` in another terminal, paste the error into the chat, and type `END` on its own line to send it. Make the edit it suggests yourself, run the tests again, and paste the next failure. If it asks for a file, paste that too.

**What you should see:** the model fixes both bugs. First, `loader.py` uses `int()`, which crashes on a score like 92.5. Once that's fixed, the tests show that a 90.0 average gets a B: `letter_grade` in `grades.py` uses `>` where it should use `>=`.

**Takeaway:** the model was smart enough. Now count what *you* did. You ran the tests every time, decided which files it needed, pasted them in, and typed every fix. You had to go around twice, because the second bug was hidden behind the first. You were the harness. In a real project with hundreds of files, choosing what to paste is the hard part.

Open the file. It sends one HTTP POST to `/chat/completions` with the list of messages so far and prints the reply. That list is the model's entire memory; every request re-sends all of it. The rest of this tutorial hands your job to code.

Put the bugs back before the next step: `git checkout -- .`

## Step 2: One tool call

```sh
python3 ../steps/02_one_tool_call.py "What files are in this folder?"
```

Now we send a `tools` list with one entry: a JSON description of a `bash` tool. The model can't run anything. Instead its reply contains a `tool_calls` field:

```json
{"tool_calls": [{"id": "call_0", "function": {"name": "bash", "arguments": "{\"command\": \"ls\"}"}}]}
```

Our code runs the command, appends a message `{"role": "tool", "tool_call_id": "call_0", "content": "<output>"}`, and calls the model again. Now it answers from what it "saw".

**What you should see:** `model asked to run: ls` (or similar), the file list, then an answer naming the files. The model didn't need you to tell it what was there; it asked.

**Takeaway:** this is function calling (OpenAI added it to its API on June 13, 2023). The model only *asks*; the harness decides whether and how to act. Notice that this script runs whatever the model asks for. Step 4 fixes that.

## Step 3: The agent loop

```sh
python3 ../steps/03_agent_loop.py "Run the tests, find the bugs, and fix them."
python3 -m unittest -v                  # usually all 4 pass now
git checkout -- .                       # put the bugs back
```

The only change from step 2 is a `while True:` loop. Keep calling the model, run every tool it asks for, append the results, and stop when a reply has no tool calls. That loop is the core of Claude Code, Codex CLI, and DeepSeek Harness (`packages/core/agent-loop`).

**Careful:** there are no permission checks. The model can run any shell command. Only run this inside `demo_project`.

**What's still missing:** permission prompts, a limit on which files it can touch, a rule against editing files it hasn't read, protection from giant outputs and infinite loops, project instructions, a log, and a plan for when the conversation gets too long.

## Step 4: The full harness

```sh
python3 ../mini_harness.py
```

Read `mini_harness.py` top to bottom. Its nine sections follow the anatomy from the talk, and each names the DeepSeek Harness package it mirrors. Then try these:

| Try | What it shows |
|---|---|
| Type `The tests are failing. Find the bugs and fix them.` | The loop and five tools. A `[y/N]` prompt before every `bash`, `write_file`, and `edit_file`. `edit_file` shows the exact change. |
| Answer `n` at an edit prompt | The `ask_permission` pre_tool hook blocks the call. The model reads "The user denied this action" and adapts. |
| Type `Read the file ../../etc/hosts` | `read_file` refuses paths outside the workspace (`PermissionError`). The model may try `bash cat` instead, which asks you first. |
| `cat .mini-harness/session-*.jsonl` | The append-only session log: every message the model saw, including the system prompt with your `AGENTS.md`. |
| Restart with `MINI_COMPACT_AT=3000 python3 ../mini_harness.py` | Compaction: once history passes 3,000 characters, older turns are replaced by a model-written summary. |
| Ask `How do I run the tests here?` | It answers from `AGENTS.md`, which the harness put in the system prompt. |

### How the pieces fit

1. **Model adapter** (`call_model`): the only function that knows the API format. Retries on 429 and 5xx errors.
2. **Tool registry** (`@tool`): turns a Python function into a JSON schema the model can read.
3. **Tools**: `read_file` (line-numbered), `write_file`, `edit_file` (exact snippet must appear exactly once), `search` (regex), `bash`. File tools are fenced to the workspace and must read a file before changing it.
4. **Hooks**: `pre_tool` hooks can block a call by returning a message (`ask_permission`); `post_tool` hooks can rewrite results (`cap_output` keeps the first and last 4,000 characters; `repeat_guard` nudges the model after the 3rd, 5th, and 8th identical call).
5. **System prompt**: identity, rules of thumb, workspace, OS, date, and any `AGENTS.md` or `CLAUDE.md`.
6. **Session log**: every message is appended to `.mini-harness/session-<time>.jsonl`.
7. **Compaction**: when history gets long, summarize the middle. It cuts at an assistant message so a tool result is never separated from the call that asked for it.
8. **Agent loop** (`run_turn`): the step-3 loop plus a step limit, compaction, and Ctrl-C handling that answers any unanswered tool calls (the API rejects a history with a tool call that has no result).
9. **Entry point**: one-shot mode if you pass a task, otherwise an interactive prompt.

## Exercises

1. **Add a tool.** Write `list_files(path)` with the `@tool` decorator. Nothing else needs to change; the loop picks it up.
2. **Add a safety hook.** Block any `bash` command containing `rm -rf`, even with `--yes`. A `@hook("pre_tool")` function that returns a string blocks the call.
3. **Swap the brain.** Run the demo on a local Ollama model. Only `MINI_BASE_URL` and `MINI_MODEL` change. Which parts of the harness had to know?
4. **Add `--resume`.** Read the newest `session-*.jsonl` and rebuild `messages` from each line's `"message"`. (What should happen to lines written by compaction?)

Run `python3 -m unittest discover tests` after each change to check you didn't break anything.

## Going further

- DeepSeek Harness source: https://github.com/deepseek-ai/deepseek-harness. Start with `docs/architecture.md`, then `packages/core/agent-loop`.
- The ReAct paper (the research idea behind the loop): https://arxiv.org/abs/2210.03629
