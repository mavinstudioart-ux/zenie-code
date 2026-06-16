from __future__ import annotations

import json


def _trim(text: str, budget: int):
    text = text or ""
    if len(text) <= budget:
        return text
    if budget < 200:
        return text[:budget]
    head = int(budget * 0.72)
    tail = budget - head - 35
    return text[:head] + "\n...[CONTEXT TRIMMED]...\n" + text[-tail:]


class ContextBudgetManager:
    def __init__(self, total_chars=60000):
        self.total_chars = max(8000, int(total_chars))

    def build(
        self,
        requirement: dict,
        profile: dict,
        baseline: dict,
        reproduction: dict,
        suspects: list[dict],
        hypotheses: list[dict],
        source_context: str,
        graph_text: str,
    ):
        allocations = {
            "requirement": int(self.total_chars * 0.08),
            "profile": int(self.total_chars * 0.08),
            "baseline": int(self.total_chars * 0.15),
            "reproduction": int(self.total_chars * 0.20),
            "suspects": int(self.total_chars * 0.09),
            "hypotheses": int(self.total_chars * 0.10),
            "graph": int(self.total_chars * 0.10),
            "source": int(self.total_chars * 0.20),
        }
        sections = {
            "requirement": json.dumps(requirement, ensure_ascii=False, indent=2),
            "profile": json.dumps(profile, ensure_ascii=False, indent=2),
            "baseline": json.dumps(baseline, ensure_ascii=False, indent=2),
            "reproduction": json.dumps(reproduction, ensure_ascii=False, indent=2),
            "suspects": json.dumps(suspects, ensure_ascii=False, indent=2),
            "hypotheses": json.dumps(hypotheses, ensure_ascii=False, indent=2),
            "graph": graph_text,
            "source": source_context,
        }
        rendered = []
        used = 0
        for name, text in sections.items():
            trimmed = _trim(text, allocations[name])
            rendered.append(f"===== {name.upper()} =====\n{trimmed}")
            used += len(trimmed)
        return {
            "text": "\n\n".join(rendered),
            "used_chars": used,
            "budget_chars": self.total_chars,
            "allocations": allocations,
        }
