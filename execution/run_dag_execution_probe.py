import argparse
import json
import traceback
from pathlib import Path
from typing import Optional

from execution.dag_executor import run_dag_execution
from execution.llm_executor import make_llm_executor


REPO_ROOT = Path(__file__).resolve().parents[1]  

TEMPLATE_DIR = REPO_ROOT / "outputs" / "execution_templates"

EXECUTION_OUTPUT_DIR = REPO_ROOT / "outputs" / "dag_execution"
EXECUTION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_ERROR_DIR = REPO_ROOT / "outputs" / "dag_execution_errors"
EXECUTION_ERROR_DIR.mkdir(parents=True, exist_ok=True)


def default_output_paths(input_path: Path) -> tuple[Path, Path]:
    """
    根据输入的静态模板文件名，自动生成执行结果文件和错误文件路径。

    例如：
    outputs/execution_templates/gsm8k_zero_shot_xxx_templates.jsonl

    会生成：
    outputs/dag_execution/gsm8k_zero_shot_xxx_execution.jsonl
    outputs/dag_execution_errors/gsm8k_zero_shot_xxx_execution_errors.jsonl
    """
    stem = input_path.stem

    if stem.endswith("_templates"):
        stem = stem[: -len("_templates")]

    output_path = EXECUTION_OUTPUT_DIR / f"{stem}_execution.jsonl"
    error_path = EXECUTION_ERROR_DIR / f"{stem}_execution_errors.jsonl"

    return output_path, error_path


def run_execution_file(
    input_path: Path,
    model_name: str,
    output_path: Optional[Path] = None,
    error_path: Optional[Path] = None,
    limit: Optional[int] = None,
    strict_extra_fields: bool = True,
    include_trace: bool = True,
    fail_fast: bool = False
) -> None:
    """
    读取静态模板 jsonl 文件，逐条执行 DAG，并保存执行结果。

    输入文件每一行是一个 template_record，格式大致为：
    {
        "dataset": "...",
        "mode": "...",
        "index": 0,
        "problem_text": "...",
        "task_templates": [...]
    }

    每条 template_record 会被送入 run_dag_execution()。
    run_dag_execution() 内部会：
    1. 根据 depends_on 调度子问题；
    2. 调用 instantiate_task_package() 构造动态 TaskPackage；
    3. 调用 executor_fn 执行子问题；
    4. 保存 execution_results 和 execution_trace。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input template file not found: {input_path}")

    if output_path is None or error_path is None:
        default_output_path, default_error_path = default_output_paths(input_path)
        output_path = output_path or default_output_path
        error_path = error_path or default_error_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.parent.mkdir(parents=True, exist_ok=True)

    executor_fn = make_llm_executor(model_name=model_name)

    total = 0
    success = 0
    failed = 0

    with open(input_path, "r", encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout, \
         open(error_path, "w", encoding="utf-8") as ferr:

        for line_no, line in enumerate(fin, start=1):
            line = line.strip()

            if not line:
                continue

            if limit is not None and total >= limit:
                break

            total += 1

            try:
                template_record = json.loads(line)

                execution_record = run_dag_execution(
                    template_record=template_record,
                    executor_fn=executor_fn,
                    strict_extra_fields=strict_extra_fields,
                    include_trace=include_trace
                )

                fout.write(json.dumps(execution_record, ensure_ascii=False) + "\n")
                success += 1

                print(
                    f"[OK] line={line_no}, "
                    f"dataset={template_record.get('dataset')}, "
                    f"index={template_record.get('index')}"
                )

            except Exception as e:
                failed += 1

                error_record = {
                    "line_no": line_no,
                    "error": repr(e),
                    "traceback": traceback.format_exc(),
                    "raw_template_record": line
                }

                try:
                    template_record = json.loads(line)
                    error_record.update({
                        "dataset": template_record.get("dataset"),
                        "mode": template_record.get("mode"),
                        "index": template_record.get("index"),
                        "problem_text": template_record.get("problem_text"),
                        "template_record": template_record
                    })
                except Exception:
                    pass

                ferr.write(json.dumps(error_record, ensure_ascii=False) + "\n")

                print(f"[FAILED] line={line_no}, error={repr(e)}")

                if fail_fast:
                    raise

    print("=" * 60)
    print(f"Input templates: {input_path}")
    print(f"Saved DAG execution results to: {output_path}")
    print(f"Saved DAG execution errors to: {error_path}")
    print(f"Total: {total}, Success: {success}, Failed: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DAG execution from static TaskTemplate records."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to an execution_templates jsonl file."
    )

    parser.add_argument(
        "--model-name",
        default="gpt-4o",
        help="LLM model name used by the execution agent."
    )

    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to save DAG execution results."
    )

    parser.add_argument(
        "--error-output",
        default=None,
        help="Optional path to save failed DAG execution records."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only execute the first N template records. Useful for debugging."
    )

    parser.add_argument(
        "--allow-extra-fields",
        action="store_true",
        help="Allow agent outputs to contain fields not defined in expected_outputs."
    )

    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="Do not save execution_trace."
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when one record fails."
    )

    args = parser.parse_args()

    run_execution_file(
        input_path=Path(args.input),
        model_name=args.model_name,
        output_path=Path(args.output) if args.output else None,
        error_path=Path(args.error_output) if args.error_output else None,
        limit=args.limit,
        strict_extra_fields=not args.allow_extra_fields,
        include_trace=not args.no_trace,
        fail_fast=args.fail_fast
    )


if __name__ == "__main__":
    main()