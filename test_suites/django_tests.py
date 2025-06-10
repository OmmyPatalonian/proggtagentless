import json
from datasets import load_dataset

# Step 1: Load the SWE-bench_Lite dataset from Hugging Face
dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")

# Step 2: Initialize a list to hold the formatted instance_ids
django_test_cases = []

# Step 3: Filter for entries where the repo is 'django/django'
for entry in dataset:
    if entry.get('repo') == 'django/django':
        # Extract and format the instance_id
        instance_id = entry.get('instance_id')
        if instance_id:
            django_test_cases.append(instance_id)

# Step 4: Write the formatted instance_ids to a text file
output_file_path = "django_all.txt"
with open(output_file_path, 'w') as output_file:
    for test_case in django_test_cases:
        output_file.write(f'{test_case}\n')

print(f"Extracted {len(django_test_cases)} Django test cases.")
print(f"The results have been saved to {output_file_path}.")