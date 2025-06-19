# Rerank patches using ground truth test results from SWE-bench
# Replaces synthetic reproduction tests with real F2P and P2P tests

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from agentless.util.postprocess_data import normalize_patch
from agentless.util.utils import load_json, load_jsonl

results = dict()


def load_results(args):
    """Load ground truth test results from patch folders"""
    global results

    # Get roots from comma-separated list
    roots = [Path(folder) for folder in args.patch_folder.split(",")]
    max_per_root = int(args.num_samples / len(roots))

    # Load patch data from each folder
    for i in range(max_per_root):
        for root in roots:
            # Load patches
            patches_file = root / f"output_{i}_normalized.jsonl"
            if not patches_file.exists():
                continue
                
            patches = load_jsonl(patches_file)
            print(f"Loaded {len(patches)} patches from {patches_file}")
            
            # Load test results
            results_file = root / f"output_{i}_ground_truth_test_results.jsonl"
            if not results_file.exists():
                print(f"Warning: No test results for {patches_file}")
                continue
                
            gt_results = load_jsonl(results_file)

            # Process each patch
            for patch in patches:
                instance_id = patch["instance_id"]
                
                # Find matching test result
                gt_result = None
                for x in gt_results:
                    if x["instance_id"] == instance_id:
                        gt_result = x
                        break
                
                if gt_result is None:
                    continue                # Extract test info
                f2p_passed = gt_result.get("f2p_passed", 0)
                f2p_total = gt_result.get("f2p_total", 0)
                p2p_passed = gt_result.get("p2p_passed", 0)
                p2p_total = gt_result.get("p2p_total", 0)
                
                # Calculate pass rates
                f2p_rate = f2p_passed / f2p_total if f2p_total > 0 else 0
                p2p_rate = p2p_passed / p2p_total if p2p_total > 0 else 0
                
                # Store result
                if instance_id not in results:
                    results[instance_id] = []
                    
                results[instance_id].append({
                    "patch": patch["model_patch"],
                    "score": patch.get("score", 0),
                    "f2p_passed": f2p_passed,
                    "f2p_total": f2p_total,
                    "p2p_passed": p2p_passed,
                    "p2p_total": p2p_total,
                    "f2p_rate": f2p_rate,
                    "p2p_rate": p2p_rate,
                })


def rerank_patches(args):
    """Rerank patches based on ground truth test results"""
    global results
    
    # Load results from folders
    load_results(args)
    
    # Create output folder
    os.makedirs(args.output_folder, exist_ok=True)
    
    # Write reranked patches
    with open(f"{args.output_folder}/reranked.jsonl", "w") as f:
        for instance_id, patches in results.items():
            # Sort by F2P rate first, then P2P
            patches.sort(key=lambda x: (
                x["f2p_rate"],  # Prioritize failing tests that now pass
                x["p2p_rate"],  # Then consider regression prevention
                x["score"]      # Finally consider model confidence
            ), reverse=True)
            
            # Get best patch
            best = patches[0]
            
            # Write result
            result = {
                "instance_id": instance_id,
                "model_patch": best["patch"],
                "f2p_passed": best["f2p_passed"],
                "f2p_total": best["f2p_total"],
                "p2p_passed": best["p2p_passed"],
                "p2p_total": best["p2p_total"],
                "score": best["score"],
            }
            
            f.write(json.dumps(result) + "\n")
            
    print(f"Reranked patches saved to {args.output_folder}/reranked.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rerank patches using ground truth test results"
    )
    parser.add_argument(
        "--patch_folder",
        type=str,
        help="Folders with patches (comma-separated)",
        required=True,
    )
    parser.add_argument(
        "--output_folder",
        type=str,
        help="Where to save reranked patches",
        default="results/reranked",
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        help="Samples per instance",
        default=10,
    )
    
    args = parser.parse_args()
    rerank_patches(args)
