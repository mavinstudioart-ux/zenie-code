from __future__ import annotations


class DiagnosticFSM:
    TRANSITIONS = {
        "UNKNOWN": {"DISCOVERING"},
        "DISCOVERING": {"BASELINING", "FAILED"},
        "BASELINING": {"REPRODUCING", "LOCALIZING", "FAILED"},
        "REPRODUCING": {"LOCALIZING", "NEEDS_USER_INPUT", "FAILED"},
        "LOCALIZING": {"HYPOTHESIZING", "FAILED"},
        "HYPOTHESIZING": {"PROBING", "READY_TO_PATCH", "NEEDS_USER_INPUT", "FAILED"},
        "PROBING": {"HYPOTHESIZING", "READY_TO_PATCH", "NEEDS_USER_INPUT", "FAILED"},
        "READY_TO_PATCH": {"VERIFYING", "RESOLVED", "FAILED"},
        "VERIFYING": {"RESOLVED", "HYPOTHESIZING", "FAILED"},
        "NEEDS_USER_INPUT": {"DISCOVERING", "REPRODUCING", "LOCALIZING"},
        "RESOLVED": set(),
        "FAILED": set(),
    }

    def __init__(self, on_transition=None):
        self.state = "UNKNOWN"
        self.history = [{"state": "UNKNOWN", "note": "Session created."}]
        self.on_transition = on_transition

    def transition(self, new_state: str, note: str = ""):
        allowed = self.TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"Invalid diagnostic transition: {self.state} -> {new_state}")
        self.state = new_state
        entry = {"state": new_state, "note": note}
        self.history.append(entry)
        if self.on_transition:
            self.on_transition(new_state, note)
        return self.state
