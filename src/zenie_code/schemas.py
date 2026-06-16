FILE_SELECTION_SCHEMA = {
    "name": "file_selection",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["files"],
        "additionalProperties": False,
    },
}

PATCH_SCHEMA = {
    "name": "patch_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "diff": {"type": "string"},
        },
        "required": ["diff"],
        "additionalProperties": False,
    },
}

VERIFIER_SCHEMA = {
    "name": "patch_verdict",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high", "unknown"],
            },
            "concerns": {
                "type": "array",
                "items": {"type": "string"},
            },
            "verdict": {
                "type": "string",
                "enum": ["accept", "reject", "needs_tests"],
            },
        },
        "required": ["risk_level", "concerns", "verdict"],
        "additionalProperties": False,
    },
}

REFLECTION_SCHEMA = {
    "name": "reflection",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reflection": {"type": "string"},
        },
        "required": ["reflection"],
        "additionalProperties": False,
    },
}

PLAN_SCHEMA = {
    "name": "task_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "string"},
            "files": {
                "type": "array",
                "items": {"type": "string"},
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
            },
            "test_strategy": {"type": "string"},
        },
        "required": ["hypothesis", "files", "steps", "test_strategy"],
        "additionalProperties": False,
    },
}


REQUIREMENT_SCHEMA = {
    "name": "diagnostic_requirement",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "reported_symptom": {"type": "string"},
            "task_type": {"type": "string"},
            "expected_behavior": {"type": ["string", "null"]},
            "observed_behavior": {"type": ["string", "null"]},
            "known_error": {"type": ["string", "null"]},
            "affected_area": {"type": ["string", "null"]},
            "user_technical_confidence": {
                "type": "string",
                "enum": ["low", "medium", "high", "unknown"]
            },
            "is_vague": {"type": "boolean"},
            "missing_information": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": [
            "reported_symptom", "task_type", "expected_behavior",
            "observed_behavior", "known_error", "affected_area",
            "user_technical_confidence", "is_vague", "missing_information"
        ],
        "additionalProperties": False
    }
}

HYPOTHESES_SCHEMA = {
    "name": "diagnostic_hypotheses",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "confidence": {"type": "number"},
                        "supporting_evidence": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "contradicting_evidence": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "next_probe": {"type": "string"},
                        "category": {"type": "string"},
                        "suspect_files": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": [
                        "claim", "confidence", "supporting_evidence",
                        "contradicting_evidence", "next_probe",
                        "category", "suspect_files"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["hypotheses"],
        "additionalProperties": False
    }
}
