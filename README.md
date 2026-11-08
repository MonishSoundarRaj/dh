# mini-harness

A coding-agent harness in one Python file (363 lines, standard library only), built for our COMP 523 (UNC) tech talk on agent harnesses.

**The model is the brain. The harness is the body.** A model on its own can only write text. A harness gives it tools (hands), feeds back what the tools return (eyes), keeps a log (memory), and asks you before anything risky (reflexes). Claude Code, Codex CLI, and [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) are all harnesses. This is the smallest one we could write that still fixes real bugs.

Every section of `mini_harness.py` names the DeepSeek Harness package it is a tiny version of, so you can read the two side by side.

## Quick start

You need Python 3.9+ and **your own API key**. Never commit a key to git or paste it into a shared file.

```sh
git clone https://github.com/MonishSoundarRaj/dh
cd dh/demo_project
python3 -m unittest -v               # 3 errors: the bugs
```

Set up the model. In class we used Claude Opus 5.5 with medium thinking. Get a key at console.anthropic.com (a Claude.ai subscription doesn't include API access), then, from the `dh` folder:

```sh
cp .env.example .env                 # Windows: copy .env.example .env
```

Open `.env` and replace `sk-ant-...` with your own key. The harness and the step files read `.env` by themselves, and `.gitignore` keeps it out of git. For a cheaper model, set `MINI_MODEL=claude-sonnet-5-5` there. For DeepSeek, the default and cheapest, delete the Claude lines and put `DEEPSEEK_API_KEY=sk-...` (key from platform.deepseek.com).

On Windows, use `python` instead of `python3`.

Now try the same bugs two ways:

```sh
python3 ../steps/01_chat.py          # no harness: paste the test error, type END, and do the fixes yourself
python3 ../mini_harness.py "The tests are failing. Find the bugs and fix them."
```

With no harness, the model can only see what you paste, so it suggests fixes and asks for more. With the harness, it runs the tests, reads the code, fixes both bugs, and runs the tests again to check. It asks before every command and edit (`y` to allow). To put the bugs back, run `git checkout -- .` in `demo_project`.

Run it with no task (`python3 ../mini_harness.py`) for an interactive chat.

## No API key? Run offline

`tests/fake_model.py` is a scripted stand-in for the model API that replays the demo fix:

```sh
python3 tests/fake_model.py &                       # serves http://127.0.0.1:8765
cd demo_project
MINI_BASE_URL=http://127.0.0.1:8765 python3 ../mini_harness.py "Fix the failing tests"
```

## Configuration

Set these in `.env` (see `.env.example`) or export them in your terminal. Anything exported wins over `.env`.

| Variable | Default | Meaning |
|---|---|---|
| `DEEPSEEK_API_KEY` | none | Your DeepSeek key. `MINI_API_KEY` works for any provider. |
| `MINI_BASE_URL` | `https://api.deepseek.com` | Any OpenAI-compatible server, e.g. Ollama at `http://localhost:11434/v1` |
| `MINI_MODEL` | `deepseek-v4-flash` | Model name on that server |
| `MINI_EFFORT` | none | Thinking effort, `low` / `medium` / `high`, sent as `reasoning_effort` |
| `MINI_COMPACT_AT` | `200000` | Characters of history before older turns are summarized |

Claude works through Anthropic's OpenAI-compatible endpoint (`https://api.anthropic.com/v1`), as in the quick start above.

Flags: `--yes` auto-approves every risky tool. Only use it in a throwaway folder.

## What is in the file

| Section | Lines | What it does | DeepSeek Harness package |
|---|---|---|---|
| 1. Model adapter | 26 | Calls `/chat/completions`, retries on 429/5xx | `packages/llm/llm-deepseek` |
| 2. Tool registry | 24 | `@tool` decorator: function + JSON schema | `packages/core/tools` |
| 3. Tools | 70 | `read_file`, `write_file`, `edit_file`, `search`, `bash`; workspace fence; read-before-edit | `packages/fs/tool-fs`, `fs/tool-fs-search`, `shell/tool-bash` |
| 4. Hooks | 66 | `pre_tool` / `post_tool`: permission prompt, output cap, repeat-loop guard | `tools/pre-execute` + `post-execute` events, `packages/guard`, `packages/spill` |
| 5. System prompt | 15 | Identity, workspace, OS, date, plus `AGENTS.md` / `CLAUDE.md` | `packages/core/system-prompt` |
| 6. Session log | 11 | Append-only JSONL in `.mini-harness/` | `packages/core/session` |
| 7. Compaction | 25 | Summarizes old turns when history gets long | `packages/compaction/compaction-basic` |
| 8. Agent loop | 35 | Call model → run tools → feed results back → repeat | `packages/core/agent-loop` |
| 9. Entry point | 33 | One-shot and interactive modes | `apps/cli` |

The rest is the docstring, imports, and config. Left out on purpose: plugins and hot reload, web/desktop UI, streaming, subagents, MCP, skills, and an OS-level sandbox.

## Repository layout

```
mini_harness.py       the full harness (step 4)
steps/
  01_chat.py          a chat window: you paste, it answers, you do the rest
  02_one_tool_call.py the model asks for a tool, we run it
  03_agent_loop.py    the loop, with no safety yet
demo_project/         a small gradebook with two bugs, four tests, and an AGENTS.md
tests/
  test_harness.py     16 tests, no API key needed
  fake_model.py       scripted offline model
TUTORIAL.md           build it yourself, step by step
```

## Tests

```sh
python3 -m unittest discover tests -v
```

## Safety

The harness runs commands the model asks for. It asks you first unless you pass `--yes`, and the file tools cannot leave the folder you start it in, but `bash` is not sandboxed. Run it on code you have backed up, and never with secrets in the folder.

## Credits

Structure modeled on [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (MIT). No code was copied; this is a from-scratch teaching version.
