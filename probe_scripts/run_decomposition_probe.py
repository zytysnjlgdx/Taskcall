import json
import random
import asyncio
from datetime import datetime
from mas_framework.llm.gpt_chat import achat
from pathlib import Path
from typing import List, Dict, Any
from prompts.instructions2 import ZERO_SHOT_DECOMPOSITION_INSTRUCTION
from openai import OpenAI
from dotenv import load_dotenv
import os
import pandas as pd
import glob
from typing import Optional
from execution.template_builder import build_template_record_from_probe_record


load_dotenv()

client = OpenAI(
    base_url=os.getenv("BASE_URL"),
    api_key=os.getenv("API_KEY"),

)

REPO_ROOT = Path(__file__).resolve().parents[1] # 上两级目录
DATA_DIR = REPO_ROOT / "datasets"
OUTPUT_DIR = REPO_ROOT / "outputs" / "decomposition_probe"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)  # parents=True 表示如果父目录不存在，就创建父目录 ；exist_ok=True 表示如果目录已存在，不报错
INTERMEDIATE_DIR = REPO_ROOT / "intermediate" / "decomposition_probe"
INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_OUTPUT_DIR = REPO_ROOT / "outputs" / "execution_templates"
TEMPLATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE_ERROR_DIR = REPO_ROOT / "outputs" / "execution_template_errors"
TEMPLATE_ERROR_DIR.mkdir(parents=True, exist_ok=True)



# def load_jsonl(path: Path) -> List[Dict[str, Any]]:
#     data = []
#     with open(path, "r", encoding="utf-8") as f:
#         for line in f:
#             data.append(json.loads(line))
#     return data

def load_data(path: Path) -> List[Dict[str, Any]]:
    if path.suffix == ".jsonl":
        data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))
        return data

    elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 防御性处理：保证返回的是 list
        if isinstance(data, list):
            return data
        else:
            raise ValueError(f"Expected a list in JSON file, got {type(data)} from {path}")

    else:
        raise ValueError(f"Unsupported file format: {path}")


def build_problem_text(dataset_name: str, item: Dict[str, Any]) -> str:
    if dataset_name == "gsm8k":
        return item["question"]

    elif dataset_name == "humaneval":
        return item["prompt"]

    elif dataset_name == "AQuA":
        return item["question"] + "\nChoices:\n" + "\n".join(item["options"])

    elif dataset_name == "MATH_40":
        return item["problem"]

    elif dataset_name == "MultiArith":
        return item["sQuestion"]

    elif dataset_name == "SVAMP":
        return item["Body"] + " " + item["Question"]
    elif dataset_name == "MMLU":
        return (
            f"{item['question']}\n"
            f"Option A: {item['A']}\n"
            f"Option B: {item['B']}\n"
            f"Option C: {item['C']}\n"
            f"Option D: {item['D']}"
        )
    else:
        raise ValueError(f"Unknown dataset: {dataset_name}")



def build_prompt(problem_text: str) -> str:
    prompt = ZERO_SHOT_DECOMPOSITION_INSTRUCTION + "\n\n"
    prompt += "Now process the following problem and output JSON only:\n\n"
    prompt += problem_text
    return prompt



def load_mmlu_data(split: str = "dev") -> List[Dict[str, Any]]:
    data_dir = DATA_DIR / "MMLU" / "data" / split
    csv_paths = sorted(glob.glob(str(data_dir / "*.csv")))

    if not csv_paths:
        raise ValueError(f"No csv files found in {data_dir}")

    all_data = []

    for path in csv_paths:
        df = pd.read_csv(path, header=None)

        for _, row in df.iterrows():
            item = {
                "question": row[0],
                "A": row[1],
                "B": row[2],
                "C": row[3],
                "D": row[4],
                "correct_answer": row[5],
                "subject": Path(path).stem
            }
            all_data.append(item)

    return all_data

def call_llm(prompt: str, model_name: str) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=2000,
    )
    return response.choices[0].message.content


def run_probe(
    dataset_name: str,
    dataset_path: Optional[Path],
    sample_size: int,
    model_name: str,
    random_seed: int = 42
) -> None:
    if dataset_name == "MMLU":
        data = load_mmlu_data(split="dev")
    else:
        data = load_data(dataset_path)
    rng = random.Random(random_seed)
    sampled = rng.sample(data, sample_size)

    mode = "zero_shot"
    timestamp = datetime.now().strftime("%Y_%m_%d_%H:%M")
    tag = f"{dataset_name}_{mode}_{timestamp}"

    out_path = OUTPUT_DIR / f"{tag}.jsonl"
    template_out_path = TEMPLATE_OUTPUT_DIR / f"{tag}_templates.jsonl"
    template_error_path = TEMPLATE_ERROR_DIR / f"{tag}_template_errors.jsonl"
    prompt_dir = INTERMEDIATE_DIR / tag
    prompt_dir.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as fout, \
         open(template_out_path, "w", encoding="utf-8") as template_fout, \
         open(template_error_path, "w", encoding="utf-8") as template_error_fout:
        for idx, item in enumerate(sampled):
            problem_text = build_problem_text(dataset_name, item)
            prompt = build_prompt(problem_text)

            prompt_file = prompt_dir / f"prompt_{idx}.json"
            with open(prompt_file, "w", encoding="utf-8") as pf:
                json.dump({"index": idx, "dataset": dataset_name, "mode": mode, "prompt": prompt}, pf, ensure_ascii=False, indent=2)

            try:
                raw_output = call_llm(prompt, model_name=model_name)
            except Exception as e:
                raw_output = f"ERROR: {repr(e)}"

            record = {
                "dataset": dataset_name,
                "mode": mode,
                "index": idx,
                "problem_text": problem_text,
                "raw_output": raw_output
            }
            # 1.保存原始 LLM 拆题输出
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")

            # 2. 立刻尝试构造静态 TaskTemplate
            try:
                template_record = build_template_record_from_probe_record(record)
                template_fout.write(json.dumps(template_record, ensure_ascii=False) + "\n")
            except Exception as e:
                error_record = {
                    "dataset": dataset_name,
                    "mode": mode,
                    "index": idx,
                    "problem_text": problem_text,
                    "raw_output": raw_output,
                    "error": repr(e)
                }
                template_error_fout.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                print(f"[Template build failed] dataset={dataset_name}, index={idx}, error={repr(e)}")

    print(f"Saved decomposition results to: {out_path}")
    print(f"Saved execution templates to: {template_out_path}")
    print(f"Saved template errors to: {template_error_path}")


if __name__ == "__main__":
    gsm8k_path = DATA_DIR / "gsm8k" / "gsm8k.jsonl"
    humaneval_path = DATA_DIR / "humaneval" / "humaneval-py.jsonl"
    AQuA_path = DATA_DIR / "AQuA" / "AQuA.jsonl"
    MultiArith_path = DATA_DIR / "MultiArith" / "MultiArith.json"
    SVAMP_path = DATA_DIR / "SVAMP" / "SVAMP.json"
    MATH_40_path = DATA_DIR / "MATH_40" / "math_40.jsonl"
    


    model_name = "gpt-4o"

    # run_probe("gsm8k", gsm8k_path, sample_size=5, model_name=model_name)
    # run_probe("gsm8k", gsm8k_path, sample_size=15, model_name=model_name)

    # run_probe("humaneval", humaneval_path, sample_size=5, model_name=model_name)
    # run_probe("humaneval", humaneval_path, sample_size=15, model_name=model_name)

    # run_probe("AQuA", AQuA_path, sample_size=15, model_name=model_name)
    # run_probe("MultiArith", MultiArith_path, sample_size=15, model_name=model_name)
    # run_probe("SVAMP", SVAMP_path, sample_size=15, model_name=model_name)
    # run_probe("MMLU", None, sample_size=5, model_name=model_name)
    run_probe("MATH_40", MATH_40_path, sample_size=40, model_name=model_name)