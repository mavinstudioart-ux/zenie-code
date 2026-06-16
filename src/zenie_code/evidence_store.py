from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path


class EvidenceStore:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.base_dir = repo_root / ".zenie" / "sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = None
        self.session_path = None
        self.report = None

    def start(self, symptom: str, profile: dict):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.session_id = f"{stamp}-{secrets.token_hex(3)}"
        self.session_path = self.base_dir / f"{self.session_id}.json"
        self.report = {
            "session_id": self.session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "symptom": symptom,
            "profile": profile,
            "evidence": [],
            "state_history": [],
        }
        self.save()
        return self.session_id

    def add(self, kind: str, data, source: str, confidence: float = 1.0):
        if self.report is None:
            raise RuntimeError("Evidence session has not been started.")
        item = {
            "id": len(self.report["evidence"]) + 1,
            "kind": kind,
            "source": source,
            "confidence": round(float(confidence), 4),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self.report["evidence"].append(item)
        self.save()
        return item

    def set_field(self, key: str, value):
        if self.report is None:
            raise RuntimeError("Evidence session has not been started.")
        self.report[key] = value
        self.save()

    def add_state(self, state: str, note: str = ""):
        if self.report is None:
            raise RuntimeError("Evidence session has not been started.")
        self.report["state_history"].append({
            "state": state,
            "note": note,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self.save()

    def save(self):
        if self.session_path is None or self.report is None:
            return
        self.session_path.write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def render(self):
        if not self.report:
            return "No diagnostic evidence is available."
        lines = [
            f"Session: {self.report['session_id']}",
            f"Symptom: {self.report['symptom']}",
            "",
        ]
        for item in self.report.get("evidence", []):
            lines.append(
                f"[{item['id']}] {item['kind']} "
                f"(source={item['source']}, confidence={item['confidence']})"
            )
            serialized = json.dumps(item["data"], ensure_ascii=False, indent=2)
            lines.append(serialized[:5000])
            lines.append("")
        return "\n".join(lines)
