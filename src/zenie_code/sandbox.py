import shutil
import tempfile
import time
from pathlib import Path

from .patcher import apply_patch, changed_files, run_command
from .verifier import run_static_checks


class SandboxManager:
    def __init__(self, repo_root: Path, exclude_dirs=None, timeout=600):
        self.repo_root = repo_root.resolve()
        self.exclude_dirs = set(exclude_dirs or [])
        self.timeout = timeout

    def _ignore(self, directory, names):
        ignored = set()
        for name in names:
            if name in self.exclude_dirs:
                ignored.add(name)
            if name in {
                ".git",
                ".zenie",
                ".local_coding_agent_graph.json",
                ".local_coding_agent_memory.jsonl",
                ".local_coding_agent_sessions",
            }:
                ignored.add(name)
        return ignored

    def create(self):
        temp_root = Path(tempfile.mkdtemp(prefix="local-agent-sandbox-"))
        sandbox_repo = temp_root / "repo"
        shutil.copytree(
            self.repo_root,
            sandbox_repo,
            ignore=self._ignore,
            dirs_exist_ok=False,
        )
        return temp_root, sandbox_repo

    def cleanup(self, temp_root):
        shutil.rmtree(temp_root, ignore_errors=True)

    def evaluate(self, diff, test_command="", static_checks=True):
        started = time.time()
        temp_root, sandbox_repo = self.create()
        try:
            applied, apply_output = apply_patch(sandbox_repo, diff)
            if not applied:
                return {
                    "apply_status": "failed",
                    "apply_output": apply_output,
                    "static_status": "skipped",
                    "static_result": {"status": "skipped", "checks": []},
                    "test_status": "skipped",
                    "test_output": "",
                    "duration_seconds": round(time.time() - started, 3),
                    "changed_files": changed_files(diff),
                }

            static_result = (
                run_static_checks(sandbox_repo)
                if static_checks
                else {"status": "skipped", "checks": []}
            )

            test_status = "skipped"
            test_output = ""
            if test_command:
                code, out, err = run_command(
                    sandbox_repo,
                    test_command,
                    timeout=self.timeout,
                )
                test_status = "passed" if code == 0 else "failed"
                test_output = (out + "\n" + err).strip()

            return {
                "apply_status": "passed",
                "apply_output": apply_output,
                "static_status": static_result.get("status", "skipped"),
                "static_result": static_result,
                "test_status": test_status,
                "test_output": test_output[-10000:],
                "duration_seconds": round(time.time() - started, 3),
                "changed_files": changed_files(diff),
            }
        finally:
            self.cleanup(temp_root)
