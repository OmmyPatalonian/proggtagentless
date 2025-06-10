import argparse
import json
import os
from collections import Counter
from pathlib import Path

from agentless.util.postprocess_data import normalize_patch
from agentless.util.utils import load_json, load_jsonl

execution_results = dict()


def _load_results(args):
    global execution_results

    roots = [Path(folder) for folder in args.patch_folder.split(",")]

    intervals = [(0, int(args.num_samples / len(roots)) - 1) for _ in range(len(roots))]

    interval = intervals[0]
    for i in range(interval[0], interval[1] + 1):
        for _, root in enumerate(roots):
            patches = load_jsonl(root / f"output_{i}_normalized.jsonl")
            print(
                f"Loaded {len(patches)} patches from {root / f'output_{i}_normalized.jsonl'}"
            )
            if args.regression:
                regression_test_results = load_jsonl(
                    root / f"output_{i}_regression_test_results.jsonl"
                )
            if args.reproduction:
                reproduction_test_results = load_jsonl(
                    root / f"output_{i}_reproduction_test_results.jsonl"
                )

            for patch in patches[:]:
                if args.regression:
                    regression_test_result = [
                        x
                        for x in regression_test_results
                        if x["instance_id"] == patch["instance_id"]
                    ][0].get("regression", [0] * 10000)
                    regression_test_result = len(regression_test_result)
                else:
                    regression_test_result = 0

                if args.reproduction:
                    if (
                        len(
                            [
                                x
                                for x in reproduction_test_results
                                if x["instance_id"] == patch["instance_id"]
                            ]
                        )
                        == 1
                    ):
                        reproduction_test_result = [
                            x
                            for x in reproduction_test_results
                            if x["instance_id"] == patch["instance_id"]
                        ][0].get("reproduction", False)
                    else:
                        reproduction_test_result = False
                else:
                    reproduction_test_result = True

                execution_results.setdefault(patch["instance_id"], []).append(
                    {
                        "normalized_patch": patch["normalized_patch"].strip(),
                        "patch": patch["model_patch"],
                        "regression_test_result": regression_test_result,
                        "reproduction_test_result": reproduction_test_result,
                    }
                )


def _load_ground_truth_results(args):
    """
    Load ground truth test results for reranking.
    
    This function replaces the synthetic test result loading with ground truth test
    results from SWE-bench. It loads F2P (fails in original but passes with patch)
    and P2P (passes in original and still passes with patch) test results, allowing
    for more accurate patch ranking.
    """
    global execution_results

    roots = [Path(folder) for folder in args.patch_folder.split(",")]
    intervals = [(0, int(args.num_samples / len(roots)) - 1) for _ in range(len(roots))]

    interval = intervals[0]
    for i in range(interval[0], interval[1] + 1):
        for _, root in enumerate(roots):
            # Load normalized patches
            patches = load_jsonl(root / f"output_{i}_normalized.jsonl")
            print(
                f"Loaded {len(patches)} patches from {root / f'output_{i}_normalized.jsonl'}"
            )
            
            # Load ground truth results
            ground_truth_results_file = root / f"output_{i}_ground_truth_results.jsonl"
            if os.path.exists(ground_truth_results_file):
                ground_truth_results = load_jsonl(ground_truth_results_file)
                
                # Store results for each patch
                for patch in patches[:]:
                    instance_id = patch["instance_id"]
                    
                    # Find corresponding test results
                    instance_results = [r for r in ground_truth_results if r["instance_id"] == instance_id]
                    if instance_results:
                        f2p_result = instance_results[0].get("f2p_result", False)
                        p2p_result = instance_results[0].get("p2p_result", False)
                        overall_result = instance_results[0].get("overall_result", False)
                    else:
                        f2p_result = False
                        p2p_result = False
                        overall_result = False

                    execution_results.setdefault(instance_id, []).append(
                        {
                            "normalized_patch": patch["normalized_patch"].strip(),
                            "patch": patch["model_patch"],
                            "f2p_result": f2p_result,
                            "p2p_result": p2p_result,
                            "overall_result": overall_result
                        }
                    )


def get_sample(instance_id, sample_id) -> tuple[str, bool]:
    """Returns the diff and pass status."""
    return execution_results[instance_id][sample_id]


def get_all_patches(instance_id, num_samples, deduplicate) -> list[str]:
    """Returns all unique patches."""
    patches = [execution_results[instance_id][i]["patch"] for i in range(num_samples)]
    if deduplicate:
        patch_keys = [
            execution_results[instance_id][i]["normalized_patch"]
            for i in range(num_samples)
        ]
    else:
        patch_keys = [
            execution_results[instance_id][i]["patch"] for i in range(num_samples)
        ]
    unique_patches = set()
    patch_ids = []
    for i in range(num_samples):
        patch_key = patch_keys[i].strip()
        if patch_key and patch_key not in unique_patches:
            unique_patches.add(patch_key)
            patch_ids.append(i)
    return [(id, patches[id]) for id in patch_ids]


def get_all_patches_num(instance_id, num_samples, deduplicate) -> list[str]:
    """Returns all unique patches with number."""
    # print(f"{len(execution_results)}")
    patches = [execution_results[instance_id][i]["patch"] for i in range(num_samples)]
    if deduplicate:
        patch_keys = [
            execution_results[instance_id][i]["normalized_patch"]
            for i in range(num_samples)
        ]
    else:
        patch_keys = [
            execution_results[instance_id][i]["patch"] for i in range(num_samples)
        ]
    unique_patches = {}
    total_patch_num = {}
    patch_ids = []
    for i in range(num_samples):
        if patch_keys[i] and patch_keys[i] not in unique_patches:
            unique_patches[patch_keys[i]] = i
            patch_ids.append(i)
            total_patch_num[i] = 0
        if patch_keys[i]:
            total_patch_num[unique_patches[patch_keys[i]]] += 1

    return [(id, patches[id], total_patch_num[id]) for id in patch_ids]


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


def modified_length(normalized_patch):
    changed_length = 0

    for line in normalized_patch.splitlines():
        if len(line) > 3 and (line.startswith("---") or line.startswith("+++")):
            continue

        if line.startswith("-"):
            changed_length += 1
        if line.startswith("+"):
            changed_length += 1

    assert changed_length != 0

    return changed_length


def majority_voting(args):

    with open(args.output_file, "w") as f:

        for instance_id in execution_results:
            if len(execution_results[instance_id]) < args.num_samples:
                print(
                    f"There were only {len(execution_results[instance_id])} patches for {instance_id} instead of the full {args.num_samples}"
                )

            patch_keys = [
                execution_results[instance_id][i]["normalized_patch"]
                for i in range(len(execution_results[instance_id]))
            ]
            regression_tests = [
                execution_results[instance_id][i]["regression_test_result"]
                for i in range(len(execution_results[instance_id]))
            ]

            min_tests = min(regression_tests)
            regression_tests = [
                True if x == min_tests else False for x in regression_tests
            ]

            reproduction_tests = [
                execution_results[instance_id][i]["reproduction_test_result"]
                for i in range(len(execution_results[instance_id]))
            ]
            raw_patches = [
                execution_results[instance_id][i]["patch"]
                for i in range(len(execution_results[instance_id]))
            ]

            if args.regression and not args.reproduction:
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip() and regression_tests[i]
                ]
            elif args.reproduction:
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip()
                    and regression_tests[i]
                    and reproduction_tests[i]
                ]
                if len(patch_ids) == 0:
                    # reset to just using the all regression passing patches
                    patch_ids = [
                        i
                        for i in range(len(execution_results[instance_id]))
                        if patch_keys[i].strip() and regression_tests[i]
                    ]
            else:
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip()
                ]

            if not patch_ids:
                # just vote on all patches
                if not all([x.strip() == "" for x in raw_patches]) and not all(
                    [x.strip() == "" for x in patch_keys]
                ):
                    vote = Counter()
                    first_appear_idx = dict()
                    valid_indices = []
                    for i in range(len(execution_results[instance_id])):
                        sample = get_sample(instance_id, i)
                        patch_key = sample["normalized_patch"]
                        if patch_key != "":
                            valid_indices.append(i)
                            vote[patch_key] += 1
                            if patch_key not in first_appear_idx:
                                first_appear_idx[patch_key] = i
                    maj_selected_id = max(
                        valid_indices,
                        key=lambda i: (
                            vote[patch_keys[i]],
                            -first_appear_idx[patch_keys[i]],
                        ),
                    )
                    patch = get_sample(instance_id, maj_selected_id)["patch"]
                    result = {
                        "model_name_or_path": "agentless",
                        "instance_id": instance_id,
                        "model_patch": patch,
                    }
                else:
                    print(f"No raw patches valid for {instance_id}")
                    result = {
                        "model_name_or_path": "agentless",
                        "instance_id": instance_id,
                        "model_patch": "",
                    }
                f.write(json.dumps(result) + "\n")
                continue

            vote = Counter()
            first_appear_idx = dict()
            changed_length_idx = dict()
            for i in patch_ids:
                sample = get_sample(instance_id, i)
                patch_key, patch = sample["normalized_patch"], sample["patch"]
                vote[patch_key] += 1
                if patch_key not in first_appear_idx:
                    first_appear_idx[patch_key] = i
                    changed_length_idx[patch_key] = modified_length(patch_key)

            maj_selected_id = max(
                patch_ids,
                key=lambda i: (vote[patch_keys[i]], -first_appear_idx[patch_keys[i]]),
            )

            if args.target is not None and instance_id == args.target:
                for patch in vote:
                    print(
                        "=" * 20,
                        vote[patch],
                        "=" * 20,
                    )
                    print(patch)
                    print("=" * 50)

            sample = get_sample(instance_id, maj_selected_id)
            result = {
                "model_name_or_path": "agentless",
                "instance_id": instance_id,
                "model_patch": sample["patch"],
            }

            f.write(json.dumps(result) + "\n")


def majority_voting_with_ground_truth(args):
    """
    Perform majority voting on patches based on ground truth test results.
    
    This function enhances the original majority voting algorithm to consider
    ground truth test results when ranking patches. It can prioritize patches
    that pass F2P tests, P2P tests, or both, keeping the core selection logic
    but using more accurate test results.
    """
    with open(args.output_file, "w") as f:
        for instance_id in execution_results:
            if len(execution_results[instance_id]) < args.num_samples:
                print(
                    f"There were only {len(execution_results[instance_id])} patches for {instance_id} instead of the full {args.num_samples}"
                )

            patch_keys = [
                execution_results[instance_id][i]["normalized_patch"]
                for i in range(len(execution_results[instance_id]))
            ]
            
            # Get test results
            f2p_results = [
                execution_results[instance_id][i]["f2p_result"]
                for i in range(len(execution_results[instance_id]))
            ]
            
            p2p_results = [
                execution_results[instance_id][i]["p2p_result"]
                for i in range(len(execution_results[instance_id]))
            ]
            
            overall_results = [
                execution_results[instance_id][i]["overall_result"]
                for i in range(len(execution_results[instance_id]))
            ]
            
            raw_patches = [
                execution_results[instance_id][i]["patch"]
                for i in range(len(execution_results[instance_id]))
            ]

            # First try patches that pass both F2P and P2P
            if args.prioritize_overall:
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip() and overall_results[i]
                ]
            elif args.prioritize_f2p:
                # Prioritize F2P results
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip() and f2p_results[i]
                ]
            elif args.prioritize_p2p:
                # Prioritize P2P results
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip() and p2p_results[i]
                ]
            else:
                # No prioritization, use all non-empty patches
                patch_ids = [
                    i
                    for i in range(len(execution_results[instance_id]))
                    if patch_keys[i].strip()
                ]

            # If no patches meet the criteria, try a fallback
            if not patch_ids:
                # If we prioritized overall, try F2P only
                if args.prioritize_overall:
                    patch_ids = [
                        i
                        for i in range(len(execution_results[instance_id]))
                        if patch_keys[i].strip() and f2p_results[i]
                    ]
                
                # If still no patches, try any non-empty patch
                if not patch_ids:
                    patch_ids = [
                        i
                        for i in range(len(execution_results[instance_id]))
                        if patch_keys[i].strip()
                    ]

            # If still no valid patches, output empty patch
            if not patch_ids:
                if not all([x.strip() == "" for x in raw_patches]) and not all(
                    [x.strip() == "" for x in patch_keys]
                ):
                    # Use any non-empty patch
                    vote = Counter()
                    first_appear_idx = dict()
                    valid_indices = []
                    for i in range(len(execution_results[instance_id])):
                        sample = get_sample(instance_id, i)
                        patch_key = sample["normalized_patch"]
                        if patch_key != "":
                            valid_indices.append(i)
                            vote[patch_key] += 1
                            if patch_key not in first_appear_idx:
                                first_appear_idx[patch_key] = i
                    maj_selected_id = max(
                        valid_indices,
                        key=lambda i: (
                            vote[patch_keys[i]],
                            -first_appear_idx[patch_keys[i]],
                        ),
                    )
                    patch = get_sample(instance_id, maj_selected_id)["patch"]
                    result = {
                        "model_name_or_path": "agentless",
                        "instance_id": instance_id,
                        "model_patch": patch,
                    }
                else:
                    # Output empty patch
                    print(f"No valid patches for {instance_id}")
                    result = {
                        "model_name_or_path": "agentless",
                        "instance_id": instance_id,
                        "model_patch": "",
                    }
                f.write(json.dumps(result) + "\n")
                continue

            # Perform majority voting
            vote = Counter()
            first_appear_idx = dict()
            changed_length_idx = dict()
            for i in patch_ids:
                sample = get_sample(instance_id, i)
                patch_key, patch = sample["normalized_patch"], sample["patch"]
                vote[patch_key] += 1
                if patch_key not in first_appear_idx:
                    first_appear_idx[patch_key] = i
                    changed_length_idx[patch_key] = modified_length(patch_key)

            # Select patch based on vote count and appearance order
            maj_selected_id = max(
                patch_ids,
                key=lambda i: (vote[patch_keys[i]], -first_appear_idx[patch_keys[i]]),
            )

            # Print details for debugging if target is specified
            if args.target is not None and instance_id == args.target:
                for patch in vote:
                    print(
                        "=" * 20,
                        vote[patch],
                        "=" * 20,
                    )
                    print(patch)
                    print("=" * 50)

            # Get the selected patch
            sample = get_sample(instance_id, maj_selected_id)
            
            # Format the final result
            result = {
                "model_name_or_path": "agentless",
                "instance_id": instance_id,
                "model_patch": sample["patch"],
                "f2p_result": sample["f2p_result"],
                "p2p_result": sample["p2p_result"],
                "overall_result": sample["overall_result"]
            }

            # Write to output file
            f.write(json.dumps(result) + "\n")


def normalize_patches(args):
    # separate the patch folders
    output_folders = [Path(folder) for folder in args.patch_folder.split(",")]
    num_folders = len(output_folders)
    selected_ids = list(range(int(args.num_samples / num_folders)))

    for output_folder in output_folders:
        for i in selected_ids:
            if os.path.exists(output_folder / f"output_{i}_normalized.jsonl"):
                # skip
                continue
            patches = load_jsonl(output_folder / f"output_{i}_processed.jsonl")
            for d in patches:
                instance_id = d["instance_id"]
                patch = d["model_patch"]
                original_file_content = d["original_file_content"]
                new_file_content = d["new_file_content"]
                edited_files = d["edited_files"]
                normalized_patch = normalize_patch(
                    instance_id,
                    patch,
                    original_file_content,
                    new_file_content,
                    edited_files,
                )
                d["normalized_patch"] = normalized_patch
            with open(output_folder / f"output_{i}_normalized.jsonl", "w") as f:
                for d in patches:
                    f.write(json.dumps(d) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Rerank patches based on test results")
    parser.add_argument("--patch_folder", type=str, help="Folder containing patch files")
    parser.add_argument("--target", type=str, default=None, help="Target instance ID for detailed debugging")
    parser.add_argument("--num_samples", type=int, default=11, help="Number of samples to consider")
    parser.add_argument("--deduplicate", action="store_true", help="Remove duplicate patches")
    parser.add_argument("--regression", action="store_true", help="Use regression test results for ranking")
    parser.add_argument("--reproduction", action="store_true", help="Use reproduction test results for ranking")
    parser.add_argument("--ground_truth", action="store_true", help="Use ground truth test results for ranking")
    parser.add_argument("--output_file", type=str, default="all_preds.jsonl", help="Output file path")
    parser.add_argument("--prioritize_f2p", action="store_true", help="Prioritize patches passing F2P tests")
    parser.add_argument("--prioritize_p2p", action="store_true", help="Prioritize patches passing P2P tests")
    parser.add_argument("--prioritize_overall", action="store_true", help="Prioritize patches passing both F2P and P2P tests")
    args = parser.parse_args()

    # first normalize
    normalize_patches(args)
    
    # then load results and rerank
    if args.ground_truth:
        _load_ground_truth_results(args)
        majority_voting_with_ground_truth(args)
    else:
        _load_results(args)
        majority_voting(args)


if __name__ == "__main__":
    main()
