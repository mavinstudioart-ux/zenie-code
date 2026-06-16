from __future__ import annotations

import re

from .schemas import REQUIREMENT_SCHEMA

VAGUE_PATTERNS = [
    r"^\s*(cek|check|periksa|lihat)\s+(project|proyek|aplikasi|website|web|kode)\b",
    r"^\s*(aplikasi|website|web|project|proyek)\s+(error|bermasalah|rusak|tidak jalan)\b",
    r"^\s*(tidak jalan|nggak jalan|ga jalan|error|bermasalah)\s*$",
    r"^\s*(tolong\s+)?(benahi|perbaiki)\s+(semuanya|project|proyek|aplikasi|website)\s*$",
]


def is_vague_request(text: str):
    normalized = " ".join((text or "").lower().split())
    if len(normalized.split()) <= 3:
        return True
    if any(re.search(pattern, normalized) for pattern in VAGUE_PATTERNS):
        return True

    explicit_edit_terms = [
        "perbaiki fungsi", "ubah file", "implementasikan", "tambahkan",
        "hapus ", "refactor", "buat patch", "fix function", "change ",
    ]
    symptom_terms = [
        "tidak bisa", "tidak jalan", "gagal", "error", "exception",
        "crash", "bermasalah", "lambat", "timeout", "blank",
        "tidak muncul", "tidak berfungsi",
    ]
    has_explicit_edit = any(term in normalized for term in explicit_edit_terms)
    has_symptom = any(term in normalized for term in symptom_terms)
    return has_symptom and not has_explicit_edit


def heuristic_refine(text: str):
    lowered = (text or "").lower()
    task_type = "unknown_diagnosis"
    if any(word in lowered for word in ["error", "gagal", "failed", "exception", "crash"]):
        task_type = "runtime_or_test_failure"
    elif any(word in lowered for word in ["lambat", "slow", "performance"]):
        task_type = "performance_problem"
    elif any(word in lowered for word in ["login", "auth", "masuk"]):
        task_type = "authentication_problem"
    elif any(word in lowered for word in ["build", "compile"]):
        task_type = "build_failure"

    error_match = re.search(
        r"(?:error|exception|gagal|failed)\s*[:\-]\s*(.+)",
        text or "",
        re.IGNORECASE,
    )
    return {
        "reported_symptom": text.strip() if text else "Unknown project problem",
        "task_type": task_type,
        "expected_behavior": None,
        "observed_behavior": text.strip() if text else None,
        "known_error": error_match.group(1).strip() if error_match else None,
        "affected_area": None,
        "user_technical_confidence": "unknown",
        "is_vague": is_vague_request(text),
        "missing_information": [
            "expected_behavior",
            "exact user action that triggers the problem",
        ],
    }


def refine_requirement(llm, text: str, profile: dict):
    fallback = heuristic_refine(text)
    try:
        result = llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Convert a possibly vague software complaint into a structured "
                        "diagnostic contract. Do not invent an error message."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User complaint:\n{text}\n\n"
                        f"Detected project type:\n{profile.get('project_type')}\n"
                        f"Frameworks:\n{profile.get('frameworks')}"
                    ),
                },
            ],
            REQUIREMENT_SCHEMA,
            temperature=0.0,
        )
        result["is_vague"] = bool(result.get("is_vague", fallback["is_vague"]))
        return result
    except Exception:
        return fallback
