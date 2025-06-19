# Load ground truth tests from SWE-bench dataset
# Gets actual F2P and P2P tests from SWE-bench
# instead of generating synthetic tests

import json
import os
import argparse
import logging
from typing import Dict, List, Tuple, Any

from datasets import load_dataset


def get_tests(dataset="princeton-nlp/SWE-bench_Lite", 
             ids=None, 
             output_dir="ground_truth_tests"):
    """Get ground truth tests from SWE-bench dataset.
    
    Args:
        dataset: Dataset name (SWE-bench_Lite or SWE-bench_Verified)
        ids: Specific instance IDs to extract (None = all)
        output_dir: Where to save test files
    
    Returns:
        Dict mapping instance_id to (f2p_tests, p2p_tests)
    """
    try:
        # Load the dataset
        ds = load_dataset(dataset, split="test")
        if logging.getLogger().level <= logging.INFO:
            print(f"Loaded {len(ds)} instances from {dataset}")
    except Exception as e:
        print(f"Error loading dataset: {e}")
        raise ValueError(f"Failed to load dataset: {e}")
        raise ValueError(f"Failed to load dataset {dataset}: {e}")
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating directory: {e}")
        raise IOError(f"Failed to create directory: {e}")
    
    results = {}
    
    for instance in ds:
        instance_id = instance["instance_id"]
        
        if ids and instance_id not in ids:
            continue
        
        # Get F2P and P2P tests
        f2p_tests = parse_tests(instance["FAIL_TO_PASS"])
        p2p_tests = parse_tests(instance["PASS_TO_PASS"])
        
        # Save to output files
        instance_dir = os.path.join(output_dir, instance_id)
        os.makedirs(instance_dir, exist_ok=True)
        
        write_tests(f2p_tests, os.path.join(instance_dir, "f2p.txt"))
        write_tests(p2p_tests, os.path.join(instance_dir, "p2p.txt"))
        
        results[instance_id] = (f2p_tests, p2p_tests)
        
    return results


def write_tests(tests, filepath):
    """Write tests to a file, one per line"""
    with open(filepath, "w") as f:
        for test in tests:
            f.write(f"{test}\n")


def parse_tests(test_field):
    """Parse test field - could be string (JSON) or list"""
    if isinstance(test_field, str):
        try:
            return json.loads(test_field)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            raise ValueError(f"Bad JSON in test field: {e}")
    return test_field


def load_tests(instance_id, test_dir="ground_truth_tests"):
    """Load ground truth tests for an instance
    
    Args:
        instance_id: Instance to load tests for
        test_dir: Directory with test files
        
    Returns:
        Tuple of (f2p_tests, p2p_tests)
    """
    instance_dir = os.path.join(test_dir, instance_id)
    
    f2p_path = os.path.join(instance_dir, "f2p.txt")
    p2p_path = os.path.join(instance_dir, "p2p.txt")
    
    # Make sure files exist
    if not os.path.exists(f2p_path) or not os.path.exists(p2p_path):
        print(f"Missing test files for {instance_id}")
        raise FileNotFoundError(f"Missing test files for {instance_id}")
    
    try:
        with open(f2p_path, "r") as f:
            f2p_tests = [line.strip() for line in f.readlines()]
            
        with open(p2p_path, "r") as f:
            p2p_tests = [line.strip() for line in f.readlines()]
    except Exception as e:
        print(f"Error reading test files: {e}")
        raise IOError(f"Error reading test files: {e}")
    
    return f2p_tests, p2p_tests


# Keep old function names for compatibility
extract_gt_tests = get_tests
load_gt_tests = load_tests
load_ground_truth_tests = load_tests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract ground truth tests from SWE-bench")
    parser.add_argument(
        "--dataset",
        type=str,
        default="princeton-nlp/SWE-bench_Lite",
        choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"],
        help="Dataset to extract tests from",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="ground_truth_tests",
        help="Directory to save the test lists",
    )
    parser.add_argument(
        "--target_ids",
        nargs="+",
        type=str,
        help="Instance IDs to extract tests for (space separated)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )
    
    args = parser.parse_args()
    
    # Basic logging setup
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    
    # Check empty case works
    assert get_tests(ids=["nonexistent_id"]) == {}, "Should handle empty results"
    
    # Get tests
    results = get_tests(
        dataset=args.dataset,
        ids=args.target_ids,
        output_dir=args.output_dir,
    )
    
    # Print summary
    print(f"Extracted tests for {len(results)} instances")
    for instance_id, (f2p, p2p) in results.items():
        print(f"{instance_id}: {len(f2p)} F2P, {len(p2p)} P2P")
    
    # Test loading if we got results
    if results:
        test_id = next(iter(results.keys()))
        try:
            f2p, p2p = load_tests(test_id, args.output_dir)
            print(f"Successfully loaded tests for {test_id}")
            print(f"Sample F2P test: {f2p[0] if f2p else 'None'}")
        except Exception as e:
            print(f"Error loading tests: {e}")
