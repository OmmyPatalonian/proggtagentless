#!/usr/bin/env python3
"""
Load ground-truth tests (F2P/P2P) + base commits from SWE-bench.

Creates per-instance folder:
    f2p.txt
    p2p.txt
    tests.txt        (F2P + P2P merged)
    base_commit.txt
    test_patch.diff  (ONLY if present; e.g., Verified)
    gold_patch.diff  (solution patch; optional)
    repo.txt
    environment_setup_commit.txt

Optionally writes a JSON map of {instance_id: base_commit} (--commit_out).

Usage example:
    python agentless/util/bench_loader.py \
      --dataset princeton-nlp/SWE-bench_Lite \
      --output_dir agentless/test/docker_eval/ground_truth_tests \
      --target_ids django__django-17087 django__django-14667 \
      --commit_out commit_map.json
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from datasets import load_dataset


def parse_tests(test_field):
    """Parse FAIL_TO_PASS / PASS_TO_PASS which may be JSON string or list."""
    if isinstance(test_field, str):
        try:
            return json.loads(test_field)
        except json.JSONDecodeError as e:
            raise ValueError(f"Bad JSON in test field: {e}") from e
    return test_field


def write_lines(lines: List[str], path: Path):
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def get_tests(
    dataset: str = "princeton-nlp/SWE-bench_Lite",
    ids: List[str] | None = None,
    output_dir: str = "ground_truth_tests",
    commit_out: str | None = None,
) -> Dict[str, Tuple[List[str], List[str], str]]:
    """
    Extract ground-truth tests (+ base commit) from SWE-bench.

    Returns:
        {instance_id: (f2p_tests, p2p_tests, base_commit)}

    Side effects:
        Writes per-instance files in output_dir (see module docstring).
    """
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

        test_patch = inst.get("test_patch", "")  # present in Verified
        gold_patch = inst.get("patch", "")       # solution patch
        repo_name = inst.get("repo", "")         # e.g. astropy/astropy
        env_setup_commit = inst.get("environment_setup_commit", "")

        inst_dir = out_root / instance_id
        inst_dir.mkdir(parents=True, exist_ok=True)

        write_lines(f2p_tests, inst_dir / "f2p.txt")
        write_lines(p2p_tests, inst_dir / "p2p.txt")
        write_lines(f2p_tests + p2p_tests, inst_dir / "tests.txt")
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
    """
    Load F2P/P2P for one instance.

    Returns:
        (f2p_tests, p2p_tests)
    """
    inst_dir = Path(test_dir) / instance_id
    f2p_path = inst_dir / "f2p.txt"
    p2p_path = inst_dir / "p2p.txt"

    if not f2p_path.exists() or not p2p_path.exists():
        raise FileNotFoundError(f"Missing test files for {instance_id}")

    f2p = [l.strip() for l in f2p_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    p2p = [l.strip() for l in p2p_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return f2p, p2p


# Backwards-compatible aliases
extract_gt_tests = get_tests
load_gt_tests = load_tests
load_ground_truth_tests = load_tests


def main():
    parser = argparse.ArgumentParser(description="Extract ground truth tests from SWE-bench")
    parser.add_argument(
        "--dataset",
        default="princeton-nlp/SWE-bench_Lite",
        choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"],
        help="Dataset to extract tests from",
    )
    parser.add_argument("--output_dir", default="ground_truth_tests",
                        help="Directory to save per-instance files")
    parser.add_argument("--target_ids", nargs="+", type=str,
                        help="Space-separated instance_ids to extract (default = all)")
    parser.add_argument("--commit_out", type=str,
                        help="Optional path to write {instance_id: base_commit} map JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    # Smoke-test empty filter
    assert get_tests(ids=["__does_not_exist__"]) == {}, "Empty filter should return empty dict"

    results = get_tests(
        dataset=args.dataset,
        ids=args.target_ids,
        output_dir=args.output_dir,
        commit_out=args.commit_out,
    )

    print(f"Extracted tests for {len(results)} instances")
    for inst_id, (f2p, p2p, bc) in results.items():
        print(f"{inst_id}: {len(f2p)} F2P, {len(p2p)} P2P, base_commit={bc or 'N/A'}")

    # Optional load check
    if results:
        sample_id = next(iter(results))
        f2p, p2p = load_tests(sample_id, args.output_dir)
        print(f"Successfully loaded tests for {sample_id}")
        print(f"Sample F2P test: {f2p[0] if f2p else 'None'}")


if __name__ == "__main__":
    main()

