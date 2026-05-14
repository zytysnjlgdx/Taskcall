import json
from copy import deepcopy
from typing import Any, Dict, List, Set


INSTRUCTION = (
    "Solve only the current subproblem, not the entire original problem. "
    "Use upstream_inputs and local_evidence as the main evidence; background_question_text is only supplementary context. "
    "Return exactly one JSON object whose field names strictly match expected_outputs. "
    "Each field value must directly contain the required value, judgement, code, or result. "
    "For example, if expected_outputs defines the field \"kim_amount\", the output must be like {\"kim_amount\": 750}. "
    "If an expected output type is not \"code\", do not output code or a complete function implementation; use natural language or structured steps instead. "
    "If an expected output type is \"code\", put the complete code as the string value of the corresponding JSON field, inside a Python fenced code block. "
    "Do not add explanations, headings, or extra fields outside the JSON object."
)

def strip_markdown_fence(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


def parse_llm_json(raw_output: str) -> Dict[str, Any]:
    """
    将分解 LLM 返回的 raw_output 字符串解析为 Python 字典。
    在正常流程中，raw_output 是一个 JSON 格式的字符串。

    对数学数据中的 LaTeX 反斜杠做兜底修复：
    例如 \sqrt, \frac, \ldots 在 JSON 字符串里必须写成 \\sqrt, \\frac, \\ldots。
    """
    if not isinstance(raw_output, str):
        raise TypeError(f"raw_output must be str, got {type(raw_output).__name__}")

    text = strip_markdown_fence(raw_output)

    if text.startswith("ERROR:"):
        raise ValueError(text[:300])

    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        fixed_text = escape_invalid_json_backslashes(text)

        try:
            return json.loads(fixed_text)
        except json.JSONDecodeError:
            raise first_error

def escape_invalid_json_backslashes(text: str) -> str:
    r"""
    Escape backslashes that are illegal in JSON strings.

    JSON only allows these escapes:
        \", \\, \/, \b, \f, \n, \r, \t, \uXXXX

    LaTeX commands such as \sqrt, \frac, \ldots, \left are not valid JSON escapes,
    so they must be converted to \\sqrt, \\frac, \\ldots, \\left.
    """
    result = []
    i = 0

    while i < len(text):
        char = text[i]

        if char != "\\":
            result.append(char)
            i += 1
            continue

        # 当前字符是反斜杠
        if i + 1 >= len(text):
            result.append("\\\\")
            i += 1
            continue

        next_char = text[i + 1]

        # 合法 JSON 转义：\", \\, \/, \b, \f, \n, \r, \t
        if next_char in ['"', "\\", "/", "b", "f", "n", "r", "t"]:
            result.append("\\")
            result.append(next_char)
            i += 2
            continue

        # 合法 JSON unicode 转义：\uXXXX
        if next_char == "u":
            hex_part = text[i + 2:i + 6]
            if len(hex_part) == 4 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
                result.append("\\")
                result.append("u")
                result.append(hex_part)
                i += 6
                continue

            # 例如 LaTeX 的 \underbrace，不是合法 JSON unicode
            result.append("\\\\")
            i += 1
            continue

        # 其他情况，比如 \sqrt, \frac, \ldots, \left，都转成 \\sqrt...
        result.append("\\\\")
        i += 1

    return "".join(result)


def index_subproblems(subproblems: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    将子问题列表转换为以 id 为索引的字典。

    例如：
    [
        {"id": "q1", "goal": "..."},
        {"id": "q2", "goal": "..."}
    ]
    变为：
    {
        "q1": {"id": "q1", "goal": "..."},
        "q2": {"id": "q2", "goal": "..."}
    }

    这样后续代码可以通过 id 快速访问子问题，如 sp_index["q1"]。
    同时会检查每个子问题的 id 是否唯一。
    """
    sp_index = {}

    for sp in subproblems:
        sp_id = sp.get("id")

        if not sp_id:
            raise ValueError("A subproblem is missing id")

        if sp_id in sp_index:
            raise ValueError(f"Duplicate subproblem id: {sp_id}")

        sp_index[sp_id] = sp

    return sp_index


def find_output_spec(source_sp: Dict[str, Any], field: str) -> Dict[str, Any]:
    """
    从上游子问题中查找某个字段的输出规范。
    """
    for output in source_sp.get("outputs", []):
        if output.get("field") == field:
            return output

    raise ValueError(
        f"Field {field!r} not found in outputs of subproblem {source_sp.get('id')!r}"
    )


def assert_valid_dag(subproblems: List[Dict[str, Any]]) -> None:
    """
    检查 depends_on 关系是否构成一个有效的 DAG（有向无环图）。
    检查:depends_on 里写的子问题 id 是否真的存在;子问题之间有没有循环依赖
    """
    sp_index = index_subproblems(subproblems)
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def dfs(node_id: str) -> None:
        if node_id in visited:
            return

        if node_id in visiting:
            raise ValueError(f"Dependency cycle detected at {node_id}")

        visiting.add(node_id)

        for dep_id in sp_index[node_id].get("depends_on", []):
            if dep_id not in sp_index:
                raise ValueError(
                    f"Subproblem {node_id} depends on unknown subproblem {dep_id}"
                )
            dfs(dep_id)

        visiting.remove(node_id)
        visited.add(node_id)

    for sp_id in sp_index:
        dfs(sp_id)

def correct_final_answer_subproblem_id(decomposition: Dict[str, Any]) -> Dict[str, Any]:
    """
    自动修正 final_answer_subproblem_id。

    适用场景：
    - DAG 本身已经包含真正最终答案节点；
    - 但是 LLM 把 final_answer_subproblem_id 标早了；
    - 例如 q3 是中间结果，q4 才是最终格式/最终合并结果。

    核心规则：
    - 如果整个 DAG 只有一个 sink node，就把 final_answer_subproblem_id 修正为这个 sink node；
    - 如果有多个 sink node，不自动修正，只记录 warning。
    """
    subproblems = decomposition.get("subproblems", [])
    if not isinstance(subproblems, list) or not subproblems:
        return decomposition

    final_id = decomposition.get("final_answer_subproblem_id")

    node_ids = []

    for sp in subproblems:
        if not isinstance(sp, dict):
            continue

        sp_id = sp.get("id")
        if not isinstance(sp_id, str) or not sp_id.strip():
            continue

        sp_id = sp_id.strip()
        node_ids.append(sp_id)

    node_id_set = set(node_ids)

    # 记录每个节点被哪些下游节点依赖
    children_map: Dict[str, List[str]] = {
        node_id: []
        for node_id in node_ids
    }

    for sp in subproblems:
        if not isinstance(sp, dict):
            continue

        sp_id = sp.get("id")

        if sp_id not in node_id_set:
            continue

        depends_on = sp.get("depends_on", [])
        if not isinstance(depends_on, list):
            continue

        for dep_id in depends_on:
            if dep_id in node_id_set:
                children_map[dep_id].append(sp_id)

    sink_node_ids = [
        node_id
        for node_id in node_ids
        if len(children_map.get(node_id, [])) == 0
    ]

    checker_info = {
        "applied": False,
        "original_final_answer_subproblem_id": final_id,
        "corrected_final_answer_subproblem_id": final_id,
        "sink_subproblem_ids": sink_node_ids,
        "reason": "",
    }

    if not final_id:
        checker_info["reason"] = "missing final_answer_subproblem_id"
        decomposition["_final_answer_checker"] = checker_info
        return decomposition

    # 只有一个 sink node 时，自动修正最稳。
    if len(sink_node_ids) == 1:
        sink_id = sink_node_ids[0]

        if final_id != sink_id:
            decomposition["final_answer_subproblem_id"] = sink_id

            checker_info["applied"] = True
            checker_info["corrected_final_answer_subproblem_id"] = sink_id
            checker_info["reason"] = (
                "final_answer_subproblem_id was not the unique sink node"
            )
        else:
            checker_info["reason"] = "final_answer_subproblem_id already matches the unique sink node"

    else:
        checker_info["reason"] = (
            "automatic correction skipped because the DAG has zero or multiple sink nodes"
        )

    decomposition["_final_answer_checker"] = checker_info
    return decomposition


def validate_decomposition(decomposition: Dict[str, Any]) -> None:
    """
    把 LLM 的拆题结果转换成静态 TaskTemplate 之前，先检查这个 decomposition 的结构是否满足后续代码处理要求
    """
    if "question_text" not in decomposition:  # 检查有没有原题文本
        raise ValueError("decomposition is missing question_text")

    if "subproblems" not in decomposition or not isinstance(decomposition["subproblems"], list):  # 检查有没有子问题列表
        raise ValueError("decomposition is missing subproblems list")

    # 建立子问题索引 + 检查 DAG
    subproblems = decomposition["subproblems"]
    sp_index = index_subproblems(subproblems)
    assert_valid_dag(subproblems)

    final_answer_subproblem_id = decomposition.get("final_answer_subproblem_id")

    if not final_answer_subproblem_id:
        raise ValueError("decomposition is missing final_answer_subproblem_id")

    if final_answer_subproblem_id not in sp_index:
        raise ValueError(
            f"final_answer_subproblem_id {final_answer_subproblem_id!r} "
            f"does not match any subproblem id"
        )

    for sp in subproblems:  # 遍历每个子问题
        sp_id = sp["id"]

        if "goal" not in sp:  # 检查子问题有没有 goal
            raise ValueError(f"Subproblem {sp_id} is missing goal")

        if "outputs" not in sp or not isinstance(sp["outputs"], list):  # 检查子问题有没有 outputs
            raise ValueError(f"Subproblem {sp_id} is missing outputs list")

        for output in sp["outputs"]:  # 检查每个 output 是否有 field/type/description
            if not output.get("field"):
                raise ValueError(f"Subproblem {sp_id} has an output without field")
            if not output.get("type"):
                raise ValueError(f"Subproblem {sp_id} output {output.get('field')!r} is missing type")
            if not output.get("description"):
                raise ValueError(
                    f"Subproblem {sp_id} output {output.get('field')!r} is missing description"
                )

        depends_on = set(sp.get("depends_on", []))

        for ref in sp.get("inputs_from_subproblems", []):  # 检查 inputs_from_subproblems
            source_id = ref.get("source_subproblem_id")  # 获取来源子问题ID
            field = ref.get("field")  # 获取字段名

            if not source_id or not field:  # 检查来源子问题ID和字段名是否为空
                raise ValueError(
                    f"Subproblem {sp_id} has malformed inputs_from_subproblems: {ref}"
                )

            if source_id not in sp_index:  # 检查依赖的子问题是否存在
                raise ValueError(
                    f"Subproblem {sp_id} references unknown source subproblem {source_id}"
                )

            if source_id not in depends_on:
                raise ValueError(
                    f"Subproblem {sp_id} uses output from {source_id}, "
                    f"but {source_id} is not in depends_on"
                )

            find_output_spec(sp_index[source_id], field)  # 检查依赖字段是否真的存在于上游 outputs


def build_upstream_inputs_template(
    sp: Dict[str, Any],
    sp_index: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    为静态 TaskTemplate 构建 upstream_inputs。

    在这个阶段，upstream_inputs 不包含 value（值）。 value 字段将在上游子问题被执行后，稍后添加。
    """
    upstream_inputs = []

    for ref in sp.get("inputs_from_subproblems", []):
        source_id = ref["source_subproblem_id"]
        field = ref["field"]

        source_sp = sp_index[source_id]
        output_spec = find_output_spec(source_sp, field)

        upstream_inputs.append({
            "field": field,
            "description": output_spec.get("description", ""),
            "source_subproblem_id": source_id,
            "source_goal": source_sp.get("goal", "")
        })

    return upstream_inputs


def build_task_templates_from_decomposition(
    decomposition: Dict[str, Any],
    background_question_text: str | None = None
) -> List[Dict[str, Any]]:
    """
    将一个 LLM 分解结果转换为静态 TaskTemplates。
    """
    validate_decomposition(decomposition)

    question_text = background_question_text or decomposition["question_text"]
    subproblems = decomposition["subproblems"]
    sp_index = index_subproblems(subproblems)

    task_templates = []

    for sp in subproblems:
        upstream_inputs = build_upstream_inputs_template(sp, sp_index)
        expected_outputs = deepcopy(sp.get("outputs", []))
        depends_on = deepcopy(sp.get("depends_on", []))

        template = {
            "subproblem_id": sp["id"],
            "background_question_text": question_text,
            "goal": sp["goal"],
            "local_evidence": deepcopy(sp.get("evidence_from_question", [])),
            "upstream_inputs": upstream_inputs,
            "expected_outputs": expected_outputs,
            "depends_on": depends_on,
            "instruction": INSTRUCTION
        }

        task_templates.append(template)


    return task_templates


def build_template_record_from_probe_record(record: Dict[str, Any]) -> Dict[str, Any]:
    decomposition = parse_llm_json(record["raw_output"])

    # 在构造静态模板前，先修正可能标早的 final_answer_subproblem_id
    decomposition = correct_final_answer_subproblem_id(decomposition)

    # 更稳：background_question_text 用原始 problem_text，而不是完全相信 LLM 复写的 question_text
    task_templates = build_task_templates_from_decomposition(
        decomposition=decomposition,
        background_question_text=record.get("problem_text")
    )

    return {
        "dataset": record.get("dataset"),
        "mode": record.get("mode"),
        "index": record.get("index"),
        "problem_text": record.get("problem_text"),
        "final_answer_subproblem_id": decomposition.get("final_answer_subproblem_id"),
        "final_answer_checker": decomposition.get("_final_answer_checker", {}),
        "task_templates": task_templates
    }