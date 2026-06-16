import argparse
import json
import time
from pathlib import Path

from .agent_core import CodingAgent


def localization_score(selected, expected):
    if not expected:
        return None
    selected = set(selected)
    expected = set(expected)
    return round(len(selected & expected) / len(expected), 4)


def run_suite(suite_path, agent_dir, output_path):
    suite = json.loads(Path(suite_path).read_text(encoding="utf-8"))
    results = []

    for item in suite["tasks"]:
        started = time.time()
        repo = Path(item["repo"]).resolve()
        agent = CodingAgent(
            repo_root=repo,
            agent_dir=agent_dir,
            test_command=item.get("test_command"),
            auto_approve=False,
        )
        try:
            if item.get("mode") == "diagnosis":
                agent.diagnose_project(item["task"])
                report = agent.diagnostic_engine.current_report
                result = {
                    "id": item["id"],
                    "status": "completed",
                    "mode": "diagnosis",
                    "diagnostic_state": report["state"],
                    "confidence": report["confidence"],
                    "ready_to_patch": report["ready_to_patch"],
                    "reproduced": report["reproduction"]["reproduced"],
                    "suspect_files": [x["path"] for x in report["suspects"]],
                    "duration_seconds": round(time.time() - started, 3),
                }
                results.append(result)
                print(json.dumps(result, ensure_ascii=False))
                continue

            ranked = agent.generate_and_rank(
                item["task"],
                candidate_count=item.get("candidate_count"),
            )
            best = ranked["best"]
            result = {
                "id": item["id"],
                "status": "completed",
                "score": best["score"],
                "apply_status": best["evaluation"]["apply_status"],
                "static_status": best["evaluation"]["static_status"],
                "test_status": best["evaluation"]["test_status"],
                "verdict": best["verdict"].get("verdict"),
                "selected_files": ranked["selected_files"],
                "expected_files": item.get("expected_files", []),
                "localization_recall": localization_score(
                    ranked["selected_files"],
                    item.get("expected_files", []),
                ),
                "changed_files": best["evaluation"]["changed_files"],
                "duration_seconds": round(time.time() - started, 3),
            }
        except Exception as exc:
            result = {
                "id": item["id"],
                "status": "failed",
                "error": str(exc),
                "duration_seconds": round(time.time() - started, 3),
            }
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    summary = {
        "task_count": len(results),
        "completed": sum(r["status"] == "completed" for r in results),
        "test_passed": sum(r.get("test_status") == "passed" for r in results),
        "average_score": round(
            sum(r.get("score", 0) for r in results) / max(1, len(results)),
            3,
        ),
        "results": results,
    }
    Path(output_path).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description="Local coding-agent benchmark")
    parser.add_argument("--suite", required=True, help="Benchmark suite JSON")
    parser.add_argument(
        "--output",
        default="benchmark_results.json",
        help="Result JSON path",
    )
    args = parser.parse_args()
    summary = run_suite(
        args.suite,
        Path(__file__).resolve().parent,
        args.output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
