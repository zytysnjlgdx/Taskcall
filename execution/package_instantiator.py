from copy import deepcopy
from typing import Any, Dict


def instantiate_task_package(
    task_template: Dict[str, Any],
    execution_results: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Convert a static TaskTemplate into a dynamic TaskPackage.

    Static TaskTemplate:
    - upstream_inputs contains references to upstream outputs.
    - Each upstream input has field, description, source_subproblem_id, and source_goal.
    - It does not contain value yet.

    Dynamic TaskPackage:
    - Each upstream input is filled with the real value from execution_results.

    Example:
    Static upstream input:
    {
        "field": "kim_amount",
        "description": "The amount raised by Kim.",
        "source_subproblem_id": "q1",
        "source_goal": "Compute Kim's amount."
    }

    execution_results:
    {
        "q1": {
            "kim_amount": 750
        }
    }

    Dynamic upstream input:
    {
        "field": "kim_amount",
        "value": 750,
        "description": "The amount raised by Kim.",
        "source_subproblem_id": "q1",
        "source_goal": "Compute Kim's amount."
    }
    """

    task_package = deepcopy(task_template)

    for upstream_input in task_package.get("upstream_inputs", []):
        source_id = upstream_input.get("source_subproblem_id")
        field = upstream_input.get("field")

        if not source_id:
            raise ValueError(
                f"Malformed upstream input in {task_template.get('subproblem_id')}: "
                f"missing source_subproblem_id. upstream_input={upstream_input}"
            )

        if not field:
            raise ValueError(
                f"Malformed upstream input in {task_template.get('subproblem_id')}: "
                f"missing field. upstream_input={upstream_input}"
            )

        if source_id not in execution_results:
            raise ValueError(
                f"Cannot instantiate task package for {task_template.get('subproblem_id')}: "
                f"missing execution result for upstream subproblem {source_id!r}."
            )

        if field not in execution_results[source_id]:
            raise ValueError(
                f"Cannot instantiate task package for {task_template.get('subproblem_id')}: "
                f"field {field!r} not found in execution result of {source_id!r}."
            )

        upstream_input["value"] = execution_results[source_id][field]

    return task_package