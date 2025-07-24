#!/usr/bin/env python3
"""
Extract ground-truth tests (F2P/P2P) + base commits from SWE-bench and write:
    f2p.txt
    p2p.txt
    tests.txt        (merged, normalized pytest node IDs)
    base_commit.txt
    test_patch.diff  (if present)
    gold_patch.diff  (optional)
    repo.txt
    environment_setup_commit.txt

Optionally writes {instance_id: base_commit} to --commit_out.
"""

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from datasets import load_dataset

# Strict pytest node-id: tests/....py::<something>::<something> (>=1 "::" groups)
STRICT_NODE_RE = re.compile(r'^tests\/.+\.py(::[^:]+){2,}$')


def parse_tests(val):
    """FAIL_TO_PASS / PASS_TO_PASS may be JSON string or list."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError as e:
            raise ValueError(f"Bad JSON in test field: {e}") from e
    return val


def write_lines(lines: List[str], path: Path):
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def to_node_id(raw: str) -> Optional[str]:
    """
    Convert SWE-bench spec -> pytest node id.
    Drop anything with spaces or malformed pieces.
    """
    raw = raw.strip()
    if not raw:
        return None

    # Already a strict node id?
    if STRICT_NODE_RE.match(raw):
        return raw

    # If it already has '::' but isn't strict, skip it
    if "::" in raw and not STRICT_NODE_RE.match(raw):
        return None

    # "(pkg.mod.Class.test)" or "pkg.mod.Class.test"
    m = re.search(r'\(([^)]+)\)$', raw)
    target = m.group(1) if m else raw
    if " " in target:
        return None

    parts = target.split(".")
    if len(parts) < 3:
        return None

    file_path = "tests/" + "/".join(parts[:-2]) + ".py"
    cls = parts[-2]
    func = parts[-1]
    candidate = f"{file_path}::{cls}::{func}"
    return candidate if STRICT_NODE_RE.match(candidate) else None


def get_tests(
    dataset: str = "princeton-nlp/SWE-bench_Lite",
    ids: Optional[List[str]] = None,
    output_dir: str = "ground_truth_tests",
    commit_out: Optional[str] = None,
) -> Dict[str, Tuple[List[str], List[str], str]]:
    ds = load_dataset(dataset, split="test")
    if logging.getLogger().level <= logging.INFO:
        print(f"Loaded {len(ds)} instances from {dataset}")

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Tuple[List[str], List[str], str]] = {}

    for inst in ds:
        instance_id = inst["instance_id"]
        if ids and instance_id not in ids:
            continue

        f2p_tests = parse_tests(inst["FAIL_TO_PASS"])
        p2p_tests = parse_tests(inst["PASS_TO_PASS"])
        base_commit = inst.get("base_commit", "")

        test_patch = inst.get("test_patch", "")
        gold_patch = inst.get("patch", "")
        repo_name = inst.get("repo", "")
        env_setup_commit = inst.get("environment_setup_commit", "")

        inst_dir = out_root / instance_id
        inst_dir.mkdir(parents=True, exist_ok=True)

        write_lines(f2p_tests, inst_dir / "f2p.txt")
        write_lines(p2p_tests, inst_dir / "p2p.txt")

        # Normalize, skip junk
        all_tests: List[str] = []
        skipped = 0
        for t in (f2p_tests + p2p_tests):
            nid = to_node_id(t)
            if nid:
                all_tests.append(nid)
            else:
                skipped += 1

        # Dedup preserve order
        seen = set()
        uniq_tests = [t for t in all_tests if not (t in seen or seen.add(t))]
        write_lines(uniq_tests, inst_dir / "tests.txt")

        if skipped and logging.getLogger().level <= logging.INFO:
            print(f"[{instance_id}] Skipped {skipped} malformed specs")

        (inst_dir / "base_commit.txt").write_text(base_commit + "\n", encoding="utf-8")
        if repo_name:
            (inst_dir / "repo.txt").write_text(repo_name + "\n", encoding="utf-8")
        if env_setup_commit:
            (inst_dir / "environment_setup_commit.txt").write_text(env_setup_commit + "\n", encoding="utf-8")
        if test_patch:
            (inst_dir / "test_patch.diff").write_text(test_patch, encoding="utf-8")
        if gold_patch:
            (inst_dir / "gold_patch.diff").write_text(gold_patch, encoding="utf-8")

        results[instance_id] = (f2p_tests, p2p_tests, base_commit)

    if commit_out:
        commit_map = {k: v[2] for k, v in results.items()}
        Path(commit_out).parent.mkdir(parents=True, exist_ok=True)
        Path(commit_out).write_text(json.dumps(commit_map, indent=2), encoding="utf-8")

    return results


def load_tests(instance_id: str, test_dir: str = "ground_truth_tests"):
    inst_dir = Path(test_dir) / instance_id
    f2p_path = inst_dir / "f2p.txt"
    p2p_path = inst_dir / "p2p.txt"
    if not f2p_path.exists() or not p2p_path.exists():
        raise FileNotFoundError(f"Missing test files for {instance_id}")
    f2p = [l.strip() for l in f2p_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    p2p = [l.strip() for l in p2p_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return f2p, p2p


# Aliases
extract_gt_tests = get_tests
load_gt_tests = load_tests
load_ground_truth_tests = load_tests


def main():
    p = argparse.ArgumentParser(description="Extract ground truth tests from SWE-bench")
    p.add_argument("--dataset", default="princeton-nlp/SWE-bench_Lite",
                   choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"])
    p.add_argument("--output_dir", default="ground_truth_tests")
    p.add_argument("--target_ids", nargs="+", type=str)
    p.add_argument("--commit_out", type=str)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    assert get_tests(ids=["__does_not_exist__"]) == {}, "Empty filter should return empty dict"

    results = get_tests(args.dataset, args.target_ids, args.output_dir, args.commit_out)

    print(f"Extracted tests for {len(results)} instances")
    for inst_id, (f2p, p2p, bc) in results.items():
        print(f"{inst_id}: {len(f2p)} F2P, {len(p2p)} P2P, base_commit={bc or 'N/A'}")

    if results:
        sample = next(iter(results))
        f2p, p2p = load_tests(sample, args.output_dir)
        print(f"Successfully loaded tests for {sample}")
        print(f"Sample F2P test: {f2p[0] if f2p else 'None'}")


if __name__ == "__main__":
    main()
