from pathlib import Path

from .patcher import changed_files, changed_line_count, run_command


def detect_static_commands(repo_root: Path):
    commands = []
    if list(repo_root.rglob("*.py")):
        commands.append(("python_compileall", "python -m compileall -q ."))
    if (repo_root / "package.json").exists():
        commands.append(("npm_lint", "npm run lint --if-present"))
    if (repo_root / "go.mod").exists():
        commands.append(("go_test_compile", "go test ./..."))
    if (repo_root / "Cargo.toml").exists():
        commands.append(("cargo_check", "cargo check"))
    return commands


def run_static_checks(repo_root: Path, timeout=300):
    checks = []
    for name, command in detect_static_commands(repo_root):
        code, out, err = run_command(repo_root, command, timeout=timeout)
        checks.append({
            "name": name,
            "command": command,
            "code": code,
            "status": "passed" if code == 0 else "failed",
            "output": (out + "\n" + err).strip()[-6000:],
        })
    if not checks:
        return {"status": "skipped", "checks": []}
    status = "passed" if all(item["code"] == 0 for item in checks) else "failed"
    return {"status": status, "checks": checks}


def score_candidate(
    diff,
    apply_status,
    static_status="skipped",
    test_status="skipped",
    model_verdict="needs_tests",
):
    if apply_status != "passed":
        return -1000.0

    score = 25.0
    if static_status == "passed":
        score += 20
    elif static_status == "failed":
        score -= 45

    if test_status == "passed":
        score += 100
    elif test_status == "failed":
        score -= 90

    if model_verdict == "accept":
        score += 12
    elif model_verdict == "reject":
        score -= 40

    line_count = changed_line_count(diff)
    file_count = len(changed_files(diff))
    score -= min(line_count * 0.04, 25)
    score -= max(0, file_count - 3) * 8
    return round(score, 2)


def verification_summary(static_result, test_status, test_output):
    return {
        "static_status": static_result.get("status", "skipped"),
        "static_checks": static_result.get("checks", []),
        "test_status": test_status,
        "test_output": (test_output or "")[-8000:],
    }
