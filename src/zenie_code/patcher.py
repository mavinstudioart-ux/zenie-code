import re
import subprocess
import tempfile
from pathlib import Path


def extract_unified_diff(text: str) -> str:
    fenced = re.search(r"```(?:diff|patch)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        candidate = text.strip()

    lines = candidate.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- "):
            start = i
            break
    if start is None:
        return ""
    return "\n".join(lines[start:]).strip() + "\n"


def has_diff(diff: str) -> bool:
    return bool(diff) and (
        ("--- " in diff and "+++ " in diff and "@@" in diff)
        or diff.startswith("diff --git")
    )


def changed_files(diff: str):
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                continue
            if path.startswith("b/"):
                path = path[2:]
            if path not in files:
                files.append(path)
    return files


def changed_line_count(diff: str):
    return sum(
        1
        for line in diff.splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    )


def _write_temp_patch(diff):
    f = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        suffix=".patch",
        encoding="utf-8",
        newline="\n",
    )
    try:
        f.write(diff)
        return Path(f.name)
    finally:
        f.close()


def check_patch(repo_root: Path, diff: str):
    patch_path = _write_temp_patch(diff)
    try:
        result = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    finally:
        patch_path.unlink(missing_ok=True)


def apply_patch(repo_root: Path, diff: str):
    patch_path = _write_temp_patch(diff)
    try:
        check = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if check.returncode != 0:
            return False, "git apply --check failed:\n" + check.stderr + check.stdout

        result = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return False, "git apply failed:\n" + result.stderr + result.stdout
        return True, "Patch applied."
    finally:
        patch_path.unlink(missing_ok=True)


def rollback_patch(repo_root: Path, diff: str):
    patch_path = _write_temp_patch(diff)
    try:
        check = subprocess.run(
            ["git", "apply", "--reverse", "--check", str(patch_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if check.returncode != 0:
            return False, "Reverse check failed:\n" + check.stderr + check.stdout

        result = subprocess.run(
            ["git", "apply", "--reverse", str(patch_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return False, "Rollback failed:\n" + result.stderr + result.stdout
        return True, "Patch rolled back."
    finally:
        patch_path.unlink(missing_ok=True)


def git_diff(repo_root: Path):
    result = subprocess.run(
        ["git", "diff"],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    return result.stdout + result.stderr


def git_status(repo_root: Path):
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    return result.stdout + result.stderr


def run_command(repo_root: Path, command: str, timeout=600):
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            capture_output=True,
            shell=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        return 124, out, err + f"\nCommand timed out after {timeout} seconds."
