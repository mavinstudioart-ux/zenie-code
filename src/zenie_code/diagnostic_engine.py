from __future__ import annotations

import json
from pathlib import Path

from .baseline_checks import run_baseline
from .context_budget import ContextBudgetManager
from .diagnostic_fsm import DiagnosticFSM
from .evidence_store import EvidenceStore
from .fault_localizer import localize
from .hypothesis_engine import generate_hypotheses
from .project_profiler import format_profile, profile_repository
from .repo_graph import graph_to_text
from .repo_tools import build_context, search_repo
from .reproduction_engine import reproduce
from .requirement_refiner import refine_requirement


class DiagnosticEngine:
    def __init__(
        self,
        repo_root: Path,
        config: dict,
        llm,
        permission_manager,
        repo_files: list[str],
        repo_graph: dict,
    ):
        self.repo_root = repo_root
        self.config = config
        self.llm = llm
        self.permission_manager = permission_manager
        self.repo_files = repo_files
        self.repo_graph = repo_graph
        self.evidence_store = EvidenceStore(repo_root)
        self.current_report = None
        self.fsm = None

    def update_repository(self, repo_files, repo_graph):
        self.repo_files = repo_files
        self.repo_graph = repo_graph

    def inspect(self):
        profile = profile_repository(self.repo_root, self.repo_files)
        return profile

    def _transition(self, state, note=""):
        self.fsm.transition(state, note)

    def diagnose(self, symptom: str):
        profile = self.inspect()
        self.evidence_store.start(symptom, profile)
        self.fsm = DiagnosticFSM(on_transition=self.evidence_store.add_state)

        self._transition("DISCOVERING", "Profiling repository and refining complaint.")
        requirement = refine_requirement(self.llm, symptom, profile)
        self.evidence_store.add("requirement", requirement, "user+refiner", 0.85)

        self._transition("BASELINING", "Running safe baseline health checks.")
        baseline = run_baseline(
            self.repo_root,
            profile,
            self.config,
            self.permission_manager,
        )
        self.evidence_store.add("baseline", baseline, "baseline_checks", 1.0)

        self._transition("REPRODUCING", "Trying the narrowest detected failing command.")
        reproduction = reproduce(
            self.repo_root,
            profile,
            self.config,
            self.permission_manager,
            baseline=baseline,
        )
        self.evidence_store.add(
            "reproduction",
            reproduction,
            "reproduction_engine",
            1.0 if reproduction.get("reproduced") else 0.5,
        )

        self._transition("LOCALIZING", "Combining stack locations, keyword matches, graph, and Git history.")
        query = " ".join([
            symptom,
            reproduction.get("error_signature", ""),
            (baseline.get("primary_failure") or {}).get("output", "")[:3000],
        ])
        keyword_files = search_repo(
            self.repo_root,
            query,
            self.repo_files,
            max_hits=25,
        )
        suspects = localize(
            self.repo_root,
            symptom,
            self.repo_files,
            self.repo_graph,
            reproduction,
            baseline,
            keyword_files,
            limit=self.config.get("diagnostic_max_suspects", 15),
        )
        self.evidence_store.add("localization", suspects, "fault_localizer", 0.8)

        self._transition("HYPOTHESIZING", "Ranking falsifiable causes.")
        hypotheses = generate_hypotheses(
            self.llm,
            symptom,
            profile,
            baseline,
            reproduction,
            suspects,
        )
        self.evidence_store.add("hypotheses", hypotheses, "hypothesis_engine", 0.8)

        top_confidence = hypotheses[0]["confidence"] if hypotheses else 0.0
        reproduced = bool(reproduction.get("reproduced"))
        ready_threshold = float(self.config.get("diagnostic_patch_confidence", 0.70))
        ready = (
            top_confidence >= ready_threshold
            and (reproduced or baseline.get("failure_count", 0) > 0)
            and bool(suspects)
        )

        questions = self._build_questions(requirement, reproduction, hypotheses)
        if ready:
            self._transition(
                "READY_TO_PATCH",
                f"Top hypothesis confidence {top_confidence:.2f} with executable failure evidence.",
            )
        else:
            self._transition(
                "NEEDS_USER_INPUT",
                f"Confidence {top_confidence:.2f} is below the patch gate or reproduction is missing.",
            )

        suspect_files = [item["path"] for item in suspects[:10]]
        source_context = build_context(
            self.repo_root,
            suspect_files,
            self.config.get("diagnostic_source_context_chars", 40000),
        )
        graph_subset = {
            path: self.repo_graph[path]
            for path in suspect_files
            if path in self.repo_graph
        }
        context_bundle = ContextBudgetManager(
            self.config.get("diagnostic_context_budget_chars", 60000)
        ).build(
            requirement,
            profile,
            baseline,
            reproduction,
            suspects,
            hypotheses,
            source_context,
            graph_to_text(graph_subset, limit=100),
        )

        report = {
            "session_id": self.evidence_store.session_id,
            "state": self.fsm.state,
            "symptom": symptom,
            "requirement": requirement,
            "profile": profile,
            "baseline": baseline,
            "reproduction": reproduction,
            "suspects": suspects,
            "hypotheses": hypotheses,
            "confidence": top_confidence,
            "ready_to_patch": ready,
            "questions": questions,
            "context_bundle": context_bundle,
            "state_history": self.fsm.history,
        }
        self.current_report = report
        self.evidence_store.set_field("diagnostic_report", report)
        return report

    def reproduce_current(self, explicit_command=None):
        if self.current_report:
            profile = self.current_report["profile"]
            baseline = self.current_report["baseline"]
        else:
            profile = self.inspect()
            baseline = None

        result = reproduce(
            self.repo_root,
            profile,
            self.config,
            self.permission_manager,
            baseline=baseline,
            explicit_command=explicit_command,
        )
        if self.evidence_store.report is not None:
            self.evidence_store.add(
                "manual_reproduction",
                result,
                "reproduction_engine",
                1.0 if result.get("reproduced") else 0.5,
            )
        return result

    def build_fix_task(self, extra_instruction=""):
        report = self.current_report
        if not report:
            raise RuntimeError("No diagnosis exists. Run /diagnose first.")
        if not report["ready_to_patch"]:
            raise RuntimeError(
                "Diagnosis has not passed the patch confidence gate. "
                "Provide the requested information or run a more specific reproduction command."
            )

        top = report["hypotheses"][0]
        suspects = ", ".join(item["path"] for item in report["suspects"][:6])
        reproduction = report["reproduction"]
        task = (
            f"Fix the diagnosed issue: {top['claim']}\n"
            f"Original symptom: {report['symptom']}\n"
            f"Reproduction command: {reproduction.get('command')}\n"
            f"Error signature: {reproduction.get('error_signature')}\n"
            f"Primary suspect files: {suspects}\n"
            f"Required verification: rerun the reproduction command and existing tests.\n"
            "Make the smallest safe patch supported by the evidence."
        )
        if extra_instruction.strip():
            task += "\nAdditional user instruction: " + extra_instruction.strip()
        return task

    def explain(self):
        report = self.current_report
        if not report:
            return "No diagnosis exists. Run /diagnose first."

        try:
            return self.llm.chat([
                {
                    "role": "system",
                    "content": (
                        "Explain a software diagnosis to a nontechnical user. "
                        "Separate confirmed evidence from hypotheses. Do not claim a fix was applied."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({
                        "symptom": report["symptom"],
                        "project_type": report["profile"]["project_type"],
                        "baseline_status": report["baseline"]["status"],
                        "reproduction": report["reproduction"],
                        "top_hypotheses": report["hypotheses"][:3],
                        "suspects": report["suspects"][:5],
                        "ready_to_patch": report["ready_to_patch"],
                    }, ensure_ascii=False, indent=2),
                },
            ])
        except Exception:
            top = report["hypotheses"][0] if report["hypotheses"] else None
            if not top:
                return "Masalah belum berhasil diidentifikasi."
            return (
                f"Masalah paling mungkin: {top['claim']} "
                f"(confidence {top['confidence']:.0%}). "
                f"Status reproduksi: {report['reproduction']['status']}."
            )

    def _build_questions(self, requirement, reproduction, hypotheses):
        questions = []
        if not requirement.get("expected_behavior"):
            questions.append("Apa hasil yang seharusnya terjadi?")
        if not reproduction.get("reproduced"):
            questions.append("Langkah atau tombol apa yang dilakukan tepat sebelum masalah muncul?")
        if not requirement.get("known_error") and not reproduction.get("error_signature"):
            questions.append("Apakah ada pesan error yang terlihat di layar atau terminal?")
        if hypotheses and hypotheses[0]["confidence"] < 0.55:
            questions.append("Apakah masalah terjadi di semua perangkat/akun atau hanya kondisi tertentu?")
        return questions[:4]

    def format_report(self, report=None):
        report = report or self.current_report
        if not report:
            return "No diagnosis exists."

        lines = [
            f"Diagnostic session: {report['session_id']}",
            f"State: {report['state']}",
            f"Project: {report['profile']['project_type']}",
            f"Baseline: {report['baseline']['status']}",
            f"Reproduction: {report['reproduction']['status']}",
            f"Confidence: {report['confidence']:.0%}",
            f"Ready to patch: {'yes' if report['ready_to_patch'] else 'no'}",
            "",
            "Top suspects:",
        ]
        if report["suspects"]:
            for item in report["suspects"][:6]:
                lines.append(
                    f"  - {item['path']} score={item['score']:.2f}: "
                    + "; ".join(item["evidence"][:3])
                )
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append("Hypotheses:")
        for item in report["hypotheses"][:5]:
            lines.append(
                f"  {item['id']}. {item['claim']} "
                f"[{item['confidence']:.0%}]"
            )
            if item.get("next_probe"):
                lines.append(f"     Next probe: {item['next_probe']}")

        if report["questions"]:
            lines.append("")
            lines.append("Information still useful:")
            lines.extend(f"  - {question}" for question in report["questions"])

        primary = report["baseline"].get("primary_failure")
        if primary:
            lines.extend([
                "",
                "Primary baseline failure:",
                f"  Command: {primary.get('command')}",
                f"  Output: {primary.get('output', '')[-1500:]}",
            ])
        return "\n".join(lines)

    def format_profile(self, profile=None):
        return format_profile(profile or self.inspect())

    def format_hypotheses(self):
        if not self.current_report:
            return "No diagnosis exists."
        return json.dumps(
            self.current_report["hypotheses"],
            ensure_ascii=False,
            indent=2,
        )

    def format_evidence(self):
        return self.evidence_store.render()
