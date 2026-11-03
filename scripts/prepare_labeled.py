"""Export the supplied 660 Qwen records for `sop-candidate fit`, without API calls."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from baselines.runner import load_cases


def export(data, output):
    snapshots = []
    for row in load_cases(data):
        if "trajectory" not in row:
            raise ValueError("This export requires the supplied labeled Qwen records")
        history = row["trajectory"]
        receipts = [e["receipt"] for e in history if e.get("kind") == "tool_receipt"]
        snapshots.append({
            "case_id": row["case_id"], "domain": row["domain"],
            "answer": row["answer"], "p_error": row["p_error"],
            "samples": row["samples"], "status": row["status"],
            "failure": row["failure"], "history": history,
            "cost": sum(r.get("cost", 0) for r in receipts),
        })
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Avoid mixing supplied initial records with an existing experiment's queries.
    if (output / "initial.jsonl").exists() or (output / "posterior.jsonl").exists():
        raise ValueError("Use a new output directory; trajectory files already exist")
    with (output / "initial.jsonl").open("w", encoding="utf-8") as f:
        for snapshot in snapshots:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    return {"initial_trajectories": len(snapshots),
            "completed": sum(s["status"] == "completed" for s in snapshots),
            "failed": sum(s["status"] == "failed" for s in snapshots),
            "output": str(output / "initial.jsonl"), "api_requests": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path, default=ROOT / ".runs" / "provided_initials")
    args = parser.parse_args()
    print(json.dumps(export(args.data, args.output), ensure_ascii=False, indent=2))
