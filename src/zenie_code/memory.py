import json
from datetime import datetime
from pathlib import Path


class AgentMemory:
    def __init__(self, repo_root: Path):
        data_dir = repo_root / ".zenie"
        data_dir.mkdir(exist_ok=True)
        self.path = data_dir / "memory.jsonl"

    def append(self, record):
        record = dict(record)
        record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent(self, limit=5):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except Exception:
                pass
        return records
