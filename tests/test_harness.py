"""Tests for mini_harness.py. No API key needed: a scripted fake model stands in.

    python -m unittest discover tests -v
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fake_model  # noqa: E402
import mini_harness as mh  # noqa: E402


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        shutil.copytree(ROOT / "demo_project", self.tmp / "demo_project")
        self.workspace = self.tmp / "demo_project"
        mh.WORKSPACE = self.workspace
        mh.files_read.clear()
        mh.repeat_counts.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestTools(WorkspaceTest):
    def test_read_numbers_lines(self):
        self.assertIn("   1 | ", mh.read_file("grades.py"))

    def test_fence_blocks_paths_outside_workspace(self):
        with self.assertRaises(PermissionError):
            mh.read_file("../../etc/passwd")

    def test_edit_requires_read_first(self):
        self.assertIn("read grades.py before", mh.edit_file("grades.py", "score > 90", "score >= 90"))

    def test_edit_requires_unique_match(self):
        mh.read_file("grades.py")
        self.assertIn("appears 4 times", mh.edit_file("grades.py", "if score >", "if score >="))
        self.assertEqual(mh.edit_file("grades.py", "score > 90", "score >= 90"), "Edited grades.py.")

    def test_write_cannot_clobber_unread_file(self):
        self.assertIn("before overwriting", mh.write_file("grades.py", "oops"))
        self.assertIn("Wrote", mh.write_file("new.txt", "hi"))

    def test_search_finds_matches_and_skips_dot_dirs(self):
        (self.workspace / ".hidden").mkdir()
        (self.workspace / ".hidden" / "x.py").write_text("def average(): pass")
        hits = mh.search(r"def average")
        self.assertIn("grades.py:", hits)
        self.assertNotIn(".hidden", hits)

    def test_bash_reports_exit_code(self):
        self.assertIn("[exit code 1]", mh.bash(f"{sys.executable} -m unittest"))

    def test_tool_errors_become_results(self):
        call = {"function": {"name": "read_file", "arguments": json.dumps({"path": "missing.py"})}}
        self.assertTrue(mh.execute(call).startswith("Error: FileNotFoundError"))


class TestHooks(WorkspaceTest):
    def test_cap_output_keeps_head_and_tail(self):
        capped = mh.cap_output("bash", {}, "a" * 5000 + "b" * 5000)
        self.assertTrue(capped.startswith("a") and capped.endswith("b"))
        self.assertIn("characters cut", capped)

    def test_repeat_guard_nudges_on_third_identical_call(self):
        results = [mh.repeat_guard("bash", {"command": "ls"}, "out") for _ in range(3)]
        self.assertEqual(results[:2], ["out", "out"])
        self.assertIn("3 times", results[2])

    def test_denied_permission_blocks_the_tool(self):
        mh.input = lambda prompt: "n"              # the user types "n" at the prompt
        try:
            call = {"function": {"name": "bash", "arguments": json.dumps({"command": "touch made.txt"})}}
            self.assertIn("denied", mh.execute(call))
            self.assertFalse((self.workspace / "made.txt").exists())
        finally:
            del mh.input


class TestLoopPieces(WorkspaceTest):
    def test_system_prompt_includes_agents_md(self):
        self.assertIn("python3 -m unittest -v", mh.system_prompt())

    def test_interrupted_tool_calls_get_results(self):
        messages = [{"role": "assistant", "content": "", "tool_calls": [{"id": "a"}, {"id": "b"}]},
                    {"role": "tool", "tool_call_id": "a", "content": "done"}]
        mh.answer_missing_tool_calls(messages)
        self.assertEqual(messages[-1], {"role": "tool", "tool_call_id": "b", "content": "Interrupted by the user."})

    def test_compaction_keeps_tool_calls_paired(self):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
        for i in range(12):
            messages.append({"role": "assistant", "content": "x" * 100, "tool_calls": [{"id": str(i)}]})
            messages.append({"role": "tool", "tool_call_id": str(i), "content": "y" * 100})
        old_limit, old_call = mh.COMPACT_AT, mh.call_model
        mh.COMPACT_AT, mh.call_model = 1000, lambda *a, **k: {"content": "SUMMARY"}
        try:
            compacted = mh.maybe_compact(messages)
        finally:
            mh.COMPACT_AT, mh.call_model = old_limit, old_call
        self.assertLess(len(compacted), len(messages))
        self.assertIn("SUMMARY", compacted[2]["content"])
        self.assertEqual(compacted[3]["role"], "assistant")      # tail starts at a call, not a result


class TestEndToEnd(WorkspaceTest):
    """Run the real CLI against the scripted fake model and check the demo gets fixed."""

    def setUp(self):
        super().setUp()
        self.server = fake_model.serve(port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.env = {**os.environ, "MINI_BASE_URL": f"http://127.0.0.1:{self.server.server_port}",
                    "NO_COLOR": "1"}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def run_harness(self, *args, stdin=""):
        return subprocess.run([sys.executable, str(ROOT / "mini_harness.py"), *args], cwd=self.workspace,
                              env=self.env, input=stdin, capture_output=True, text=True, timeout=60)

    def test_agent_fixes_the_demo(self):
        before = subprocess.run([sys.executable, "-m", "unittest"], cwd=self.workspace, capture_output=True)
        self.assertNotEqual(before.returncode, 0)
        out = self.run_harness("--yes", "Fix the failing tests")
        self.assertIn("All 4 tests pass", out.stdout, out.stderr)
        after = subprocess.run([sys.executable, "-m", "unittest"], cwd=self.workspace, capture_output=True)
        self.assertEqual(after.returncode, 0)
        log = next((self.workspace / ".mini-harness").glob("session-*.jsonl")).read_text().splitlines()
        roles = [json.loads(line)["message"]["role"] for line in log]
        self.assertEqual(roles[:2], ["system", "user"])
        self.assertEqual(roles.count("tool"), 8)

    def test_user_can_deny_an_edit(self):
        original = (self.workspace / "loader.py").read_text()
        out = self.run_harness("Fix the failing tests", stdin="y\nn\n")   # allow bash, deny the edit
        self.assertIn("won't do that", out.stdout, out.stderr)
        self.assertEqual((self.workspace / "loader.py").read_text(), original)


if __name__ == "__main__":
    unittest.main()
