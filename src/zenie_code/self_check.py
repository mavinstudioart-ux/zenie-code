import tempfile
from pathlib import Path

from .context_budget import ContextBudgetManager
from .diagnostic_fsm import DiagnosticFSM
from .evidence_store import EvidenceStore
from .patcher import apply_patch, rollback_patch
from .permissions import PermissionManager
from .project_profiler import profile_repository
from .repo_graph import build_repo_graph
from .reproduction_engine import extract_error_signature, extract_locations
from .requirement_refiner import is_vague_request


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "tests").mkdir()
        source = root / "sample.py"
        source.write_text(
            "def add(a, b):\n    return a - b\n",
            encoding="utf-8",
        )
        (root / "tests" / "test_sample.py").write_text(
            "from sample import add\n\n"
            "def test_add():\n"
            "    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            "[project]\nname='sample'\nversion='0.1.0'\n",
            encoding="utf-8",
        )

        diff = """--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
        ok, message = apply_patch(root, diff)
        assert ok, message
        assert "a + b" in source.read_text(encoding="utf-8")

        ok, message = rollback_patch(root, diff)
        assert ok, message
        assert "a - b" in source.read_text(encoding="utf-8")

        files = ["sample.py", "tests/test_sample.py", "pyproject.toml"]
        graph = build_repo_graph(root, files)
        assert "add" in graph["sample.py"]["functions"]

        profile = profile_repository(root, files)
        assert "Python" in profile["ecosystems"]
        assert profile["commands"]["static"] == "python -m compileall -q ."

        assert is_vague_request("cek project ini")
        assert not is_vague_request("perbaiki fungsi add agar menjumlahkan dua angka")

        signature = extract_error_signature(
            'File "sample.py", line 2\nAssertionError: expected 5'
        )
        locations = extract_locations(
            'File "sample.py", line 2, in add\nAssertionError'
        )
        assert "AssertionError" in signature
        assert locations[0]["path"] == "sample.py"

        fsm = DiagnosticFSM()
        fsm.transition("DISCOVERING")
        fsm.transition("BASELINING")
        assert fsm.state == "BASELINING"

        store = EvidenceStore(root)
        store.start("sample fails", profile)
        store.add("test", {"status": "failed"}, "self_check")
        assert store.session_path.exists()

        bundle = ContextBudgetManager(10000).build(
            {"symptom": "x"}, profile, {}, {}, [], [], "source", "graph"
        )
        assert bundle["used_chars"] <= bundle["budget_chars"]

        permissions = PermissionManager({
            "run_shell": "allow",
            "run_diagnostics": "allow",
        })
        allowed, _ = permissions.authorize("run_shell", "rm -rf .")
        assert not allowed
        allowed, _ = permissions.authorize(
            "run_diagnostics",
            "python -m pytest -q",
        )
        assert allowed

    print("Self-check passed.")


if __name__ == "__main__":
    main()
