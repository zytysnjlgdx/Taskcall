import json
from pathlib import Path
from datasets import load_dataset

OUT_DIR = Path("datasets/MATH")

SUBJECTS = [
    "algebra",
    "counting_and_probability",
    "geometry",
    "intermediate_algebra",
    "number_theory",
    "prealgebra",
    "precalculus",
]

for subject in SUBJECTS:
    print(f"Downloading {subject}...")

    ds = load_dataset("EleutherAI/hendrycks_math", subject)

    for split in ds.keys():  # usually train / test
        split_dir = OUT_DIR / split / subject
        split_dir.mkdir(parents=True, exist_ok=True)

        for idx, item in enumerate(ds[split]):
            item = dict(item)
            item["math_type"] = subject
            item["source_dataset"] = "EleutherAI/hendrycks_math"

            out_path = split_dir / f"{idx}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)

print(f"Done. Saved to {OUT_DIR}")
