import cmd
import json
import shlex

from .agent_core import CodingAgent
from .branding import prompt
from .config_manager import user_home_dir
from .model_manager import ModelManager
from .model_wizard import first_run_wizard

HELP_TEXT = """
Diagnosis:
  /inspect                            Profile the repository without changing files
  /diagnose <symptom>                 Run discovery, baseline, reproduction, localization, hypotheses
  /reproduce [command]                Reproduce with detected or explicit command
  /hypotheses                         Show ranked causes and next probes
  /evidence                           Show collected diagnostic evidence
  /questions                          Show information still needed from the user
  /explain                            Explain diagnosis in nontechnical language
  /fix [extra instruction]            Patch only after diagnosis passes confidence gate

Coding:
  /plan <task>                        Produce a coding plan
  /files <query>                      Find relevant files
  /read <path> [start] [end]          Read a file range
  /ask <question>                     Ask without editing
  /edit <task>                        Rank candidates and ask before applying
  /auto <task>                        Rank and apply best candidate
  /candidates <n> <task>              Compare n candidates
  /diff                               Show git diff
  /test [command]                     Run tests
  /run <command>                      Run shell command through permission gate
  /undo                               Reverse last applied agent patch

Session:
  /model                              Choose active model
  /models                             List model profiles
  /model-start                        Start active model
  /model-stop                         Stop active model
  /status
  /memory
  /permissions
  /permission <action> <allow|ask|deny>
  /clear
  /exit

A vague direct request such as "cek project ini" automatically starts diagnosis.
"""


class AgentConsole(cmd.Cmd):
    intro = None
    prompt = prompt()

    def __init__(self, agent: CodingAgent):
        super().__init__()
        self.agent = agent
        self.agent.set_approval_callback(self.ask_permission)

    def ask_permission(self, action, detail):
        print(f"\nPermission requested: {action}")
        if detail:
            print(detail)
        return input("Allow? [y/N] ").strip().lower() == "y"

    def default(self, line):
        line = line.strip()
        if not line:
            return
        if line.startswith("/"):
            command, *rest = line[1:].split(" ", 1)
            arg = rest[0] if rest else ""
            handler = getattr(self, f"slash_{command}", None)
            if handler:
                return handler(arg)
            print(f"Unknown command: /{command}")
            return

        if self.agent.route_direct_input(line) == "diagnose":
            print("Zenie detected an underspecified request; starting diagnosis instead of patching.")
            return self.slash_diagnose(line)
        return self.slash_edit(line)

    def slash_help(self, arg):
        print(HELP_TEXT)


    def slash_models(self, arg):
        manager = ModelManager(user_home_dir())
        profiles = manager.list_profiles()
        if not profiles:
            print("No model profiles configured.")
            return
        for item in profiles:
            mark = "*" if item.get("active") else " "
            print(
                f"{mark} {item['name']} | {item.get('provider')} | "
                f"{item.get('model', item.get('model_path', ''))} | "
                f"{item.get('status')}"
            )

    def slash_model(self, arg):
        manager = ModelManager(user_home_dir())
        profiles = manager.list_profiles()
        if not profiles:
            profile = first_run_wizard(manager)
            if profile:
                print(f"Active model: {profile['name']}")
            return

        for i, item in enumerate(profiles, start=1):
            mark = "*" if item.get("active") else " "
            print(f"{i}. {mark} {item['name']} [{item.get('provider')}]")
        raw = input("Select model number, or A to add: ").strip().lower()
        if raw == "a":
            profile = first_run_wizard(manager)
        else:
            profile = manager.use(profiles[int(raw) - 1]["name"])
        if profile:
            self.agent.config = manager.apply_active_to_config(self.agent.config)
            print(f"Active model: {profile['name']}")

    def slash_model_start(self, arg):
        manager = ModelManager(user_home_dir())
        print(manager.start(arg.strip() or None))

    def slash_model_stop(self, arg):
        manager = ModelManager(user_home_dir())
        print(manager.stop(arg.strip() or None))

    def slash_status(self, arg):
        print(self.agent.status())

    def slash_inspect(self, arg):
        print(self.agent.inspect_project())

    def slash_diagnose(self, arg):
        symptom = arg.strip() or "Project is not working correctly; inspect and diagnose it."
        print(self.agent.diagnose_project(symptom))

    def slash_reproduce(self, arg):
        print(self.agent.reproduce_issue(arg.strip() or None))

    def slash_hypotheses(self, arg):
        print(self.agent.show_hypotheses())

    def slash_evidence(self, arg):
        print(self.agent.show_evidence())

    def slash_questions(self, arg):
        print(self.agent.diagnosis_questions())

    def slash_explain(self, arg):
        print(self.agent.explain_diagnosis())

    def slash_fix(self, arg):
        try:
            task, ranked = self.agent.generate_fix_from_diagnosis(arg.strip())
        except Exception as exc:
            print(f"Cannot fix yet: {exc}")
            return
        print("\nDerived fix task:\n" + task)
        print("\n" + self.agent.format_candidate_summary(ranked))
        print("\n--- BEST PATCH ---\n")
        print(ranked["best"]["diff"])
        if input("Apply diagnosed patch? [y/N] ").strip().lower() == "y":
            print(self.agent.apply_candidate(ranked["best"], task))
        else:
            print("Patch not applied.")

    def slash_plan(self, arg):
        if not arg.strip():
            print("Usage: /plan <task>")
            return
        print(json.dumps(
            self.agent.plan_task(arg.strip()),
            ensure_ascii=False,
            indent=2,
        ))

    def slash_files(self, arg):
        for path in self.agent.find_files(arg.strip()):
            print(path)

    def slash_read(self, arg):
        parts = shlex.split(arg)
        if not parts:
            print("Usage: /read <path> [start] [end]")
            return
        start = int(parts[1]) if len(parts) > 1 else 1
        end = int(parts[2]) if len(parts) > 2 else start + 120
        print(self.agent.read_file(parts[0], start, end))

    def slash_ask(self, arg):
        if not arg.strip():
            print("Usage: /ask <question>")
            return
        print(self.agent.ask(arg.strip()))

    def _rank_and_display(self, task, count=None):
        ranked = self.agent.generate_and_rank(task, candidate_count=count)
        print("\n" + self.agent.format_candidate_summary(ranked))
        print("\n--- BEST PATCH ---\n")
        print(ranked["best"]["diff"])
        return ranked

    def slash_edit(self, arg):
        task = arg.strip()
        if not task:
            print("Usage: /edit <task>")
            return
        ranked = self._rank_and_display(task)
        if input("Apply best patch? [y/N] ").strip().lower() == "y":
            print(self.agent.apply_candidate(ranked["best"], task))
        else:
            print("Patch not applied.")

    def slash_auto(self, arg):
        task = arg.strip()
        if not task:
            print("Usage: /auto <task>")
            return
        ranked = self._rank_and_display(task)
        print(self.agent.apply_candidate(ranked["best"], task))

    def slash_candidates(self, arg):
        parts = shlex.split(arg)
        if len(parts) < 2:
            print("Usage: /candidates <n> <task>")
            return
        count = int(parts[0])
        task = " ".join(parts[1:])
        self._rank_and_display(task, count=count)

    def slash_diff(self, arg):
        print(self.agent.show_diff())

    def slash_test(self, arg):
        print(self.agent.run_test(arg.strip() or None))

    def slash_run(self, arg):
        if not arg.strip():
            print("Usage: /run <command>")
            return
        print(self.agent.run_shell(arg.strip()))

    def slash_undo(self, arg):
        print(self.agent.undo_last_patch())

    def slash_memory(self, arg):
        print(self.agent.show_memory())

    def slash_permissions(self, arg):
        print(self.agent.show_permissions())

    def slash_permission(self, arg):
        parts = shlex.split(arg)
        if len(parts) != 2:
            print("Usage: /permission <action> <allow|ask|deny>")
            return
        try:
            print(self.agent.set_permission(parts[0], parts[1]))
        except Exception as exc:
            print(f"Error: {exc}")

    def slash_clear(self, arg):
        self.agent.session_notes.clear()
        print("Session notes cleared.")

    def slash_exit(self, arg):
        return True

    def do_EOF(self, arg):
        print()
        return True
