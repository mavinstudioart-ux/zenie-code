from __future__ import annotations

import json
import os
from pathlib import Path

from .patcher import git_status, run_command


def _manifest_checks(root: Path, profile: dict):
    checks = []
    for manifest in profile.get("manifests", []):
        path = root / manifest
        status = "passed"
        output = ""
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif manifest == "pyproject.toml":
                import tomllib
                tomllib.loads(path.read_text(encoding="utf-8"))
            elif not path.exists():
                status = "failed"
                output = "Manifest disappeared after profiling."
        except Exception as exc:
            status = "failed"
            output = str(exc)
        checks.append({
            "name": f"manifest:{manifest}",
            "category": "manifest",
            "command": None,
            "status": status,
            "exit_code": 0 if status == "passed" else 1,
            "output": output,
        })
    return checks


def _environment_checks(root: Path, profile: dict):
    required = profile.get("environment", {}).get("required_keys", [])
    if not required:
        return []

    env_file_exists = any(
        (root / name).exists()
        for name in [".env", ".env.local", ".env.development", ".env.production"]
    )
    missing_process = [key for key in required if key not in os.environ]
    return [{
        "name": "environment_configuration",
        "category": "environment",
        "command": None,
        "status": "warning" if missing_process and not env_file_exists else "passed",
        "exit_code": 0,
        "output": (
            "Required keys not visible in the current process and no runtime .env file "
            f"was detected: {', '.join(missing_process)}"
            if missing_process and not env_file_exists
            else "Environment declaration detected."
        ),
    }]


def _command_candidates(profile: dict, config: dict):
    commands = profile.get("commands", {})
    order = ["static", "check", "typecheck", "lint", "test"]
    if config.get("diagnostic_run_build", False):
        order.append("build")

    selected = []
    seen = set()
    for category in order:
        command = commands.get(category)
        if command and command not in seen:
            selected.append((category, command))
            seen.add(command)
    return selected[: config.get("diagnostic_max_commands", 5)]


def run_baseline(
    root: Path,
    profile: dict,
    config: dict,
    permission_manager,
):
    checks = []
    checks.extend(_manifest_checks(root, profile))
    checks.extend(_environment_checks(root, profile))

    checks.append({
        "name": "git_status",
        "category": "repository",
        "command": "git status --short",
        "status": "passed",
        "exit_code": 0,
        "output": git_status(root).strip(),
    })

    for category, command in _command_candidates(profile, config):
        allowed, reason = permission_manager.authorize("run_diagnostics", command)
        if not allowed:
            checks.append({
                "name": category,
                "category": category,
                "command": command,
                "status": "skipped",
                "exit_code": None,
                "output": reason,
            })
            continue

        code, stdout, stderr = run_command(
            root,
            command,
            timeout=config.get("diagnostic_command_timeout", 180),
        )
        output = (stdout + "\n" + stderr).strip()
        checks.append({
            "name": category,
            "category": category,
            "command": command,
            "status": "passed" if code == 0 else "failed",
            "exit_code": code,
            "output": output[-12000:],
        })

    failures = [item for item in checks if item["status"] == "failed"]
    warnings = [item for item in checks if item["status"] == "warning"]
    return {
        "status": "failed" if failures else ("warning" if warnings else "passed"),
        "checks": checks,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "primary_failure": failures[0] if failures else None,
    }
