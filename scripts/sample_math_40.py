import json
import random
from pathlib import Path

random.seed(42)

MATH_DIR = Path("datasets/MATH")
SOURCE_SPLIT = "test"
OUTPUT_DIR = Path("datasets/MATH_40")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_TYPES = {
    "algebra": 8,
    "intermediate_algebra": 8,
    "number_theory": 8,
    "counting_and_probability": 8,
    "geometry": 8,
}

TARGET_LEVELS = {"Level 3", "Level 4", "Level 5"}

sampled_items = []

for math_type, sample_num in TARGET_TYPES.items():
    type_dir = MATH_DIR / SOURCE_SPLIT / math_type

    candidates = []

    for file_path in type_dir.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            item = json.load(f)

        if item.get("level") in TARGET_LEVELS:
            item["source_file"] = str(file_path)
            item["math_type"] = math_type
            candidates.append(item)

    print(math_type, "candidates:", len(candidates))

    if len(candidates) < sample_num:
        raise ValueError(
            f"{math_type} only has {len(candidates)} candidates, "
            f"but needs {sample_num}."
        )

    selected = random.sample(candidates, sample_num)
    sampled_items.extend(selected)

output_path = OUTPUT_DIR / "math_40.jsonl"

with open(output_path, "w", encoding="utf-8") as f:
    for idx, item in enumerate(sampled_items):
        record = {
            "dataset": "MATH_40",
            "index": idx,
            "math_type": item.get("math_type"),
            "level": item.get("level"),
            "problem": item.get("problem"),
            "solution": item.get("solution"),
            "source_file": item.get("source_file"),
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"Saved {len(sampled_items)} examples to {output_path}")
