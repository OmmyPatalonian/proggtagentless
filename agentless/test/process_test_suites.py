"""
Process Django test suites and map them to SWE-bench instance IDs.
"""
import argparse
import json
import os
import re
from pathlib import Path

from datasets import load_dataset


def extract_instance_ids_from_dataset(dataset_name="princeton-nlp/SWE-bench_Lite"):
    """
    Extract Django instance IDs from the SWE-bench dataset.
    
    Args:
        dataset_name: Name of the dataset to load
        
    Returns:
        List of Django instance IDs
    """
    ds = load_dataset(dataset_name, split="test")
    django_instances = [
        instance["instance_id"] for instance in ds 
        if instance["repo"] == "django/django"
    ]
    return django_instances


def load_test_suite(test_suite_file):
    """
    Load test suite from file.
    
    Args:
        test_suite_file: Path to test suite file
        
    Returns:
        List of tests in the suite
    """
    with open(test_suite_file, "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def extract_instance_id_from_filename(filename):
    """
    Extract instance ID from filename.
    
    Args:
        filename: Filename to extract instance ID from
        
    Returns:
        Instance ID if found, None otherwise
    """
    match = re.search(r'django__django-(\d+)', filename)
    if match:
        return f"django__django-{match.group(1)}"
    return None


def process_test_suites(test_suites_dir, output_dir, dataset_name):
    """
    Process test suites and create F2P and P2P files.
    
    Args:
        test_suites_dir: Directory containing test suites
        output_dir: Directory to save the processed files
        dataset_name: Name of the dataset to load
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get Django instance IDs from the dataset
    django_instances = extract_instance_ids_from_dataset(dataset_name)
    print(f"Found {len(django_instances)} Django instances in the dataset")
    
    # Process each test suite file
    test_suite_files = list(Path(test_suites_dir).glob("*.txt"))
    print(f"Found {len(test_suite_files)} test suite files")
    
    for test_suite_file in test_suite_files:
        # Extract instance ID from filename
        instance_id = extract_instance_id_from_filename(test_suite_file.name)
        
        # Skip if instance ID not found or not in dataset
        if not instance_id or instance_id not in django_instances:
            print(f"Skipping {test_suite_file.name}: Instance ID not found or not in dataset")
            continue
        
        print(f"Processing {test_suite_file.name} for {instance_id}")
        
        # Load test suite
        tests = load_test_suite(test_suite_file)
        
        # Create instance directory
        instance_dir = os.path.join(output_dir, instance_id)
        os.makedirs(instance_dir, exist_ok=True)
        
        # Save as F2P tests
        f2p_path = os.path.join(instance_dir, "f2p.txt")
        with open(f2p_path, "w") as f:
            for test in tests:
                f.write(f"{test}\n")
                
        # For now, P2P tests are empty (will be populated by regression test selection)
        p2p_path = os.path.join(instance_dir, "p2p.txt")
        with open(p2p_path, "w") as f:
            f.write("")
            
        print(f"Created F2P file with {len(tests)} tests for {instance_id}")
    
    print(f"Processed test suites saved to {output_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test_suites_dir",
        type=str,
        default="test_suites",
        help="Directory containing test suites",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="ground_truth_tests",
        help="Directory to save the processed files",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="princeton-nlp/SWE-bench_Lite",
        choices=["princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"],
        help="Dataset to load instance IDs from",
    )
    
    args = parser.parse_args()
    
    process_test_suites(args.test_suites_dir, args.output_dir, args.dataset)


if __name__ == "__main__":
    main()
