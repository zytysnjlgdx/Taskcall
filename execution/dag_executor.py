import json
from typing import Any, Callable, Dict, List, Optional, Set

from execution.package_instantiator import instantiate_task_package

# executor_fn 的类型：
# 输入：一个动态 TaskPackage
# 输出：agent 执行后的原始结果，可以是 dict，也可以是 JSON 字符串
ExecutorFn = Callable[[Dict[str, Any]], Any]

def index_task_templates(task_templates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    将 task_templates 列表转换成按 subproblem_id 索引的字典。

    例如：
    [
        {"subproblem_id": "q1", "goal": "..."},
        {"subproblem_id": "q2", "goal": "..."}
    ]

    会变成：
    {
        "q1": {"subproblem_id": "q1", "goal": "..."},
        "q2": {"subproblem_id": "q2", "goal": "..."}
    }

    这样后续代码就可以通过 template_index["q1"] 快速找到某个子问题模板。

    同时，这个函数也会检查：
    1. 每个模板是否都有 subproblem_id；
    2. subproblem_id 是否重复。
    """
    template_index: Dict[str, Dict[str, Any]] = {}

    for template in task_templates:
        subproblem_id = template.get("subproblem_id")

        if not subproblem_id:
            raise ValueError(f"某个任务模板缺少 subproblem_id: {template}")

        if subproblem_id in template_index:
            raise ValueError(f"task_templates 中存在重复的 subproblem_id: {subproblem_id}")

        template_index[subproblem_id] = template

    return template_index


def validate_task_templates(task_templates: List[Dict[str, Any]]) -> None:
    """
    在 DAG 执行之前，对静态 TaskTemplate 做基础检查。

    这里主要检查：
    1. task_templates 必须是非空列表；
    2. 每个模板必须有唯一的 subproblem_id；
    3. depends_on 中引用的子问题必须真实存在；
    4. 每个模板必须有 expected_outputs。
    """
    if not isinstance(task_templates, list) or not task_templates:
        raise ValueError("task_templates 必须是非空列表")

    template_index = index_task_templates(task_templates)

    for template in task_templates:
        subproblem_id = template["subproblem_id"]

        if "expected_outputs" not in template or not isinstance(template["expected_outputs"], list):
            raise ValueError(f"TaskTemplate {subproblem_id} 缺少 expected_outputs 列表")

        for dep_id in template.get("depends_on", []):
            if dep_id not in template_index:
                raise ValueError(
                    f"TaskTemplate {subproblem_id} 依赖了不存在的子问题 {dep_id}"
                )


def get_ready_templates(
    task_templates: List[Dict[str, Any]],
    completed: Set[str]
) -> List[Dict[str, Any]]:
    """
    找出当前已经可以执行的静态模板。

    一个模板可以执行，需要满足两个条件：
    1. 当前子问题还没有执行完成；
    2. depends_on 中的所有上游子问题都已经执行完成。
    """
    ready_templates = []

    for template in task_templates:
        subproblem_id = template["subproblem_id"]

        # 已经执行过的子问题，不再重复执行
        if subproblem_id in completed:
            continue

        depends_on = template.get("depends_on", [])

        # 只有所有依赖节点都完成后，当前节点才可以执行
        if all(dep_id in completed for dep_id in depends_on):
            ready_templates.append(template)

    return ready_templates


def parse_agent_output(agent_output: Any) -> Dict[str, Any]:
    """
    将执行层 agent 的输出统一转换成 Python dict。

    executor_fn 可能返回：
    1. dict，例如 {"kim_amount": 750}
    2. 纯 JSON 字符串，例如 '{"kim_amount": 750}'
    3. 被 ```json ... ``` 包裹的 JSON 字符串

    这个函数会尽量把它们统一转换成 dict。
    """
    if isinstance(agent_output, dict):
        return agent_output

    if isinstance(agent_output, str):
        text = agent_output.strip()

        if not text:
            raise ValueError("agent 输出为空，无法解析为 JSON")

        # 兼容 LLM 返回 ```json ... ``` 或 ``` ... ``` 的情况
        if text.startswith("```"):
            lines = text.splitlines()

            # 去掉第一行 ```json 或 ```
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]

            # 去掉最后一行 ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "agent 输出不是合法 JSON。"
                f"原始输出前 500 个字符为: {agent_output[:500]!r}。"
                f"清理后的输出前 500 个字符为: {text[:500]!r}"
            ) from e

    raise TypeError(
        f"agent 输出必须是 dict 或 JSON 字符串，但实际是 {type(agent_output).__name__}"
    )


def validate_agent_output(
    agent_output: Dict[str, Any],
    expected_outputs: List[Dict[str, Any]],
    strict_extra_fields: bool = True
) -> None:
    """
    检查 agent 输出是否符合当前子问题的 expected_outputs 要求。

    基础规则：
    1. agent_output 必须是 dict；
    2. expected_outputs 中声明的每个 field，都必须出现在 agent_output 中；
    3. 如果 strict_extra_fields=True，则 agent_output 不能包含额外字段。
    """
    if not isinstance(agent_output, dict):
        raise TypeError(f"agent_output 必须是 dict，但实际是 {type(agent_output).__name__}")

    expected_fields = [output["field"] for output in expected_outputs]
    expected_field_set = set(expected_fields)
    actual_field_set = set(agent_output.keys())

    # 检查是否缺少 expected_outputs 中要求的字段
    missing_fields = expected_field_set - actual_field_set
    if missing_fields:
        raise ValueError(f"agent 输出缺少必要字段: {sorted(missing_fields)}")

    # 检查是否输出了 expected_outputs 之外的额外字段
    extra_fields = actual_field_set - expected_field_set
    if strict_extra_fields and extra_fields:
        raise ValueError(f"agent 输出包含额外字段: {sorted(extra_fields)}")


def call_executor_agent(task_package: Dict[str, Any]) -> Any:
    """
    执行层 agent 的占位函数。

    后面这里要替换成真正的 LLM/agent 调用。
    当前故意抛出错误，防止你忘记传入真实 executor_fn 时误以为已经执行成功。
    """
    raise NotImplementedError(
        "call_executor_agent 目前只是占位函数。"
        "请在 run_dag_execution(...) 中传入真正的 executor_fn。"
    )


def run_dag_execution(
    template_record: Dict[str, Any],
    executor_fn: Optional[ExecutorFn] = None,
    strict_extra_fields: bool = True,
    include_trace: bool = True
) -> Dict[str, Any]:
    """
    按照 depends_on 定义的 DAG 顺序，执行一整道题的所有子问题。

    输入 template_record 的格式大致为：
    {
        "dataset": "...",
        "mode": "...",
        "index": 0,
        "problem_text": "...",
        "task_templates": [
            {... q1 的静态 TaskTemplate ...},
            {... q2 的静态 TaskTemplate ...}
        ]
    }

    执行流程：
    1. 找到当前所有依赖已经满足的子问题模板；
    2. 将静态 TaskTemplate 实例化成动态 TaskPackage；
    3. 把动态 TaskPackage 发送给 executor_fn；
    4. 检查 agent 返回的 JSON 字段是否符合 expected_outputs；
    5. 将结果保存到 execution_results；
    6. 重复以上过程，直到所有子问题都执行完成。
    """
    task_templates = template_record.get("task_templates")

    # 执行前先检查静态模板结构是否基本有效
    validate_task_templates(task_templates)

    # 如果外部没有传 executor_fn，就使用占位函数
    # 占位函数会直接报错，提醒你还没有接真实执行层
    executor = executor_fn or call_executor_agent

    # 保存每个子问题的执行结果
    # 格式：
    # {
    #   "q1": {"kim_amount": 750},
    #   "q2": {"maryam_amount": 700}
    # }
    execution_results: Dict[str, Dict[str, Any]] = {}

    # 保存已经执行完成的子问题 id
    completed: Set[str] = set()

    # 可选：保存执行过程轨迹，方便 debug
    execution_trace: List[Dict[str, Any]] = []

    while len(completed) < len(task_templates):
        # 根据 DAG 找出当前可以执行的子问题
        ready_templates = get_ready_templates(task_templates, completed)

        if not ready_templates:
            raise RuntimeError(
                "当前没有任何可执行的子问题。"
                "这通常说明 DAG 有环，或者存在无法满足的依赖。"
            )

        # 第一版先顺序执行 ready 子问题，不做并行
        for template in ready_templates:
            subproblem_id = template["subproblem_id"]

            # 静态模板 + 当前已有 execution_results
            # → 动态 TaskPackage
            task_package = instantiate_task_package(
                task_template=template,
                execution_results=execution_results
            )

            raw_agent_output = None

            try:
                # 调用执行层 agent，得到 LLM 原始回复
                raw_agent_output = executor(task_package)

                # 将 agent 输出统一解析成 dict
                # 如果 LLM 输出不是合法 JSON，这里会抛出异常
                agent_output = parse_agent_output(raw_agent_output)

                # 检查 agent 输出字段是否符合 expected_outputs
                validate_agent_output(
                    agent_output=agent_output,
                    expected_outputs=task_package.get("expected_outputs", []),
                    strict_extra_fields=strict_extra_fields
                )

            except Exception as e:
                if include_trace:
                    execution_trace.append({
                        "subproblem_id": subproblem_id,
                        "task_package": task_package,
                        "raw_agent_output": raw_agent_output,
                        "error": repr(e)
                    })

                raise RuntimeError(
                    f"DAG execution failed at subproblem {subproblem_id}. "
                    f"raw_agent_output={raw_agent_output!r}"
                ) from e


            # 将当前子问题的输出写入 execution_results
            execution_results[subproblem_id] = agent_output

            # 标记当前子问题已经完成
            completed.add(subproblem_id)

            # 记录执行轨迹，方便你之后查看每个子问题拿到了什么任务包、输出了什么
            if include_trace:
                execution_trace.append({
                    "subproblem_id": subproblem_id,
                    "task_package": task_package,
                    "raw_agent_output": raw_agent_output,  # LLM 原始返回内容，通常是字符串
                    "agent_output": agent_output  # 经过 parse_agent_output() 解析后的 Python dict
                })

    # 优先使用 template_record 中声明的 final_answer_subproblem_id
    # 这个字段来自拆题阶段，用来标明哪个子问题的输出才是原题最终答案
    final_subproblem_id = template_record.get("final_answer_subproblem_id")

    # 兼容旧模板：如果旧模板没有 final_answer_subproblem_id，就退回到最后一个子问题
    if not final_subproblem_id:
        final_subproblem_id = task_templates[-1]["subproblem_id"]

    if final_subproblem_id not in execution_results:
        raise ValueError(
            f"final_answer_subproblem_id {final_subproblem_id!r} "
            f"not found in execution_results"
        )

    execution_record = {
        "dataset": template_record.get("dataset"),
        "mode": template_record.get("mode"),
        "index": template_record.get("index"),
        "problem_text": template_record.get("problem_text"),
        "final_answer_subproblem_id": template_record.get("final_answer_subproblem_id"),
        "execution_results": execution_results,
        "final_subproblem_id": final_subproblem_id,
        "final_output": execution_results.get(final_subproblem_id)
    }

    if include_trace:
        execution_record["execution_trace"] = execution_trace

    return execution_record