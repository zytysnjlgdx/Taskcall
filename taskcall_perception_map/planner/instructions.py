ZERO_SHOT_DECOMPOSITION_INSTRUCTION = """
You are a high-level task decomposition module.
Your job is NOT to directly solve the original problem or provide a full code solution.
Instead, decompose the original problem into 2 to 4 high-level subproblems and output a structured JSON object.

Requirements:
1. Each subproblem must be specific, well-defined, and executable at the appropriate abstraction level. 
   Avoid vague goals such as "analyze the problem", "think deeply", or "reason about the task".
2. For tasks that require deriving a concrete answer or selecting among provided options based on the given problem 
   statement, it is acceptable to decompose through intermediate quantities, intermediate facts, partial results, 
   option comparison, or option elimination.
3. For function-writing or code-implementation tasks, usually indicated by a function signature such as def xxx(...) 
   or phrases like "write a function", use exactly 4 subproblems in this order: q1 extracts the function specification, 
   including objective, inputs, outputs, constraints, examples, and edge cases; q2 designs the complete core implementation logic, 
   including all required algorithm steps, but must not write the complete function implementation or output code;; q3 only produces 
   the final function implementation based on q2 and must not introduce new algorithm-design subgoals; q4 validates the implementation 
   against the stated requirements, visible examples, and edge cases. 
4. Each subproblem should include evidence_from_question when it directly relies on information from the original problem text. 
   The evidence must be copied directly from the original problem text. If a subproblem mainly depends on upstream subproblem outputs 
   rather than direct original-text evidence, evidence_from_question may be an empty list [].
5. If one subproblem uses any output from another subproblem, it must record that dependency in both inputs_from_subproblems and depends_on.
6. Each subproblem must define clear outputs.
7. The dependency graph must be a valid DAG.
8. The output must include final_answer_subproblem_id. Set it to the id of the subproblem that directly produces the final answer. 
   If a later subproblem only validates, checks, formats, or restates a previous answer, do not select that later subproblem.
9. The output must include validation_subproblem_ids. Only function-writing or code-implementation tasks may include a validation subproblem.
   In code tasks, validation_subproblem_ids should contain only the subproblem that validates the final code produced by final_answer_subproblem_id.
   For all non-code tasks, do not create validation/checking subproblems and set validation_subproblem_ids to [].
10. Return exactly one JSON object without explanations, comments, or extra text.

Output format:
{
  "question_text": "<original problem text>",
  "final_answer_subproblem_id": "<id of the subproblem that produces the final answer>",
  "validation_subproblem_ids": [],
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
      ],
      "depends_on": ["q1"]
    }
  ]
}
""".strip()

# ---------------------------------------------------------------------------
# 子问题执行阶段的指令
# ---------------------------------------------------------------------------

# 普通子问题的执行指令：告诉执行器只解当前子问题，返回 JSON
NORMAL_EXECUTION_INSTRUCTION = (
    "Solve only the current subproblem, not the entire original problem. "
    "Use upstream_inputs and local_evidence as the main evidence; background_question_text is only supplementary context. "
    "Return exactly one JSON object whose field names strictly match expected_outputs. "
    "Each field value must directly contain the required value, judgement, code, or result. "
    "For example, if expected_outputs defines the field \"kim_amount\", the output must be like {\"kim_amount\": 750}. "
    "If an expected output type is not \"code\", do not output code or a complete function implementation; use natural language or structured steps instead. "
    "If an expected output type is \"code\", put the complete code as the string value of the corresponding JSON field, inside a Python fenced code block. "
    "Do not add explanations, headings, or extra fields outside the JSON object."
)

# 验证子问题的执行指令：告诉执行器验证答案是否正确，而不是重新解题
VALIDATION_EXECUTION_INSTRUCTION = (
    "You are validating the final answer, not solving the original problem from scratch. "
    "Use upstream_inputs and upstream_dependency_graph to inspect previous subproblem outputs and their dependency structure. "
    "Determine whether the final answer produced by validation_target_subproblem_id is valid. "
    "Return exactly one JSON object. "
    "The JSON field names must strictly match the field names defined in expected_outputs. "
    "Set validation_status to \"valid\" or \"invalid\". "
    "If invalid, set error_source_subproblem_id to the most likely subproblem id that caused the error, "
    "and provide error_reason and suggested_fix. "
    "If valid, set error_source_subproblem_id to null, and set error_reason and suggested_fix to empty strings."
)

# 验证子问题的默认输出契约：验证节点必须返回这 4 个字段
VALIDATION_EXPECTED_OUTPUTS = [
    {
        "field": "validation_status",
        "type": "judgement",
        "description": "Whether the final answer is valid. The value must be either valid or invalid."
    },
    {
        "field": "error_source_subproblem_id",
        "type": "judgement",
        "description": "If validation_status is invalid, the id of the subproblem most likely causing the error; otherwise null."
    },
    {
        "field": "error_reason",
        "type": "judgement",
        "description": "The reason why the final answer is invalid, or an empty string if it is valid."
    },
    {
        "field": "suggested_fix",
        "type": "judgement",
        "description": "A concise suggestion for fixing the error, or an empty string if it is valid."
    }
]
