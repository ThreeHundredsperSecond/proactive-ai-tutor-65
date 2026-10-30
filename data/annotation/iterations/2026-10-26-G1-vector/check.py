"""Technical checks only; semantic acceptance is recorded separately in review.md."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        assert digest(HERE / name) == expected, name
    before = json.loads((HERE / "input.json").read_text(encoding="utf-8"))
    after = json.loads((HERE / "raw.txt").read_text(encoding="utf-8"))
    assert set(after) == {"task_id", "solution_status", "steps", "kc_candidates", "methods", "warnings"}
    assert after["task_id"] == before["task_id"]
    assert after["solution_status"] == before["solution_status"]
    assert [{key: s[key] for key in ("id", "action", "result")} for s in after["steps"]] == before["steps"]
    steps = {s["id"] for s in after["steps"]}
    kcs = {k["id"] for k in after["kc_candidates"]}
    assert len(steps) == len(after["steps"])
    assert len(kcs) == len(after["kc_candidates"])
    assert len({m["id"] for m in after["methods"]}) == len(after["methods"])
    for s in after["steps"]:
        assert set(s) == {"id", "action", "result", "kc_ids"}
        assert isinstance(s["kc_ids"], list) and s["kc_ids"]
        assert len(s["kc_ids"]) == len(set(s["kc_ids"]))
        assert set(s["kc_ids"]) <= kcs
    for k in after["kc_candidates"]:
        assert set(k) == {"id", "name", "description"}
        assert all(isinstance(v, str) and v.strip() for v in k.values())
    assert {kid for s in after["steps"] for kid in s["kc_ids"]} == kcs
    assert after["methods"]
    for m in after["methods"]:
        assert set(m) == {"id", "name", "step_ids"}
        assert isinstance(m["step_ids"], list) and m["step_ids"]
        assert set(m["step_ids"]) <= steps
        assert len(m["step_ids"]) == len(set(m["step_ids"]))
        assert isinstance(m["name"], str) and m["name"].strip()
    assert isinstance(after["warnings"], list)
    assert all(isinstance(w, str) for w in after["warnings"])
    result = {
        "status": "passed", "raw_sha256": digest(HERE / "raw.txt"),
        "input_sha256": digest(HERE / "input.json"), "checker_sha256": digest(Path(__file__)),
        "checks": ["frozen prompt/input hashes", "exact solution preservation", "JSON fields and references", "all KCs used"],
        "steps": len(steps), "kcs": len(kcs), "methods": len(after["methods"]),
        "semantic_validation": "not performed by this script; see review.md",
    }
    (HERE / "technical-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
