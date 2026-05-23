"""
Evaluation runner — runs the Q&A eval dataset against the live RAG pipeline
and scores results. Run manually after Phase 1 completion and after major changes.

Usage:
    python -m eval.run_eval
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.database import init_db
from backend.rag.pipeline import query

DATASET_PATH = Path(__file__).parent / "eval_dataset.json"


def score_response(answer: str, expected_contains: list[str]) -> dict:
    answer_lower = answer.lower()
    hits = [kw for kw in expected_contains if kw.lower() in answer_lower]
    keyword_score = len(hits) / len(expected_contains) if expected_contains else 1.0
    return {
        "keyword_score": round(keyword_score, 2),
        "hits": hits,
        "misses": [kw for kw in expected_contains if kw not in hits],
    }


def run():
    init_db()
    dataset = json.loads(DATASET_PATH.read_text())
    results = []
    passed = 0

    print(f"\n{'='*60}")
    print(f"ArthaOS Eval — {len(dataset)} queries")
    print(f"{'='*60}\n")

    for item in dataset:
        result = query(item["question"])
        score = score_response(result.answer, item["expected_contains"])
        status = "PASS" if score["keyword_score"] >= 0.5 else "FAIL"
        if status == "PASS":
            passed += 1

        print(f"[{status}] {item['id']} ({item['type']})")
        print(f"  Q: {item['question']}")
        print(f"  A: {result.answer[:120]}...")
        print(f"  Score: {score['keyword_score']} | Low conf: {result.low_confidence}")
        if score["misses"]:
            print(f"  Missing: {score['misses']}")
        print()

        results.append({
            "id": item["id"],
            "type": item["type"],
            "question": item["question"],
            "answer": result.answer,
            "low_confidence": result.low_confidence,
            "status": status,
            **score,
        })

    print(f"{'='*60}")
    print(f"Results: {passed}/{len(dataset)} passed ({round(passed/len(dataset)*100)}%)")
    print(f"{'='*60}\n")

    # Write results
    out = Path(__file__).parent / "last_run.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"Results saved to {out}")

    # Exit non-zero if any must-pass queries failed
    must_pass = {"spend_jan", "dining_category", "emi_query", "top_spend", "subscriptions"}
    failed_must = [r for r in results if r["id"] in must_pass and r["status"] == "FAIL"]
    if failed_must:
        print(f"\n❌ Must-pass queries failed: {[r['id'] for r in failed_must]}")
        sys.exit(1)

    print("✅ All must-pass queries passed.")


if __name__ == "__main__":
    run()
