"""
Utility to load ground truth tests from SWE-bench dataset.
"""
import json
import os
from typing import Dict, List, Tuple

from datasets import load_dataset


def extract_ground_truth_tests(
    dataset_name: str = "princeton-nlp/SWE-bench_Lite",
    target_ids: List[str] = None,
    output_dir: str = "ground_truth_tests",
) -> Dict[str, Tuple[List[str], List[str]]]:
    """
    Extract ground truth F2P and P2P tests from SWE-bench dataset.
    
    Args:
        dataset_name: Name of the dataset to load
        target_ids: List of instance IDs to extract tests for. If None, extract for all instances.
        output_dir: Directory to save the test lists
    
    Returns:
        Dictionary mapping instance_id to (f2p_tests, p2p_tests)
    """
    # Load the dataset
    ds = load_dataset(dataset_name, split="test")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    results = {}
    
    # For each instance in the dataset
    for instance in ds:
        instance_id = instance["instance_id"]
        
        # Skip if not in target_ids
        if target_ids and instance_id not in target_ids:
            continue
        
        # Extract F2P and P2P tests
        if isinstance(instance["FAIL_TO_PASS"], str):
            f2p_tests = json.loads(instance["FAIL_TO_PASS"])
        else:
            f2p_tests = instance["FAIL_TO_PASS"]
            
        if isinstance(instance["PASS_TO_PASS"], str):
            p2p_tests = json.loads(instance["PASS_TO_PASS"])
        else:
            p2p_tests = instance["PASS_TO_PASS"]
        
        # Save to output files
        instance_dir = os.path.join(output_dir, instance_id)
        os.makedirs(instance_dir, exist_ok=True)
        
        f2p_path = os.path.join(instance_dir, "f2p.txt")
        with open(f2p_path, "w") as f:
            for test in f2p_tests:
                f.write(f"{test}\n")
                
        p2p_path = os.path.join(instance_dir, "p2p.txt")
        with open(p2p_path, "w") as f:
            for test in p2p_tests:
                f.write(f"{test}\n")
        
        results[instance_id] = (f2p_tests, p2p_tests)
    
    return results


def load_ground_truth_tests(
    instance_id: str, 
    test_dir: str = "ground_truth_tests"
) -> Tuple[List[str], List[str]]:
    """
    Load ground truth F2P and P2P tests for a specific instance.
    
    Args:
        instance_id: Instance ID to load tests for
        test_dir: Directory containing the test lists
    
    Returns:
        Tuple of (f2p_tests, p2p_tests)
    """
    instance_dir = os.path.join(test_dir, instance_id)
    
    f2p_path = os.path.join(instance_dir, "f2p.txt")
    with open(f2p_path, "r") as f:
        f2p_tests = [line.strip() for line in f.readlines()]
        
    p2p_path = os.path.join(instance_dir, "p2p.txt")
    with open(p2p_path, "r") as f:
        p2p_tests = [line.strip() for line in f.readlines()]
    
    return f2p_tests, p2p_tests


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=str,
        default="princeton-nlp/SWE-bench_Lite",
        choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"],
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
    
    args = parser.parse_args()
    
    # Extract ground truth tests
    results = extract_ground_truth_tests(
        dataset_name=args.dataset,
        target_ids=args.target_ids,
        output_dir=args.output_dir,
    )
    
    # Print summary
    print(f"Extracted ground truth tests for {len(results)} instances")
    for instance_id, (f2p, p2p) in results.items():
        print(f"{instance_id}: {len(f2p)} F2P tests, {len(p2p)} P2P tests")
