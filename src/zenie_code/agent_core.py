import json
from pathlib import Path

from .config_manager import load_config as load_zenie_config
from .diagnostic_engine import DiagnosticEngine
from .llm_client import LLMClient
from .memory import AgentMemory
from .patcher import (
    apply_patch,
    changed_files,
    extract_unified_diff,
    git_diff,
    git_status,
    has_diff,
    rollback_patch,
    run_command,
)
from .permissions import PermissionManager
from .prompts import (
    LOCALIZATION_PROMPT,
    PATCH_PROMPT,
    PLAN_PROMPT,
    REFLECTION_PROMPT,
    SYSTEM_PROMPT,
    VERIFIER_PROMPT,
)
from .repo_graph import build_repo_graph, graph_to_text, save_graph
from .repo_tools import (
    build_context,
    list_repo_files,
    read_text_safe,
    search_repo,
)
from .requirement_refiner import is_vague_request
from .sandbox import SandboxManager
from .schemas import (
    FILE_SELECTION_SCHEMA,
    PATCH_SCHEMA,
    PLAN_SCHEMA,
    REFLECTION_SCHEMA,
    VERIFIER_SCHEMA,
)
from .tool_registry import retrieve_tools
from .verifier import (
    run_static_checks,
    score_candidate,
    verification_summary,
)


class CodingAgent:
    def __init__(
        self,
        repo_root: Path,
        agent_dir: Path,
        test_command=None,
        auto_approve=False,
        approval_callback=None,
    ):
        self.repo_root = repo_root.resolve()
        self.agent_dir = agent_dir.resolve()
        self.config, self.config_metadata = load_zenie_config(self.repo_root)
        if test_command is not None:
            self.config["test_command"] = test_command

        self.permission_manager = PermissionManager(
            self.config.get("permissions", {}),
            auto_approve=auto_approve,
            approval_callback=approval_callback,
        )
        self.memory = AgentMemory(self.repo_root)
        self.session_notes = []
        self.last_applied_diff = None
        self.last_applied_task = None

        self.llm = LLMClient(
            base_url=self.config["base_url"],
            api_key=self.config.get("api_key", "none"),
            model=self.config["model"],
            temperature=self.config.get("temperature", 0.2),
            max_tokens=self.config.get("max_tokens", 4096),
            timeout=self.config.get("llm_timeout", 600),
            structured_output=self.config.get("structured_output", True),
        )

        self.repo_files = self.refresh_files()
        self.repo_graph = self.refresh_graph()
        self.diagnostic_engine = DiagnosticEngine(
            self.repo_root,
            self.config,
            self.llm,
            self.permission_manager,
            self.repo_files,
            self.repo_graph,
        )

    def refresh_files(self):
        return list_repo_files(
            self.repo_root,
            include_ext=self.config["include_ext"],
            exclude_dirs=self.config["exclude_dirs"],
        )

    def refresh_graph(self):
        graph = build_repo_graph(self.repo_root, self.repo_files)
        if self.config.get("write_repo_graph", True):
            save_graph(self.repo_root, graph)
        return graph

    def status(self):
        parser_counts = {}
        for info in self.repo_graph.values():
            parser = info.get("parser", "unknown")
            parser_counts[parser] = parser_counts.get(parser, 0) + 1
        return "\n".join([
            f"Repo: {self.repo_root}",
            f"Model: {self.config.get('model')}",
            f"Base URL: {self.config.get('base_url')}",
            f"Files indexed: {len(self.repo_files)}",
            f"Graph nodes: {len(self.repo_graph)}",
            f"Graph parsers: {json.dumps(parser_counts)}",
            f"Candidates: {self.config.get('candidate_count', 2)}",
            f"Test command: {self.config.get('test_command', '')}",
            f"Rollback on failure: {self.config.get('rollback_on_failure', True)}",
            f"Config: {', '.join(self.config_metadata.get('sources', []))}",
            f"Permissions: {json.dumps(self.permission_manager.describe())}",
            f"Git status:\n{git_status(self.repo_root).rstrip() or '(clean)'}",
        ])

    def set_approval_callback(self, callback):
        self.permission_manager.approval_callback = callback

    def find_files(self, query, max_files=20):
        if not query:
            return self.repo_files[:max_files]
        model_files = self._select_files_with_model(query, max_files)
        fallback_files = search_repo(
            self.repo_root,
            query,
            self.repo_files,
            max_hits=max_files,
        )
        merged = []
        for path in model_files + fallback_files:
            if path not in merged:
                merged.append(path)
            if len(merged) >= max_files:
                break
        return merged

    def _select_files_with_model(self, task, max_files):
        prompt = LOCALIZATION_PROMPT.format(
            task=task,
            graph=graph_to_text(self.repo_graph, limit=450),
            files="\n".join(self.repo_files[:2500]),
            max_files=max_files,
        )
        try:
            result = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": "Select only valid paths from the supplied repository file list.",
                    },
                    {"role": "user", "content": prompt},
                ],
                FILE_SELECTION_SCHEMA,
                temperature=0.0,
            )
            selected = result.get("files", [])
        except Exception:
            return []

        valid = set(self.repo_files)
        output = []
        for path in selected:
            path = str(path).strip()
            if path in valid and path not in output:
                output.append(path)
            if len(output) >= max_files:
                break
        return output

    def plan_task(self, task):
        selected = self.find_files(
            task,
            max_files=self.config.get("max_files", 12),
        )
        prompt = PLAN_PROMPT.format(
            task=task,
            files="\n".join(selected),
            graph=graph_to_text(
                {path: self.repo_graph[path] for path in selected if path in self.repo_graph},
                limit=100,
            ),
        )
        try:
            return self.llm.chat_json(
                [
                    {"role": "system", "content": "Create a concise coding execution plan."},
                    {"role": "user", "content": prompt},
                ],
                PLAN_SCHEMA,
                temperature=0.1,
            )
        except Exception as exc:
            return {
                "hypothesis": "Model planning failed.",
                "files": selected,
                "steps": ["Inspect selected files", "Create minimal patch", "Run tests"],
                "test_strategy": str(exc),
            }

    def read_file(self, rel_path, start=1, end=160):
        path = self.repo_root / rel_path
        if not path.exists() or not path.is_file():
            return f"File not found: {rel_path}"
        lines = read_text_safe(path, max_chars=500000).splitlines()
        start = max(1, start)
        end = min(len(lines), end)
        return "\n".join(
            f"{index:>5} | {lines[index - 1]}"
            for index in range(start, end + 1)
        )

    def ask(self, question):
        files = self.find_files(question, max_files=8)
        context = build_context(
            self.repo_root,
            files,
            self.config.get("max_context_chars", 60000),
        )
        return self.llm.chat([
            {
                "role": "system",
                "content": "Answer as a concise repository-aware coding assistant. Do not edit files.",
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Repository graph:\n{graph_to_text(self.repo_graph, limit=250)}\n\n"
                    f"Relevant context:\n{context}"
                ),
            },
        ])

    def _generation_context(self, task):
        self.repo_files = self.refresh_files()
        self.repo_graph = self.refresh_graph()
        selected = self.find_files(
            task,
            max_files=self.config.get("max_files", 12),
        )
        context = build_context(
            self.repo_root,
            selected,
            self.config.get("max_context_chars", 60000),
        )
        return selected, context

    def _generate_candidate(
        self,
        task,
        selected,
        context,
        candidate_index,
        failure_evidence="",
    ):
        temperature = min(
            0.8,
            self.config.get("temperature", 0.2)
            + candidate_index * self.config.get("candidate_temperature_step", 0.08),
        )
        prompt = PATCH_PROMPT.format(
            task=task,
            candidate_index=candidate_index + 1,
            tools=json.dumps(retrieve_tools(task), ensure_ascii=False, indent=2),
            memory=json.dumps(self.memory.recent(limit=10), ensure_ascii=False, indent=2),
            graph=graph_to_text(self.repo_graph, limit=400),
            context=context,
            failure_evidence=failure_evidence or "(none)",
        )

        try:
            result = self.llm.chat_json(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                PATCH_SCHEMA,
                temperature=temperature,
                seed=self.config.get("seed", 42) + candidate_index,
            )
            diff = str(result.get("diff", ""))
        except Exception:
            raw = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT + "\nReturn only a unified diff.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
            diff = extract_unified_diff(raw)

        if not has_diff(diff):
            raise RuntimeError("Model did not return a valid unified diff.")

        return {
            "candidate_index": candidate_index,
            "diff": diff,
            "selected_files": selected,
            "generation_temperature": temperature,
        }

    def _model_verify(self, task, diff, verification):
        if not self.config.get("enable_model_verifier", True):
            return {
                "risk_level": "unknown",
                "concerns": [],
                "verdict": "needs_tests",
            }
        try:
            return self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": "You are an independent strict patch verifier.",
                    },
                    {
                        "role": "user",
                        "content": VERIFIER_PROMPT.format(
                            task=task,
                            diff=diff,
                            verification=json.dumps(
                                verification,
                                ensure_ascii=False,
                                indent=2,
                            ),
                        ),
                    },
                ],
                VERIFIER_SCHEMA,
                temperature=0.0,
            )
        except Exception as exc:
            return {
                "risk_level": "unknown",
                "concerns": [f"Verifier unavailable: {exc}"],
                "verdict": "needs_tests",
            }

    def _evaluate_candidate(self, task, candidate):
        sandbox = SandboxManager(
            self.repo_root,
            exclude_dirs=self.config.get("sandbox_exclude_dirs", self.config["exclude_dirs"]),
            timeout=self.config.get("test_timeout", 600),
        )
        evaluation = sandbox.evaluate(
            candidate["diff"],
            test_command=self.config.get("test_command", ""),
            static_checks=self.config.get("enable_static_checks", True),
        )
        verification = {
            "apply_status": evaluation["apply_status"],
            "static_status": evaluation["static_status"],
            "static_result": evaluation["static_result"],
            "test_status": evaluation["test_status"],
            "test_output": evaluation["test_output"],
            "changed_files": evaluation["changed_files"],
        }
        verdict = self._model_verify(task, candidate["diff"], verification)
        score = score_candidate(
            candidate["diff"],
            apply_status=evaluation["apply_status"],
            static_status=evaluation["static_status"],
            test_status=evaluation["test_status"],
            model_verdict=verdict.get("verdict", "needs_tests"),
        )
        candidate = dict(candidate)
        candidate.update({
            "evaluation": evaluation,
            "verdict": verdict,
            "score": score,
        })
        return candidate

    def generate_and_rank(self, task, candidate_count=None):
        selected, context = self._generation_context(task)
        count = candidate_count or self.config.get("candidate_count", 2)
        count = max(1, min(int(count), self.config.get("max_candidate_count", 5)))

        candidates = []
        errors = []
        for index in range(count):
            try:
                generated = self._generate_candidate(
                    task,
                    selected,
                    context,
                    index,
                )
                candidates.append(self._evaluate_candidate(task, generated))
            except Exception as exc:
                errors.append(f"Candidate {index + 1}: {exc}")

        # One repair round using concrete verifier output.
        repair_attempts = self.config.get("repair_attempts", 1)
        if candidates and repair_attempts > 0:
            current_best = max(candidates, key=lambda item: item["score"])
            failed = (
                current_best["evaluation"]["apply_status"] != "passed"
                or current_best["evaluation"]["static_status"] == "failed"
                or current_best["evaluation"]["test_status"] == "failed"
                or current_best["verdict"].get("verdict") == "reject"
            )
            if failed:
                evidence = json.dumps(
                    {
                        "previous_diff": current_best["diff"],
                        "evaluation": current_best["evaluation"],
                        "verdict": current_best["verdict"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                for attempt in range(repair_attempts):
                    try:
                        index = count + attempt
                        repaired = self._generate_candidate(
                            task,
                            selected,
                            context,
                            index,
                            failure_evidence=evidence,
                        )
                        repaired["repair_candidate"] = True
                        candidates.append(self._evaluate_candidate(task, repaired))
                    except Exception as exc:
                        errors.append(f"Repair candidate {attempt + 1}: {exc}")

        if not candidates:
            raise RuntimeError("No valid candidates generated.\n" + "\n".join(errors))

        candidates.sort(key=lambda item: item["score"], reverse=True)
        result = {
            "task": task,
            "best": candidates[0],
            "candidates": candidates,
            "errors": errors,
            "selected_files": selected,
        }
        self.memory.append({
            "status": "candidate_ranking",
            "task": task,
            "selected_files": selected,
            "scores": [
                {
                    "candidate_index": item["candidate_index"],
                    "score": item["score"],
                    "test_status": item["evaluation"]["test_status"],
                    "static_status": item["evaluation"]["static_status"],
                    "verdict": item["verdict"].get("verdict"),
                }
                for item in candidates
            ],
        })
        return result

    def generate_patch(self, task, candidate_count=None):
        return self.generate_and_rank(task, candidate_count)["best"]

    def format_candidate_summary(self, ranked):
        lines = [
            f"Selected files: {', '.join(ranked.get('selected_files', [])) or '(none)'}",
            "",
            "Candidates:",
        ]
        for position, item in enumerate(ranked["candidates"], start=1):
            evaluation = item["evaluation"]
            lines.append(
                f"  {position}. source=#{item['candidate_index'] + 1} "
                f"score={item['score']} "
                f"apply={evaluation['apply_status']} "
                f"static={evaluation['static_status']} "
                f"test={evaluation['test_status']} "
                f"verdict={item['verdict'].get('verdict')}"
            )
        if ranked.get("errors"):
            lines.append("")
            lines.append("Generation errors:")
            lines.extend(f"  - {error}" for error in ranked["errors"])
        return "\n".join(lines)

    def apply_candidate(self, candidate, task):
        diff = candidate["diff"]
        allowed, reason = self.permission_manager.authorize(
            "apply_patch",
            f"Apply patch changing: {', '.join(changed_files(diff))}",
        )
        if not allowed:
            return f"Patch not applied: {reason}"

        applied, message = apply_patch(self.repo_root, diff)
        if not applied:
            self._reflect(task, diff, {"apply_error": message})
            return message

        self.last_applied_diff = diff
        self.last_applied_task = task

        output = [
            message,
            "\n--- STATIC CHECKS ---",
        ]
        static_result = (
            run_static_checks(self.repo_root)
            if self.config.get("enable_static_checks", True)
            else {"status": "skipped", "checks": []}
        )
        output.append(json.dumps(static_result, ensure_ascii=False, indent=2))

        test_status = "skipped"
        test_output = ""
        test_command = self.config.get("test_command", "")
        if test_command:
            allowed, reason = self.permission_manager.authorize(
                "run_tests",
                test_command,
            )
            if allowed:
                code, out, err = run_command(
                    self.repo_root,
                    test_command,
                    timeout=self.config.get("test_timeout", 600),
                )
                test_status = "passed" if code == 0 else "failed"
                test_output = (out + "\n" + err).strip()
                output.extend([
                    "\n--- TEST ---",
                    test_output,
                    f"\nTest status: {test_status}",
                ])
            else:
                output.append(f"\nTests skipped: {reason}")

        verification = verification_summary(
            static_result,
            test_status,
            test_output,
        )
        verdict = self._model_verify(task, diff, verification)
        score = score_candidate(
            diff,
            apply_status="passed",
            static_status=static_result.get("status", "skipped"),
            test_status=test_status,
            model_verdict=verdict.get("verdict", "needs_tests"),
        )
        output.extend([
            "\n--- VERIFIER ---",
            json.dumps(verdict, ensure_ascii=False, indent=2),
            f"\nReal-repository score: {score}",
        ])

        failed = (
            static_result.get("status") == "failed"
            or test_status == "failed"
            or verdict.get("verdict") == "reject"
        )
        if failed:
            self._reflect(task, diff, {
                "static": static_result,
                "test_status": test_status,
                "test_output": test_output,
                "verdict": verdict,
            })
            if self.config.get("rollback_on_failure", True):
                rollback_allowed, rollback_reason = self.permission_manager.authorize(
                    "rollback_patch",
                    "Verification failed; reverse the last agent patch.",
                )
                if rollback_allowed:
                    rolled_back, rollback_output = rollback_patch(self.repo_root, diff)
                    output.extend(["\n--- ROLLBACK ---", rollback_output])
                    if rolled_back:
                        self.last_applied_diff = None
                        self.last_applied_task = None
                else:
                    output.append(f"\nRollback skipped: {rollback_reason}")

        output.extend(["\n--- CURRENT GIT DIFF ---", git_diff(self.repo_root)])
        self.memory.append({
            "status": "applied_candidate",
            "task": task,
            "score": score,
            "static_status": static_result.get("status", "skipped"),
            "test_status": test_status,
            "verdict": verdict.get("verdict"),
            "changed_files": changed_files(diff),
        })
        return "\n".join(output)

    def apply_and_test(self, diff, task=None):
        candidate = {
            "diff": diff,
            "evaluation": {},
            "verdict": {},
            "score": 0,
        }
        return self.apply_candidate(candidate, task or "unknown task")

    def undo_last_patch(self):
        if not self.last_applied_diff:
            return "No applied agent patch is available to undo."
        allowed, reason = self.permission_manager.authorize(
            "rollback_patch",
            "Undo the last applied agent patch.",
        )
        if not allowed:
            return f"Undo denied: {reason}"
        ok, output = rollback_patch(self.repo_root, self.last_applied_diff)
        if ok:
            self.last_applied_diff = None
            self.last_applied_task = None
        return output

    def _reflect(self, task, diff, verification):
        if not self.config.get("enable_reflection", True):
            return ""
        try:
            result = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": "Write a concrete reusable lesson from failure evidence.",
                    },
                    {
                        "role": "user",
                        "content": REFLECTION_PROMPT.format(
                            task=task,
                            diff=diff,
                            verification=json.dumps(
                                verification,
                                ensure_ascii=False,
                                indent=2,
                            ),
                        ),
                    },
                ],
                REFLECTION_SCHEMA,
                temperature=0.1,
            )
            reflection = result.get("reflection", "")
        except Exception as exc:
            reflection = f"Reflection unavailable: {exc}"

        self.memory.append({
            "status": "reflection",
            "task": task,
            "reflection": reflection[:3000],
        })
        self.session_notes.append("Reflection: " + reflection[:3000])
        return reflection


    def inspect_project(self):
        self.repo_files = self.refresh_files()
        self.repo_graph = self.refresh_graph()
        self.diagnostic_engine.update_repository(self.repo_files, self.repo_graph)
        profile = self.diagnostic_engine.inspect()
        return self.diagnostic_engine.format_profile(profile)

    def diagnose_project(self, symptom):
        self.repo_files = self.refresh_files()
        self.repo_graph = self.refresh_graph()
        self.diagnostic_engine.update_repository(self.repo_files, self.repo_graph)
        report = self.diagnostic_engine.diagnose(symptom)
        self.memory.append({
            "status": "diagnosis",
            "symptom": symptom,
            "diagnostic_state": report["state"],
            "confidence": report["confidence"],
            "ready_to_patch": report["ready_to_patch"],
            "session_id": report["session_id"],
        })
        return self.diagnostic_engine.format_report(report)

    def reproduce_issue(self, command=None):
        result = self.diagnostic_engine.reproduce_current(command)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def show_hypotheses(self):
        return self.diagnostic_engine.format_hypotheses()

    def show_evidence(self):
        return self.diagnostic_engine.format_evidence()

    def explain_diagnosis(self):
        return self.diagnostic_engine.explain()

    def diagnosis_questions(self):
        report = self.diagnostic_engine.current_report
        if not report:
            return "No diagnosis exists."
        questions = report.get("questions", [])
        return "\n".join(f"- {item}" for item in questions) or "No additional questions."

    def generate_fix_from_diagnosis(self, extra_instruction="", candidate_count=None):
        task = self.diagnostic_engine.build_fix_task(extra_instruction)
        return task, self.generate_and_rank(task, candidate_count=candidate_count)

    def route_direct_input(self, text):
        if is_vague_request(text):
            return "diagnose"
        return "edit"

    def show_diff(self):
        return git_diff(self.repo_root)

    def show_memory(self):
        return json.dumps(
            self.memory.recent(limit=20),
            ensure_ascii=False,
            indent=2,
        )

    def show_permissions(self):
        return json.dumps(
            self.permission_manager.describe(),
            ensure_ascii=False,
            indent=2,
        )

    def set_permission(self, action, mode):
        self.permission_manager.set_mode(action, mode)
        return f"{action} = {mode}"

    def run_test(self, command=None):
        command = command or self.config.get("test_command", "")
        if not command:
            return "No test command configured."
        allowed, reason = self.permission_manager.authorize("run_tests", command)
        if not allowed:
            return f"Test denied: {reason}"
        code, out, err = run_command(
            self.repo_root,
            command,
            timeout=self.config.get("test_timeout", 600),
        )
        status = "passed" if code == 0 else "failed"
        text = (out + "\n" + err).strip()
        self.session_notes.append(f"Test `{command}` {status}:\n{text[-4000:]}")
        return text + f"\n\nTest status: {status}"

    def run_shell(self, command):
        allowed, reason = self.permission_manager.authorize("run_shell", command)
        if not allowed:
            return f"Command denied: {reason}"
        code, out, err = run_command(
            self.repo_root,
            command,
            timeout=self.config.get("shell_timeout", 600),
        )
        text = (out + "\n" + err).strip()
        self.session_notes.append(
            f"Shell `{command}` returned {code}:\n{text[-4000:]}"
        )
        return text + f"\n\nExit code: {code}"
