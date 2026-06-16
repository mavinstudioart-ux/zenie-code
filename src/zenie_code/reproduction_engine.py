from __future__ import annotations

import re
from pathlib import Path

from .patcher import run_command

ERROR_PATTERNS = [
    re.compile(r"(?i)(traceback \(most recent call last\):)"),
    re.compile(r"(?i)\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b[:\s]*(.*)"),
    re.compile(r"(?i)\b(error|failed|failure|fatal)\b[:\s-]*(.*)"),
    re.compile(r"(?i)(module not found|cannot find module|connection refused|timed out)"),
]

LOCATION_PATTERNS = [
    re.compile(r'File "([^"]+)", line (\d+)'),
    re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+):(\d+)(?::\d+)?"),
    re.compile(r"\(([^()]+\.[A-Za-z0-9]+):(\d+):\d+\)"),
]


def extract_error_signature(output: str):
    lines = (output or "").splitlines()
    signature_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern.search(stripped) for pattern in ERROR_PATTERNS):
            signature_lines.append(stripped)
        if len(signature_lines) >= 5:
            break
    if not signature_lines:
        signature_lines = [line.strip() for line in lines[-5:] if line.strip()]
    return " | ".join(signature_lines)[:1200]


def extract_locations(output: str):
    locations = []
    for pattern in LOCATION_PATTERNS:
        for match in pattern.finditer(output or ""):
            item = {
                "path": match.group(1).replace("\\", "/"),
                "line": int(match.group(2)),
            }
            if item not in locations:
                locations.append(item)
    return locations[:30]


def choose_reproduction_command(profile: dict, baseline: dict | None = None):
    if baseline and baseline.get("primary_failure"):
        command = baseline["primary_failure"].get("command")
        if command:
            return command

    commands = profile.get("commands", {})
    for key in ["test", "check", "typecheck", "lint", "build"]:
        if commands.get(key):
            return commands[key]
    return None


def reproduce(
    root: Path,
    profile: dict,
    config: dict,
    permission_manager,
    baseline: dict | None = None,
    explicit_command: str | None = None,
):
    command = explicit_command or choose_reproduction_command(profile, baseline)
    if not command:
        return {
            "status": "unavailable",
            "reproduced": False,
            "command": None,
            "attempts": [],
            "error_signature": "",
            "locations": [],
            "message": "No safe reproduction command was detected.",
        }

    allowed, reason = permission_manager.authorize("run_diagnostics", command)
    if not allowed:
        return {
            "status": "denied",
            "reproduced": False,
            "command": command,
            "attempts": [],
            "error_signature": "",
            "locations": [],
            "message": reason,
        }

    attempts = []
    repeat_count = max(1, min(config.get("reproduction_repeat_count", 1), 2))
    signatures = []
    for _ in range(repeat_count):
        code, stdout, stderr = run_command(
            root,
            command,
            timeout=config.get("diagnostic_command_timeout", 180),
        )
        output = (stdout + "\n" + stderr).strip()
        signature = extract_error_signature(output)
        signatures.append(signature)
        attempts.append({
            "exit_code": code,
            "output": output[-16000:],
            "error_signature": signature,
        })

    first = attempts[0]
    reproduced = first["exit_code"] != 0
    repeatable = (
        len(attempts) == 1
        or all(signature == signatures[0] for signature in signatures)
    )
    return {
        "status": "reproduced" if reproduced else "not_reproduced",
        "reproduced": reproduced,
        "repeatable": repeatable,
        "command": command,
        "attempts": attempts,
        "error_signature": first["error_signature"],
        "locations": extract_locations(first["output"]),
        "message": (
            "Failure reproduced."
            if reproduced
            else "The selected command completed successfully."
        ),
    }
