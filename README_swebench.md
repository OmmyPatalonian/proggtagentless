# Agentless experiments on SWE-Bench

<p align="center">
    <big><a href="#-setup">🐈Setup</a></big> |
    <big><a href="#-localization">🙀Localization</a></big> | 
    <big><a href="#-repair">😼Repair</a></big> |
    <big><a href="#-patch-validation-and-selection">😸Patch Validation and Selection</a></big> |
    <big><a href="#-cost">💰Cost</a></big>
</p>

This document shows how to generate patches on SWE-bench using Agentless. We support both [SWE-Bench Lite](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite) and [SWE-Bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified).

## 🐈 Setup

```shell
# Clone and setup
git clone https://github.com/OpenAutoCoder/Agentless.git
cd Agentless
conda create -n agentless python=3.11 
conda activate agentless
pip install -r requirements.txt
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Set API key
export OPENAI_API_KEY={key_here}

# Create results folder
mkdir results
```

<details>
<summary>📌 Helpful Tips</summary>

- Use `--dataset=princeton-nlp/SWE-bench_Verified` to specify the benchmark
- Download [preprocessed data](https://github.com/OpenAutoCoder/Agentless/releases/tag/v1.5.0) to save time
- Use `--target_id=django__django-10914` to target a specific bug
- Control parallelism with `--num_threads`

</details>

## 🙀 Localization 

Agentless uses a 3-stage localization process to find where to make edits:

<details>
<summary>1. Localize to suspicious files</summary>

```shell
# Generate LLM-predicted suspicious files
python agentless/fl/localize.py --file_level \
                               --output_folder results/swe-bench-lite/file_level \
                               --num_threads 10 \
                               --skip_existing 

# Identify irrelevant folders to exclude
python agentless/fl/localize.py --file_level \
                               --irrelevant \
                               --output_folder results/swe-bench-lite/file_level_irrelevant \
                               --num_threads 10 \
                               --skip_existing 

# Perform embedding-based retrieval
python agentless/fl/retrieve.py --index_type simple \
                               --filter_type given_files \
                               --filter_file results/swe-bench-lite/file_level_irrelevant/loc_outputs.jsonl \
                               --output_folder results/swe-bench-lite/retrievel_embedding \
                               --persist_dir embedding/swe-bench_simple \
                               --num_threads 10 

# Merge results
python agentless/fl/combine.py  --retrieval_loc_file results/swe-bench-lite/retrievel_embedding/retrieve_locs.jsonl \
                               --model_loc_file results/swe-bench-lite/file_level/loc_outputs.jsonl \
                               --top_n 3 \
                               --output_folder results/swe-bench-lite/file_level_combined 
```
</details>

<details>
<summary>2. Localize to related elements</summary>

```shell
python agentless/fl/localize.py --related_level \
                               --output_folder results/swe-bench-lite/related_elements \
                               --top_n 3 \
                               --compress_assign \
                               --compress \
                               --start_file results/swe-bench-lite/file_level_combined/combined_locs.jsonl \
                               --num_threads 10 \
                               --skip_existing 
```
</details>

<details>
<summary>3. Localize to edit locations</summary>

```shell
# Generate edit locations
python agentless/fl/localize.py --fine_grain_line_level \
                               --output_folder results/swe-bench-lite/edit_location_samples \
                               --top_n 3 \
                               --compress \
                               --temperature 0.8 \
                               --num_samples 4 \
                               --start_file results/swe-bench-lite/related_elements/loc_outputs.jsonl \
                               --num_threads 10 \
                               --skip_existing 

# Split into individual sets
python agentless/fl/localize.py --merge \
                               --output_folder results/swe-bench-lite/edit_location_individual \
                               --top_n 3 \
                               --num_samples 4 \
                               --start_file results/swe-bench-lite/edit_location_samples/loc_outputs.jsonl 
```
</details>

## 😼 Repair

Generate patches using the localized edit locations:

```shell
# Generate patches for the first set of edit locations
python agentless/repair/repair.py --loc_file results/swe-bench-lite/edit_location_individual/loc_merged_0-0_outputs.jsonl \
                                 --output_folder results/swe-bench-lite/repair_sample_1 \
                                 --loc_interval \
                                 --top_n=3 \
                                 --context_window=10 \
                                 --max_samples 10 \
                                 --cot \
                                 --diff_format \
                                 --use_ground_truth \
                                 --gen_and_process \
                                 --num_threads 2 
```

<details>
<summary>For all edit location sets (generates 40 total samples)</summary>

```shell
for i in {1..3}; do
    python agentless/repair/repair.py --loc_file results/swe-bench-lite/edit_location_individual/loc_merged_${i}-${i}_outputs.jsonl \
                                     --output_folder results/swe-bench-lite/repair_sample_$((i+1)) \
                                     --loc_interval \
                                     --top_n=3 \
                                     --context_window=10 \
                                     --max_samples 10  \
                                     --cot \
                                     --diff_format \
                                     --use_ground_truth \
                                     --gen_and_process \
                                     --num_threads 2 
done
```
</details>

The `--use_ground_truth` flag signals to the LLM that ground truth tests will be used for evaluation.

## 😸 Patch Validation and Selection 

### Ground Truth Tests (Recommended)

Use actual SWE-bench tests for better patch validation:

```shell
# Extract ground truth tests
python -m agentless.util.bench_loader --dataset princeton-nlp/SWE-bench_Lite \
                                     --output_dir ground_truth_tests

# Run tests on patches
python -m agentless.test.run_gt_tests --run_id ground_truth_validation \
                                     --predictions_path results/swe-bench-lite/repair_sample_1/output_0_processed.jsonl \
                                     --ground_truth_dir ground_truth_tests

# Rerank based on ground truth results
python -m agentless.repair.rerank_with_ground_truth \
    --patch_folder results/swe-bench-lite/repair_sample_1/,results/swe-bench-lite/repair_sample_2/ \
    --num_samples 20 \
    --output_folder results/swe-bench-lite/reranked_gt
```

This reranking prioritizes patches that pass F2P tests first, then P2P tests, and finally by model score.

### Traditional Test-Based Validation

<details>
<summary>Alternatively, use regression tests and synthetic reproduction tests</summary>

#### Regression test selection

```shell
# Get passing tests from original codebase
python agentless/test/run_regression_tests.py --run_id generate_regression_tests \
                                             --output_file results/swe-bench-lite/passing_tests.jsonl 

# Filter tests
python agentless/test/select_regression_tests.py --passing_tests results/swe-bench-lite/passing_tests.jsonl \
                                                --output_folder results/swe-bench-lite/select_regression 

# Run regression tests on patches
folder=results/swe-bench-lite/repair_sample_1
for num in {0..9..1}; do
    run_id_prefix=$(basename $folder); 
    python agentless/test/run_regression_tests.py --regression_tests results/swe-bench-lite/select_regression/output.jsonl \
                                                 --predictions_path="${folder}/output_${num}_processed.jsonl" \
                                                 --run_id="${run_id_prefix}_regression_${num}" --num_workers 10;
done
```

#### Reproduction test generation

```shell
# Generate reproduction tests
python agentless/test/generate_reproduction_tests.py --max_samples 40 \
                                                    --output_folder results/swe-bench-lite/reproduction_test_samples \
                                                    --num_threads 10 

# Verify tests (in parallel)
for st in {0..36..4}; do   
    en=$((st + 3));   
    echo "Processing ${st} to ${en}";        
    for num in $(seq $st $en); do     
        echo "Processing ${num}";
        python agentless/test/run_reproduction_tests.py --run_id="reproduction_test_generation_filter_sample_${num}" \
                                                        --test_jsonl="results/swe-bench-lite/reproduction_test_samples/output_${num}_processed_reproduction_test.jsonl" \
                                                        --num_workers 6 \
                                                        --testing;
    done
done

# Select tests
python agentless/test/generate_reproduction_tests.py --max_samples 40 \
                                                    --output_folder results/swe-bench-lite/reproduction_test_samples \
                                                    --output_file reproduction_tests.jsonl \
                                                    --select

# Run reproduction tests on patches
folder=results/swe-bench-lite/repair_sample_1
for num in {0..9..1}; do
    run_id_prefix=$(basename $folder); 
    python agentless/test/run_reproduction_tests.py --test_jsonl results/swe-bench-lite/reproduction_test_samples/reproduction_tests.jsonl \
                                                   --predictions_path="${folder}/output_${num}_processed.jsonl" \
                                                   --run_id="${run_id_prefix}_reproduction_${num}" --num_workers 10;
done
```

#### Traditional reranking

```shell
python agentless/repair/rerank.py --patch_folder results/swe-bench-lite/repair_sample_1/,results/swe-bench-lite/repair_sample_2/,results/swe-bench-lite/repair_sample_3/,results/swe-bench-lite/repair_sample_4/ \
                                 --num_samples 40 \
                                 --deduplicate \
                                 --regression \
                                 --reproduction
```

#### Combined approach

```shell
python agentless/repair/rerank.py --patch_folder results/swe-bench-lite/repair_sample_1/,results/swe-bench-lite/repair_sample_2/,results/swe-bench-lite/repair_sample_3/,results/swe-bench-lite/repair_sample_4/ \
                                 --num_samples 40 \
                                 --deduplicate \
                                 --regression \
                                 --reproduction \
                                 --ground_truth \
                                 --prioritize_f2p \
                                 --prioritize_p2p
```
</details>

## 💰 Cost 

```shell
python dev/util/cost.py --output_file results/swe-bench-lite/file_level/output.jsonl 
```

Add `--embedding_cost` to compute embedding costs.
