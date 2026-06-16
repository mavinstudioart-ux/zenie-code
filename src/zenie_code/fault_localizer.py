from __future__ import annotations

import subprocess
from pathlib import Path


def _recent_files(root: Path):
    try:
        result = subprocess.run(
            ["git", "log", "-n", "10", "--name-only", "--pretty=format:"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=20,
        )
        return {
            line.strip().replace("\\", "/")
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except Exception:
        return set()


def _normalize_location_path(raw: str, repo_files: set[str]):
    raw = raw.replace("\\", "/")
    if raw in repo_files:
        return raw
    for rel in repo_files:
        if raw.endswith(rel) or rel.endswith(raw):
            return rel
    basename = Path(raw).name
    matches = [rel for rel in repo_files if Path(rel).name == basename]
    return matches[0] if len(matches) == 1 else None


def localize(
    root: Path,
    symptom: str,
    repo_files: list[str],
    repo_graph: dict,
    reproduction: dict,
    baseline: dict,
    keyword_files: list[str],
    limit: int = 15,
):
    files_set = set(repo_files)
    recent = _recent_files(root)
    scores = {}

    def add(path, amount, reason):
        if path not in files_set:
            return
        record = scores.setdefault(path, {"score": 0.0, "evidence": []})
        record["score"] += amount
        if reason not in record["evidence"]:
            record["evidence"].append(reason)

    for location in reproduction.get("locations", []):
        path = _normalize_location_path(location["path"], files_set)
        if path:
            add(path, 0.42, f"Appears in reproduced stack/output at line {location['line']}")

    for index, path in enumerate(keyword_files[:20]):
        add(path, max(0.04, 0.18 - index * 0.008), "Matches symptom or error keywords")

    output = "\n".join(
        attempt.get("output", "")
        for attempt in reproduction.get("attempts", [])
    ).lower()
    for path in repo_files:
        basename = Path(path).name.lower()
        if basename and basename in output:
            add(path, 0.22, "Filename appears in failure output")
        if path in recent:
            add(path, 0.08, "Recently changed in Git history")
        if path.startswith(("tests/", "test/", "spec/")) and (
            "test" in output or "assert" in output or "failed" in output
        ):
            add(path, 0.05, "Test file may encode the failing behavior")

    primary = baseline.get("primary_failure") or {}
    primary_output = primary.get("output", "").lower()
    for path in repo_files:
        if Path(path).name.lower() in primary_output:
            add(path, 0.20, "Filename appears in baseline failure")

    # One-hop graph expansion from high-scoring files.
    seeds = sorted(scores, key=lambda item: scores[item]["score"], reverse=True)[:6]
    for seed in seeds:
        seed_module = seed.rsplit(".", 1)[0].replace("/", ".")
        for path, info in repo_graph.items():
            imports = " ".join(info.get("imports", []))
            if seed_module and seed_module in imports:
                add(path, 0.06, f"Imports or references suspect module {seed}")

    suspects = []
    for path, record in scores.items():
        suspects.append({
            "path": path,
            "symbol": None,
            "lines": [],
            "score": round(min(record["score"], 1.0), 4),
            "evidence": record["evidence"],
        })
    suspects.sort(key=lambda item: item["score"], reverse=True)
    return suspects[:limit]
