from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .agent_core import CodingAgent
from .branding import banner, heading
from .config_manager import ensure_user_config, user_config_path, user_home_dir
from .console import AgentConsole
from .model_manager import ModelManager
from .model_wizard import add_external, add_llamacpp, first_run_wizard, scan_and_add


def build_parser():
    parser = argparse.ArgumentParser(
        prog="zenie",
        description="Zenie Code — local agentic coding CLI",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Task. Leave empty to open the interactive CLI.",
    )
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--dry-run", action="store_true", help="Rank candidates only")
    parser.add_argument("--auto", action="store_true", help="Apply the best candidate")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--candidates", type=int, default=None)
    parser.add_argument("--test", default=None)
    parser.add_argument("--no-rollback", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--no-banner", action="store_true")
    parser.add_argument("--config-path", action="store_true")
    parser.add_argument("--version", action="version", version=f"Zenie Code {__version__}")
    return parser


def handle_model_command(argv):
    if not argv or argv[0] != "model":
        return False

    manager = ModelManager(user_home_dir())
    action = argv[1] if len(argv) > 1 else "list"

    if action == "list":
        profiles = manager.list_profiles()
        if not profiles:
            print("No model profiles configured.")
        for item in profiles:
            mark = "*" if item.get("active") else " "
            print(
                f"{mark} {item['name']} | {item.get('provider')} | "
                f"{item.get('status')} | "
                f"{item.get('model', item.get('model_path', ''))}"
            )
        return True

    if action == "use":
        if len(argv) < 3:
            raise SystemExit("Usage: zenie model use <name>")
        profile = manager.use(argv[2])
        print(f"Active model: {profile['name']}")
        return True

    if action == "start":
        name = argv[2] if len(argv) > 2 else None
        print(manager.start(name))
        return True

    if action == "stop":
        name = argv[2] if len(argv) > 2 else None
        print(manager.stop(name))
        return True

    if action == "remove":
        if len(argv) < 3:
            raise SystemExit("Usage: zenie model remove <name>")
        manager.remove(argv[2])
        print(f"Removed model profile: {argv[2]}")
        return True

    if action == "scan":
        directory = argv[2] if len(argv) > 2 else None
        if directory:
            models = manager.scan_gguf(directory)
            for item in models:
                print(item)
        else:
            scan_and_add(manager)
        return True

    if action == "add":
        provider = argv[2] if len(argv) > 2 else None
        if provider == "llama.cpp":
            profile = add_llamacpp(manager)
        elif provider in {"ollama", "lmstudio", "openai-compatible", "litellm"}:
            profile = add_external(manager, provider)
        else:
            profile = first_run_wizard(manager)
        if profile:
            print(f"Added model profile: {profile['name']}")
        return True

    raise SystemExit(
        "Usage: zenie model [list|add|scan|use|start|stop|remove]"
    )


def main():
    if handle_model_command(sys.argv[1:]):
        return

    parser = build_parser()
    args = parser.parse_args()

    if args.config_path:
        ensure_user_config()
        print(user_config_path())
        return

    if not args.no_banner:
        print(banner(__version__))
        print()

    agent_dir = Path(__file__).resolve().parent
    agent = CodingAgent(
        repo_root=Path(args.repo),
        agent_dir=agent_dir,
        test_command=args.test,
        auto_approve=args.yes,
    )

    if agent.config_metadata.get("created_user_config"):
        print(
            heading("First-run configuration created:")
            + f" {agent.config_metadata['user_config_path']}"
        )
        print("Edit base_url, model, and test_command when needed.\n")

    if args.no_rollback:
        agent.config["rollback_on_failure"] = False

    task = " ".join(args.task).strip()
    if not task:
        AgentConsole(agent).cmdloop()
        return

    if args.diagnose or agent.route_direct_input(task) == "diagnose":
        print(agent.diagnose_project(task))
        return

    ranked = agent.generate_and_rank(task, candidate_count=args.candidates)
    print(agent.format_candidate_summary(ranked))
    print("\n--- BEST PATCH ---\n")
    print(ranked["best"]["diff"])

    if args.dry_run:
        return

    if args.auto:
        print(agent.apply_candidate(ranked["best"], task))
        return

    if input("Apply best patch? [y/N] ").strip().lower() == "y":
        agent.permission_manager.auto_approve = True
        print(agent.apply_candidate(ranked["best"], task))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Zenie error: {exc}", file=sys.stderr)
        raise SystemExit(1)
