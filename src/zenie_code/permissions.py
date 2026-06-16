import re

DEFAULT_BLOCKED_PATTERNS = [
    r"(^|\s)rm\s+-rf(\s|$)",
    r"(^|\s)git\s+reset\s+--hard(\s|$)",
    r"(^|\s)git\s+clean\s+-fdx?(\s|$)",
    r"(^|\s)format(\.com)?\s",
    r"(^|\s)shutdown(\.exe)?(\s|$)",
    r"(^|\s)reboot(\s|$)",
    r"(^|\s)del\s+/[sq](\s|$)",
    r"(^|\s)Remove-Item\b.*-Recurse\b.*-Force",
]


class PermissionManager:
    VALID_MODES = {"allow", "ask", "deny"}

    def __init__(self, config=None, auto_approve=False, approval_callback=None):
        config = config or {}
        self.rules = {
            "apply_patch": config.get("apply_patch", "ask"),
            "rollback_patch": config.get("rollback_patch", "allow"),
            "run_tests": config.get("run_tests", "allow"),
            "run_diagnostics": config.get("run_diagnostics", "allow"),
            "run_shell": config.get("run_shell", "ask"),
            "write_memory": config.get("write_memory", "allow"),
        }
        self.auto_approve = auto_approve
        self.approval_callback = approval_callback
        self.blocked_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in config.get("blocked_command_patterns", DEFAULT_BLOCKED_PATTERNS)
        ]

    def describe(self):
        return dict(self.rules)

    def set_mode(self, action, mode):
        if action not in self.rules:
            raise KeyError(f"Unknown action: {action}")
        if mode not in self.VALID_MODES:
            raise ValueError(f"Mode must be one of: {sorted(self.VALID_MODES)}")
        self.rules[action] = mode

    def command_block_reason(self, command):
        for pattern in self.blocked_patterns:
            if pattern.search(command or ""):
                return f"Command blocked by safety pattern: {pattern.pattern}"
        return None

    def authorize(self, action, detail=""):
        if action in {"run_shell", "run_tests", "run_diagnostics"}:
            reason = self.command_block_reason(detail)
            if reason:
                return False, reason

        mode = self.rules.get(action, "ask")
        if mode == "allow":
            return True, "allowed"
        if mode == "deny":
            return False, f"Permission denied by policy: {action}"
        if self.auto_approve:
            return True, "auto-approved"
        if self.approval_callback:
            approved = bool(self.approval_callback(action, detail))
            return approved, "approved" if approved else "not approved"
        return False, f"Permission requires confirmation: {action}"
