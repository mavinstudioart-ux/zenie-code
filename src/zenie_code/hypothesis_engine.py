from __future__ import annotations

import json
import re

from .schemas import HYPOTHESES_SCHEMA


def _rule_hypotheses(symptom: str, reproduction: dict, baseline: dict, suspects: list[dict]):
    text = " ".join([
        symptom or "",
        reproduction.get("error_signature", ""),
        "\n".join(
            attempt.get("output", "")
            for attempt in reproduction.get("attempts", [])
        ),
        json.dumps(baseline.get("primary_failure") or {}),
    ]).lower()

    top_file = suspects[0]["path"] if suspects else None
    rules = []

    def add(claim, confidence, evidence, probe, category):
        rules.append({
            "claim": claim,
            "confidence": confidence,
            "supporting_evidence": evidence,
            "contradicting_evidence": [],
            "next_probe": probe,
            "category": category,
            "suspect_files": [top_file] if top_file else [],
        })

    if re.search(r"module not found|cannot find module|no module named|importerror", text):
        add(
            "A dependency, import path, or module alias is missing or inconsistent.",
            0.82,
            ["Failure output reports a missing module or import."],
            "Verify dependency manifests and resolve the exact import from the first stack location.",
            "dependency_or_import",
        )
    if re.search(r"database_url|api_key|secret|environment variable|not defined|missing env", text):
        add(
            "Required runtime configuration is absent or loaded too late.",
            0.86,
            ["Failure evidence refers to a required environment/configuration value."],
            "Compare .env examples with runtime environment and trace configuration loading.",
            "configuration",
        )
    if re.search(r"connection refused|econnrefused|could not connect|connectionerror", text):
        add(
            "A required external service is unavailable or configured at the wrong address.",
            0.78,
            ["The reproduced failure is a refused connection."],
            "Check service URL, port, container status, and health endpoint.",
            "external_service",
        )
    if re.search(r"syntaxerror|parse error|unexpected token|compile error", text):
        add(
            "The repository contains a syntax or parse error near the first reported location.",
            0.90,
            ["Static or build output reports a syntax/parse failure."],
            "Read the reported span and run the narrowest parser/compiler check.",
            "syntax",
        )
    if re.search(r"assert|expected .* received|assertionerror|test.*failed", text):
        add(
            "Application behavior conflicts with an executable test expectation.",
            0.70,
            ["A test or assertion failed reproducibly."],
            "Read the failing test and trace its first application call.",
            "logic",
        )
    if re.search(r"timeout|timed out|deadline exceeded", text):
        add(
            "A timeout value, blocking operation, or unavailable dependency prevents completion.",
            0.66,
            ["The failure evidence reports a timeout."],
            "Compare configured timeout units and isolate the slow external call.",
            "timeout",
        )
    if re.search(r"permission denied|access is denied|eacces", text):
        add(
            "The process lacks permission for a required file, directory, port, or command.",
            0.82,
            ["The failure evidence reports a permission error."],
            "Inspect the exact resource path and current process permissions.",
            "permission",
        )

    if not rules and baseline.get("primary_failure"):
        add(
            "The first failing baseline command exposes the most likely defect area.",
            0.55,
            ["At least one baseline health check failed."],
            "Inspect the first error location and rerun the narrowest failing command.",
            "unknown_failure",
        )
    if not rules:
        add(
            "No defect has been reproduced; the problem may depend on a user action or runtime environment not represented by current checks.",
            0.30,
            ["Detected commands completed or no safe reproduction command was available."],
            "Ask for the exact action, expected result, observed result, and visible error.",
            "insufficient_evidence",
        )

    return rules


def generate_hypotheses(
    llm,
    symptom: str,
    profile: dict,
    baseline: dict,
    reproduction: dict,
    suspects: list[dict],
):
    rules = _rule_hypotheses(symptom, reproduction, baseline, suspects)

    try:
        result = llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Generate falsifiable software-debugging hypotheses. "
                        "Confidence must reflect supplied evidence, not plausibility alone."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Symptom:\n{symptom}\n\n"
                        f"Project profile:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
                        f"Baseline:\n{json.dumps(baseline, ensure_ascii=False)}\n\n"
                        f"Reproduction:\n{json.dumps(reproduction, ensure_ascii=False)}\n\n"
                        f"Suspect locations:\n{json.dumps(suspects, ensure_ascii=False)}"
                    ),
                },
            ],
            HYPOTHESES_SCHEMA,
            temperature=0.1,
        )
        model_hypotheses = result.get("hypotheses", [])
    except Exception:
        model_hypotheses = []

    merged = []
    seen = set()
    for item in rules + model_hypotheses:
        claim = str(item.get("claim", "")).strip()
        key = re.sub(r"\W+", " ", claim.lower()).strip()
        if not claim or key in seen:
            continue
        seen.add(key)
        normalized = {
            "id": f"H{len(merged) + 1}",
            "claim": claim,
            "confidence": round(
                max(0.0, min(float(item.get("confidence", 0.3)), 1.0)),
                4,
            ),
            "supporting_evidence": item.get("supporting_evidence", []),
            "contradicting_evidence": item.get("contradicting_evidence", []),
            "next_probe": item.get("next_probe", ""),
            "category": item.get("category", "unknown"),
            "suspect_files": item.get("suspect_files", []),
        }
        merged.append(normalized)

    merged.sort(key=lambda item: item["confidence"], reverse=True)
    return merged[:8]
