"""Run ground truth tests from SWE-bench for validating patches.

This script was created to replace run_reproduction_tests.py and focuses 
exclusively on executing ground truth tests from SWE-bench rather than 
the synthetic reproduction tests used elsewhere in the codebase.

This file maintains the same output format for compatibility with the
reranking system while providing a cleaner interface focused solely on
ground truth tests from SWE-bench.
"""
import argparse
import json
import os

from datasets import load_dataset

from agentless.test.run_tests import run_ground_truth_tests, txt_file_contains_string
from agentless.util.utils import load_jsonl


def extract_patch_info(lines):
    """Extract instance IDs and patches from data lines."""
    ids = [line["instance_id"] for line in lines]
    patches = [line["model_patch"] for line in lines]
    return ids, patches


def run_gt_batch(instance_ids, patches, args, run_id, ground_truth_dir):
    """Run ground truth tests for a batch of instances."""
    results = run_ground_truth_tests(
        instance_ids,
        patches,
        args.num_workers,
        run_id,
        args.instance_ids,
        args.timeout,
        ground_truth_dir=ground_truth_dir,
        apply_model_patch=True,
    )
    return results


def check_log_file(log_path, success_text):
    """Check if a log file contains the success text."""
    if not os.path.isfile(log_path):
        return False
    return txt_file_contains_string(log_path, success_text)


def load_results_from_logs(data_lines, run_id):
    """Load test results from existing log files."""
    results = {}
    
    for data in data_lines:
        instance_id = data["instance_id"]
        
        # Check F2P results
        f2p_log = f"logs/run_evaluation/{run_id}_f2p/test/{instance_id}/test_output.txt"
        f2p_result = check_log_file(f2p_log, "Issue resolved")
        
        # Check P2P results
        p2p_log = f"logs/run_evaluation/{run_id}_p2p/test/{instance_id}/test_output.txt"
        p2p_result = False
        if os.path.isfile(p2p_log):
            p2p_result = not txt_file_contains_string(p2p_log, "Issue reproduced")
        
        # Combine results
        results[instance_id] = {
            "f2p_result": f2p_result,
            "p2p_result": p2p_result,
            "overall_result": f2p_result and p2p_result
        }
    
    return results


def save_results(data_lines, test_results, output_path):
    """Save test results to a JSONL file."""
    updated_data = []
    
    for data in data_lines:
        instance_id = data["instance_id"]
        if instance_id in test_results:
            # Add test results to the data
            data["f2p_result"] = test_results[instance_id]["f2p_result"]
            data["p2p_result"] = test_results[instance_id]["p2p_result"]
            data["overall_result"] = test_results[instance_id]["overall_result"]
        updated_data.append(data)
    
    # Write updated data to file
    with open(output_path, "w") as f:
        for data in updated_data:
            f.write(json.dumps(data) + "\n")


def run_ground_truth_tests_main(args):
    """
    Run ground truth tests on patches.
    
    This function uses real benchmark tests from SWE-bench for validation
    instead of synthetic tests. It loads F2P and P2P tests and evaluates
    patches against them.
    
    Args:
        args: Command-line arguments
    """
    if args.testing:
        # For test selection - run on original repo to verify which tests are suitable
        ds = load_dataset(args.dataset)
        instance_ids = ds["test"]["instance_id"]
        patches = ["" for _ in instance_ids]  # Empty patches for testing

        # This will just verify which tests are valid - not normally used with ground truth
        print("Warning: Testing mode with ground truth tests is not typically used")
        print("This will only verify that tests can be executed, not that they reproduce issues")
        
        results = run_ground_truth_tests(
            instance_ids,
            patches,
            args.num_workers,
            args.run_id,
            args.instance_ids,
            args.timeout,
            args.ground_truth_dir,
            apply_model_patch=False,
        )
        
        with open(f"ground_truth_test_verification_{args.run_id}.json", "w") as file:
            file.write(json.dumps(results))

    elif args.predictions_path == "gold":
        # Evaluate ground truth patches from the benchmark
        ds = load_dataset(args.dataset)
        instance_ids = ds["test"]["instance_id"]
        patches = ds["test"]["patch"]

        results = run_ground_truth_tests(
            instance_ids,
            patches,
            args.num_workers,
            args.run_id,
            args.instance_ids,
            args.timeout,
            args.ground_truth_dir,
            apply_model_patch=True,
        )

        with open("gold_ground_truth_results.json", "w") as file:
            file.write(json.dumps(results))

    else:
        # Run on the agentless generated patches
        assert args.predictions_path.endswith("_processed.jsonl"), \
            "Predictions path must end with _processed.jsonl"
            
        with open(args.predictions_path, "r") as file:
            data_lines = [json.loads(line) for line in file]

        if args.load:
            # Load existing results rather than running tests again
            test_results = load_results_from_logs(data_lines, args.run_id)
            
            # Save to file
            results_file = args.predictions_path.replace(
                "processed.jsonl", "ground_truth_results.jsonl"
            )
            save_results(data_lines, test_results, results_file)
        else:            # Run the ground truth tests
            instance_ids, patches = extract_patch_info(data_lines)
            
            results = run_gt_batch(
                instance_ids, 
                patches, 
                args, 
                args.run_id, 
                args.ground_truth_dir
            )
            
            # Format results for saving
            test_results = {}
            for instance_id, result in results.items():
                test_results[instance_id] = {
                    "f2p_result": result.get("f2p_result", False),
                    "p2p_result": result.get("p2p_result", False),
                    "overall_result": result.get("f2p_result", False) and result.get("p2p_result", False)
                }
            
            # Save results
            results_file = args.predictions_path.replace(
                "processed.jsonl", "ground_truth_results.jsonl"
            )
            save_results(data_lines, test_results, results_file)


def main():
    """Parse arguments and run the ground truth tests."""
    parser = argparse.ArgumentParser(description="Run ground truth tests from SWE-bench")
    parser.add_argument("--run_id", type=str, required=True, 
                        help="Unique identifier for this test run")
    parser.add_argument("--testing", action="store_true", 
                        help="Test ground truth tests without applying patches")
    parser.add_argument("--predictions_path", type=str,
                        help="Path to processed patch file")
    parser.add_argument("--num_workers", type=int, default=12,
                        help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=600, 
                        help="Timeout for running tests in seconds")
    parser.add_argument("--instance_ids", nargs="+", type=str,
                        help="Specific instance IDs to run (space separated)")
    parser.add_argument("--dataset", type=str, default="princeton-nlp/SWE-bench_Lite",
                        choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"],
                        help="Dataset to use")
    parser.add_argument("--ground_truth_dir", type=str, default="ground_truth_tests",
                        help="Directory containing ground truth tests")
    parser.add_argument("--load", action="store_true",
                        help="Load existing results instead of running tests")

    args = parser.parse_args()
    run_ground_truth_tests_main(args)


if __name__ == "__main__":
    main()
