import ast
import json
import re
from pathlib import Path

from .repo_tools import read_text_safe

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".php": "php",
    ".rb": "ruby",
}


def _tree_sitter_parser(language):
    try:
        from tree_sitter_language_pack import get_parser
        return get_parser(language)
    except Exception:
        pass
    try:
        from tree_sitter_languages import get_parser
        return get_parser(language)
    except Exception:
        return None


def _node_text(node, source_bytes):
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def summarize_tree_sitter(rel_path, text, language):
    parser = _tree_sitter_parser(language)
    if parser is None:
        return None

    source = text.encode("utf-8")
    tree = parser.parse(source)
    symbols = []
    imports = []

    symbol_types = {
        "function_definition": "function",
        "function_declaration": "function",
        "method_definition": "method",
        "method_declaration": "method",
        "class_definition": "class",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "struct_item": "struct",
        "function_item": "function",
        "impl_item": "impl",
    }
    import_types = {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "use_declaration",
        "use_declaration",
        "require_expression",
    }

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in symbol_types:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                symbols.append({
                    "type": symbol_types[node.type],
                    "name": _node_text(name_node, source),
                    "line": node.start_point[0] + 1,
                })
        elif node.type in import_types:
            imports.append(_node_text(node, source).strip()[:300])
        stack.extend(reversed(node.children))

    return {
        "path": rel_path,
        "language": language,
        "parser": "tree-sitter",
        "imports": imports[:80],
        "classes": [s["name"] for s in symbols if s["type"] == "class"],
        "functions": [
            s["name"]
            for s in symbols
            if s["type"] in {"function", "method"}
        ],
        "symbols": symbols[:300],
    }


def summarize_python_ast(rel_path, text):
    result = {
        "path": rel_path,
        "language": "python",
        "parser": "python-ast",
        "imports": [],
        "classes": [],
        "functions": [],
        "symbols": [],
    }
    try:
        tree = ast.parse(text)
    except Exception:
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result["imports"].append(node.module or "")
        elif isinstance(node, ast.ClassDef):
            result["classes"].append(node.name)
            result["symbols"].append({
                "type": "class",
                "name": node.name,
                "line": node.lineno,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append(node.name)
            result["symbols"].append({
                "type": "function",
                "name": node.name,
                "line": node.lineno,
            })
    return result


def summarize_regex(rel_path, text, language="generic"):
    names = []
    patterns = [
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"\bconst\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    ]
    for pattern in patterns:
        names.extend(re.findall(pattern, text))
    classes = re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    return {
        "path": rel_path,
        "language": language,
        "parser": "regex",
        "imports": re.findall(
            r"^\s*(?:import|from|require\(|include|use)\s+(.+)$",
            text,
            re.MULTILINE,
        )[:80],
        "classes": sorted(set(classes))[:80],
        "functions": sorted(set(names))[:160],
        "symbols": [],
    }


def summarize_file(rel_path, text):
    language = LANGUAGE_BY_SUFFIX.get(Path(rel_path).suffix.lower(), "generic")
    tree_sitter = summarize_tree_sitter(rel_path, text, language)
    if tree_sitter is not None:
        return tree_sitter
    if language == "python":
        return summarize_python_ast(rel_path, text)
    return summarize_regex(rel_path, text, language)


def build_repo_graph(root: Path, files, max_file_chars=200000):
    graph = {}
    for rel in files:
        text = read_text_safe(root / rel, max_chars=max_file_chars)
        graph[rel] = summarize_file(rel, text)
    return graph


def graph_to_text(graph, limit=300):
    lines = []
    for index, (path, info) in enumerate(graph.items()):
        if index >= limit:
            lines.append("...[GRAPH TRUNCATED]...")
            break
        parts = [f"parser={info.get('parser', 'unknown')}"]
        if info.get("classes"):
            parts.append("classes=" + ",".join(info["classes"][:12]))
        if info.get("functions"):
            parts.append("functions=" + ",".join(info["functions"][:20]))
        if info.get("imports"):
            parts.append("imports=" + ",".join(info["imports"][:8]))
        lines.append(f"{path}: " + "; ".join(parts))
    return "\n".join(lines)


def save_graph(root: Path, graph):
    data_dir = root / ".zenie"
    data_dir.mkdir(exist_ok=True)
    path = data_dir / "repo_graph.json"
    path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
