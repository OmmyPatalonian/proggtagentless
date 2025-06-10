# Transitioning to Ground Truth Tests

## Overview

`run_gt_tests.py` is a specialized version of `run_reproduction_tests.py` that focuses solely on using ground truth tests from SWE-bench instead of synthetic reproduction tests. This file provides a cleaner interface for working with ground truth tests and simplifies the usage.

## Key Changes

- Removed the dual-purpose nature of `run_reproduction_tests.py`
- Removed the `--use_ground_truth` flag since this file is exclusively for ground truth tests
- Simplified the command-line interface
- Improved error messages and documentation
- Maintained compatibility with the rest of the Agentless system

## Migration Steps

1. Replace any calls to `python -m agentless.test.run_reproduction_tests --use_ground_truth` with `python -m agentless.test.run_gt_tests`

2. Remove the `--use_ground_truth` flag from your commands

3. Keep all other arguments the same

## Example

**Old command:**
```bash
python -m agentless.test.run_reproduction_tests \
  --run_id ground_truth_validation \
  --predictions_path results/ground_truth/repair/output_0_processed.jsonl \
  --use_ground_truth \
  --ground_truth_dir ground_truth_tests
```

**New command:**
```bash
python -m agentless.test.run_gt_tests \
  --run_id ground_truth_validation \
  --predictions_path results/ground_truth/repair/output_0_processed.jsonl \
  --ground_truth_dir ground_truth_tests
```

## Removal of run_reproduction_tests.py

After transitioning to `run_gt_tests.py`, you can safely remove `run_reproduction_tests.py` if you exclusively use ground truth tests. If you still need to use synthetic reproduction tests, keep both files.
