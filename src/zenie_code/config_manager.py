from __future__ import annotations

import json
import os
from pathlib import Path

from .model_manager import ModelManager

DEFAULT_CONFIG = {'base_url': 'http://127.0.0.1:8080/v1', 'api_key': 'none', 'model': 'local-coder', 'temperature': 0.15, 'candidate_temperature_step': 0.08, 'seed': 42, 'max_tokens': 6144, 'max_context_chars': 60000, 'max_files': 12, 'llm_timeout': 600, 'test_timeout': 600, 'shell_timeout': 600, 'test_command': 'python -m pytest -q', 'candidate_count': 2, 'max_candidate_count': 5, 'repair_attempts': 1, 'structured_output': True, 'enable_repo_graph': True, 'write_repo_graph': True, 'enable_reflection': True, 'enable_model_verifier': True, 'enable_static_checks': True, 'rollback_on_failure': True, 'exclude_dirs': ['.git', '.venv', 'venv', 'node_modules', 'dist', 'build', '__pycache__', '.next', '.cache', 'coverage', '.pytest_cache', '.zenie'], 'sandbox_exclude_dirs': ['.git', '.venv', 'venv', 'node_modules', 'dist', 'build', '__pycache__', '.next', '.cache', 'coverage', '.pytest_cache', '.zenie'], 'include_ext': ['.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.md', '.yml', '.yaml', '.html', '.css', '.php', '.java', '.go', '.rs', '.c', '.cpp', '.cc', '.h', '.hpp', '.rb'], 'permissions': {'apply_patch': 'ask', 'rollback_patch': 'allow', 'run_tests': 'allow', 'run_shell': 'ask', 'write_memory': 'allow', 'blocked_command_patterns': ['(^|\\s)rm\\s+-rf(\\s|$)', '(^|\\s)git\\s+reset\\s+--hard(\\s|$)', '(^|\\s)git\\s+clean\\s+-fdx?(\\s|$)', '(^|\\s)format(\\.com)?\\s', '(^|\\s)shutdown(\\.exe)?(\\s|$)', '(^|\\s)reboot(\\s|$)', '(^|\\s)del\\s+/[sq](\\s|$)', '(^|\\s)Remove-Item\\b.*-Recurse\\b.*-Force'], 'run_diagnostics': 'allow'}, 'diagnostic_patch_confidence': 0.7, 'diagnostic_max_commands': 5, 'diagnostic_command_timeout': 180, 'diagnostic_run_build': False, 'reproduction_repeat_count': 1, 'diagnostic_max_suspects': 15, 'diagnostic_source_context_chars': 40000, 'diagnostic_context_budget_chars': 60000, 'brand': 'Zenie Code', 'config_version': 1}

def user_home_dir() -> Path:
    override = os.environ.get("ZENIE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".zenie"


def user_config_path() -> Path:
    explicit = os.environ.get("ZENIE_CONFIG")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return user_home_dir() / "config.json"


def project_config_path(repo_root: Path) -> Path:
    return repo_root / ".zenie" / "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_user_config() -> tuple[Path, bool]:
    path = user_config_path()
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path, True


def load_config(repo_root: Path | None = None) -> tuple[dict, dict]:
    user_path, created = ensure_user_config()
    config = dict(DEFAULT_CONFIG)
    sources = [str(user_path)]

    try:
        user_data = json.loads(user_path.read_text(encoding="utf-8"))
        config = _deep_merge(config, user_data)
    except Exception as exc:
        raise RuntimeError(f"Invalid Zenie config: {user_path}: {exc}") from exc

    if repo_root is not None:
        project_path = project_config_path(repo_root)
        if project_path.exists():
            try:
                project_data = json.loads(
                    project_path.read_text(encoding="utf-8")
                )
                config = _deep_merge(config, project_data)
                sources.append(str(project_path))
            except Exception as exc:
                raise RuntimeError(
                    f"Invalid project Zenie config: {project_path}: {exc}"
                ) from exc

    manager = ModelManager(user_home_dir())
    config = manager.apply_active_to_config(config)

    metadata = {
        "created_user_config": created,
        "user_config_path": str(user_path),
        "sources": sources,
    }
    return config, metadata
