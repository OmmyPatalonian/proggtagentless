#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import subprocess
from typing import Dict, List, Optional

RESULT_BEGIN = "RESULT_JSON_BEGIN"
RESULT_END   = "RESULT_JSON_END"
HEX40_RE     = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)


def extract_json(stdout: str, stderr: str = ""):
    blob = stdout + "\n" + stderr
    import re
    m = re.search(rf"{RESULT_BEGIN}\s*(\{{.*\}})\s*{RESULT_END}", blob, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def load_preds(jsonl_path: pathlib.Path, limit: Optional[int]) -> List[dict]:
    out = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            patch = obj.get("model_patch", "").strip()
            if not patch:
                continue
            out.append(obj)
            if limit and len(out) >= limit:
                break
    return out


def guess_commit_from_tests(tests_txt: pathlib.Path) -> Optional[str]:
    try:
        text = tests_txt.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return None
    m = HEX40_RE.search(text)
    return m.group(0) if m else None


def run_container(
    image: str,
    repo_url: str,
    base_commit: Optional[str],
    tests_file: pathlib.Path,
    patch_file: pathlib.Path,
    mount_repo_out: Optional[pathlib.Path] = None,
) -> dict:
    cmd = [
        "docker", "run", "--rm",
        "-e", f"REPO_URL={repo_url}",
        "-v", f"{tests_file}:/workspace/ground_truth_tests.txt:ro",
        "-v", f"{patch_file}:/workspace/patch.diff:ro",
    ]
    if base_commit:
        cmd += ["-e", f"BASE_COMMIT={base_commit}"]
    if mount_repo_out:
        mount_repo_out.mkdir(parents=True, exist_ok=True)
        cmd += ["-v", f"{mount_repo_out}:/workspace/repo"]

    cmd.append(image)

    proc = subprocess.run(cmd, text=True, capture_output=True)
    stdout, stderr = proc.stdout, proc.stderr

    res = extract_json(stdout, stderr)
    if not res:
        res = {"error": "no RESULT_JSON", "passed": 0, "total": 0,
               "stdout": stdout[-2000:], "stderr": stderr[-2000:]}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True,
                    help="Path to all_preds.jsonl (or *_processed.jsonl)")
    ap.add_argument("--gt_root", required=True,
                    help="ground_truth_tests/<inst>/tests.txt directory")
    ap.add_argument("--base_commits", default=None,
                    help="JSON map {instance_id: base_commit} (produced by bench_loader.py)")
    ap.add_argument("--image", default="swebench-runner:latest")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default="results/evaluation_results.json")
    ap.add_argument("--repo_dump_root", default=None,
                    help="Bind-mount cloned repo for debugging rejects")
    args = ap.parse_args()

    preds_path = pathlib.Path(args.predictions).resolve()
    gt_root    = pathlib.Path(args.gt_root).resolve()
    out_path   = pathlib.Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Optional base commit map
    base_map: Dict[str, str] = {}
    if args.base_commits and os.path.isfile(args.base_commits):
        base_map = json.load(open(args.base_commits, encoding="utf-8"))

    preds = load_preds(preds_path, args.limit)

    results = {}
    for idx, obj in enumerate(preds, 1):
        inst = obj["instance_id"]
        print(f"[{idx}/{len(preds)}] {inst}")

        repo_root = inst.split("__", 1)[0]      # "django"
        repo_url  = f"{repo_root}/{repo_root}"  # "django/django"

        inst_dir   = gt_root / inst
        tests_file = inst_dir / "tests.txt"
        if not tests_file.exists():
            print(f"  ! Missing {tests_file}, skipping.")
            results[inst] = {"error": "no-tests", "passed": 0, "total": 0}
            continue

        # Write/overwrite patch
        patch_file = inst_dir / "patch.diff"
        patch_file.write_text(obj["model_patch"], encoding="utf-8")

        # Resolve base commit
        base_commit = obj.get("base_commit") or \
                      base_map.get(inst) or \
                      (inst_dir / "base_commit.txt").read_text().strip() if (inst_dir / "base_commit.txt").exists() else None
        if not base_commit:
            base_commit = guess_commit_from_tests(tests_file)

        repo_out = None
        if args.repo_dump_root:
            repo_out = pathlib.Path(args.repo_dump_root).resolve() / f"tmp_repo_{inst}"

        res = run_container(
            image=args.image,
            repo_url=repo_url,
            base_commit=base_commit,
            tests_file=tests_file,
            patch_file=patch_file,
            mount_repo_out=repo_out,
        )
        results[inst] = res

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved results to {out_path}")


if __name__ == "__main__":
    main()

