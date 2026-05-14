import json
from typing import Any, Callable, Dict

from probe_scripts.run_decomposition_probe import call_llm


def build_executor_prompt(task_package: Dict[str, Any]) -> str:
    """
    将动态 TaskPackage 拼成发给 LLM 的 prompt。
    任务包内部已经包含 instruction、inputs 和 expected_outputs，
    所以外层 prompt 不需要重复写太多规则。
    """
    return (
        "Execute the following task package strictly.\n"
        "The task package already contains the instruction, inputs, and expected output schema.\n\n"
        "Task Package:\n"
        f"{json.dumps(task_package, ensure_ascii=False, indent=2)}\n"
    )


def make_llm_executor(model_name: str) -> Callable[[Dict[str, Any]], str]:
    """
    构造一个执行层 LLM executor。

    输入：动态 TaskPackage
    输出：LLM 原始字符串回复

    注意：这里故意返回 raw_output 字符串，
    因为 dag_executor.py 会负责把它解析成 dict，
    并把 raw_agent_output 保存进 execution_trace。
    """
    def llm_executor(task_package: Dict[str, Any]) -> str:
        prompt = build_executor_prompt(task_package)
        raw_output = call_llm(prompt, model_name=model_name)
        return raw_output

    return llm_executor