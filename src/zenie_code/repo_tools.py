import re
from pathlib import Path


def should_skip(path: Path, exclude_dirs):
    parts = set(path.parts)
    return any(item in parts for item in exclude_dirs)


def list_repo_files(root: Path, include_ext, exclude_dirs, limit=2000):
    files = []
    for path in root.rglob("*"):
        if path.is_file() and not should_skip(path, exclude_dirs):
            if path.suffix.lower() in include_ext:
                rel = path.relative_to(root).as_posix()
                files.append(rel)
                if len(files) >= limit:
                    break
    return sorted(files)


def read_text_safe(path: Path, max_chars=20000):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"[ERROR reading {path}: {exc}]"
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[TRUNCATED]..."
    return text


def search_repo(root: Path, query: str, files, max_hits=40):
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_./-]+", query) if len(t) > 2]
    hits = []

    for rel in files:
        path = root / rel
        text = read_text_safe(path, max_chars=120000)
        lower = text.lower()
        score = 0
        for term in terms:
            if term in lower or term in rel.lower():
                score += lower.count(term) + (5 if term in rel.lower() else 0)
        if score:
            hits.append((score, rel))

    hits.sort(reverse=True)
    return [rel for _, rel in hits[:max_hits]]


def build_context(root: Path, selected_files, max_context_chars):
    chunks = []
    used = 0

    for rel in selected_files:
        path = root / rel
        text = read_text_safe(path, max_chars=30000)
        block = f"\n\n===== FILE: {rel} =====\n{text}\n"
        if used + len(block) > max_context_chars:
            break
        chunks.append(block)
        used += len(block)

    return "".join(chunks)
