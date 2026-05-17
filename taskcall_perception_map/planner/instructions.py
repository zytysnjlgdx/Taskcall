ZERO_SHOT_DECOMPOSITION_INSTRUCTION = """
You are a problem-structure-aware task decomposition module.

Your task is to identify the underlying structure of the original problem and decompose it into a compact set of necessary subproblems. Each subproblem should correspond to a distinct structural step needed to reach the final answer, with at least 2 subproblems. The decomposition must contain exactly one terminal subproblem, and this terminal subproblem must directly produce the final answer requested by the original problem.

Before creating subproblems, analyze what the problem provides, what final answer it asks for, and what structural steps are necessary to bridge them, including any required constraints, intermediate results, transformations, comparisons, decision rules, specifications, or executable artifacts.

Each subproblem should correspond to one necessary component of the problem structure and produce a useful output for downstream solving.

Do not split a single coherent reasoning step into multiple subproblems unless the split produces distinct outputs that are needed downstream.

Requirements:

1. The output must include final_answer_contract. Before choosing its format, infer what kind of final answer the original problem asks for. final_answer_contract defines the required format of the final answer value, not the final answer itself. Do not put the actual final answer in final_answer_contract. The format field must be exactly one of: choice_label, number_or_expression, or code_block. Use choice_label for explicit answer choices or labels, number_or_expression for numeric results or symbolic expressions, and code_block for executable code. Use allowed_values only when the original problem explicitly provides a fixed set of answer choices or labels; otherwise use an empty list []. For choice_label, allowed_values should contain only the answer labels, such as A, B, C, D, when such labels are present.

2. Each subproblem must be specific, well-defined, and executable at the appropriate abstraction level. Its goal must clearly state the concrete output it will produce, such as an intermediate result, extracted constraint, decision rule, comparison result, candidate answer, implementation specification, executable artifact, or final answer.

3. Each subproblem should include evidence_from_question when it directly relies on information from the original problem text. The evidence must be copied directly from the original problem text. If a subproblem mainly depends on upstream subproblem outputs rather than direct original-text evidence, evidence_from_question may be an empty list []. Each subproblem must be self-contained with respect to the information needed to produce its output. Every original-problem quantity, condition, option, or constraint required by the subproblem must appear in evidence_from_question unless it is supplied by inputs_from_subproblems.

4. Do not create a subproblem that requires enumerating an infinite, unbounded, or very large set of values, candidates, cases, or solutions. If such a set may be infinite or large, the subproblem must require a compact representation, such as a formula, parameterized solution, constraint, rule, symbolic expression, or summary sufficient for downstream solving.

5. If one subproblem uses any output from another subproblem, it must record that dependency in inputs_from_subproblems. Each dependency must specify the source subproblem id and the output field being used.

6. Each subproblem must define clear outputs. Each output field should describe a concrete artifact produced by that subproblem, not a vague reasoning process. The description of each output must only describe the meaning, format, or role of the output field. It must not include the actual answer, computed value, solved result, or any value that the executor is supposed to produce. The type field of each output must be exactly one of: value, evidence, rule, candidate, judgement, code, or other. Use "rule" for formulas, constraints, definitions, theorem applications, and decision rules.

7. The dependencies defined by inputs_from_subproblems must form a valid DAG. A downstream subproblem should only depend on upstream outputs that are actually needed for its own goal.

8. The generated DAG is the core solving graph: it must only contain subproblems that contribute to producing the final answer. Do not create separate validation, checking, confirmation, testing, pure formatting, or answer-restatement subproblems.

Output format:
{
  "final_answer_contract": {
    "format": "<choice_label|number_or_expression|code_block>",
    "allowed_values": []
  },
  "subproblems": [
    {
      "id": "q2",
      "goal": "<goal>",
      "evidence_from_question": ["<evidence 1>", "<evidence 2>"],
      "inputs_from_subproblems": [
        {
          "source_subproblem_id": "q1",
          "field": "<field name>"
        }
      ],
      "outputs": [
        {
          "field": "<output field>",
          "type": "<value|evidence|rule|candidate|judgement|code|other>",
          "description": "<meaning of the output>"
        }
      ]
    }
  ]
}

Now process the following problem. Return exactly one JSON object that strictly follows the Output format above. Do not include explanations, comments, or extra text outside the JSON object.

Problem:
""".strip()


# ---------------------------------------------------------------------------
# 子问题执行阶段的指令
# ---------------------------------------------------------------------------
# 注意：Planner 当前只负责生成 PlanGraph。下面这个执行指令只是作为 PlanNode 的默认
# instruction 兜底保留；runtime/adapter 后续可以再和朋友一起统一改成新版动态任务包协议。
NORMAL_EXECUTION_INSTRUCTION = (
    "Solve only the current subproblem, not the entire original problem. "
    "Prioritize upstream_inputs and local_evidence. "
    "If necessary information for the current subproblem is missing from them, "
    "use background_question_text only as supplementary context. "
    "Return exactly one valid JSON object whose field names match expected_outputs. "
    "Do not include explanations, comments, or extra text outside the JSON object."
)
