TOOLS = {
    "search_code": {
        "description": "Search repository files by task keywords.",
        "args": {"query": "string"}
    },
    "read_file": {
        "description": "Read a file range with line numbers.",
        "args": {"path": "string", "start": "integer", "end": "integer"}
    },
    "generate_patch": {
        "description": "Generate a minimal unified diff patch.",
        "args": {"task": "string"}
    },
    "run_tests": {
        "description": "Run configured or custom test command.",
        "args": {"command": "string optional"}
    },
    "show_diff": {
        "description": "Show current git diff.",
        "args": {}
    }
}


def retrieve_tools(task: str):
    task_l = task.lower()
    selected = ["search_code", "read_file"]
    if any(w in task_l for w in ["fix", "perbaiki", "ubah", "edit", "implement", "bug", "error"]):
        selected.append("generate_patch")
    if any(w in task_l for w in ["test", "pytest", "gagal", "error", "bug"]):
        selected.append("run_tests")
    selected.append("show_diff")
    return {name: TOOLS[name] for name in dict.fromkeys(selected)}
