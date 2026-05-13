from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from taskcall_perception_map import (
    AdapterBackedWorkerAgent,
    AgentDefinition,
    AgentRegistry,
    ArtifactSelector,
    CapabilityCallStep,
    CapabilityInvocationContext,
    CapabilityRegistry,
    CompleteStep,
    ExecutionScheduler,
    InMemoryArtifactStore,
    InMemorySessionStore,
    InMemoryTranscriptStore,
    InMemoryWorkerAgentStore,
    LoopEngine,
    NestedAgentRuntime,
    NodeRunner,
    OutputSpec,
    OutputValidator,
    PermissionGate,
    PlanGraph,
    PlanNode,
    RuntimeTaskPackage,
    SemanticArtifact,
    SpawnAgentStep,
    TaskPackageBuilder,
    WorkerAgentIdentity,
    WorkerAgentManager,
)
from taskcall_perception_map.domain.models import AgentStepRequest


@dataclass(slots=True)
class AddNumbersCapability:
    name: str = "add_numbers"
    description: str = "Add a list of numeric values."

    async def invoke(
        self,
        payload: Any,
        context: CapabilityInvocationContext,
    ) -> float:
        values = payload["values"]
        return float(sum(values))


class ContributionWorkerAdapter:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id

    async def run_step(self, request: AgentStepRequest) -> CapabilityCallStep | CompleteStep:
        if "sum" not in request.scratchpad.capability_outputs:
            if self.node_id == "kim_amount":
                return CapabilityCallStep(
                    capability_name="add_numbers",
                    payload={"values": [430, 320]},
                    save_as="sum",
                    message="Computing Kim's fundraising total.",
                )

            return CapabilityCallStep(
                capability_name="add_numbers",
                payload={"values": [300, 400]},
                save_as="sum",
                message="Computing Maryam's fundraising total.",
            )

        result_value = request.scratchpad.capability_outputs["sum"]
        return CompleteStep(
            artifacts=[
                build_output_artifact(
                    request.task_package,
                    request.task_package.expected_outputs[0].field,
                    result_value,
                    provenance=[f"demo:{self.node_id}"],
                )
            ],
            raw_output={"value": result_value},
        )


class AggregatorAdapter:
    async def run_step(
        self,
        request: AgentStepRequest,
    ) -> SpawnAgentStep | CompleteStep:
        if "delegated_total" not in request.scratchpad.agent_outputs:
            kim_amount = next(
                artifact.value
                for artifact in request.task_package.upstream_inputs
                if artifact.field == "kim_amount"
            )
            maryam_amount = next(
                artifact.value
                for artifact in request.task_package.upstream_inputs
                if artifact.field == "maryam_amount"
            )
            delegated_inputs = [
                literal_artifact(
                    field="kim_amount",
                    value=kim_amount,
                    description="Kim's total contribution.",
                    producer_node_id=request.task_package.node_id,
                ),
                literal_artifact(
                    field="maryam_amount",
                    value=maryam_amount,
                    description="Maryam's total contribution.",
                    producer_node_id=request.task_package.node_id,
                ),
                literal_artifact(
                    field="alexandra_amount",
                    value=430.0,
                    description="Alexandra's direct contribution.",
                    producer_node_id=request.task_package.node_id,
                ),
                literal_artifact(
                    field="sarah_amount",
                    value=300.0,
                    description="Sarah's direct contribution.",
                    producer_node_id=request.task_package.node_id,
                ),
            ]
            return SpawnAgentStep(
                task_goal="Add all contribution amounts and return the final total.",
                required_capabilities=["add_numbers"],
                local_evidence=[
                    "The final worker only needs to perform the addition.",
                ],
                provided_inputs=delegated_inputs,
                expected_outputs=[
                    OutputSpec(
                        field="delegated_total",
                        artifact_type="value",
                        description="The combined contribution total.",
                    )
                ],
                save_as="delegated_total",
                message="Delegating the final addition to a child sum worker.",
            )

        child_result = request.scratchpad.agent_outputs["delegated_total"]
        total_value = child_result.artifacts[0].value
        return CompleteStep(
            artifacts=[
                build_output_artifact(
                    request.task_package,
                    "total_amount",
                    total_value,
                    provenance=[
                        "demo:total_amount",
                        f"child-agent:{child_result.identity.agent_id}",
                    ],
                )
            ],
            raw_output={"value": total_value},
        )


class SumWorkerAdapter:
    async def run_step(self, request: AgentStepRequest) -> CapabilityCallStep | CompleteStep:
        if "sum" not in request.scratchpad.capability_outputs:
            values = [
                float(artifact.value) for artifact in request.task_package.upstream_inputs
            ]
            return CapabilityCallStep(
                capability_name="add_numbers",
                payload={"values": values},
                save_as="sum",
                message="Child worker is summing delegated inputs.",
            )

        result_value = request.scratchpad.capability_outputs["sum"]
        return CompleteStep(
            artifacts=[
                build_output_artifact(
                    request.task_package,
                    request.task_package.expected_outputs[0].field,
                    result_value,
                    provenance=[
                        "demo:sum_worker",
                        (
                            "parent:"
                            f"{request.task_package.metadata.get('parent_agent_id')}"
                        ),
                    ],
                )
            ],
            raw_output={"value": result_value},
        )


def build_output_artifact(
    task_package: RuntimeTaskPackage,
    field: str,
    value: float,
    *,
    provenance: list[str],
) -> SemanticArtifact:
    output_spec = next(
        spec for spec in task_package.expected_outputs if spec.field == field
    )
    return SemanticArtifact(
        field=output_spec.field,
        artifact_type=output_spec.artifact_type,
        value=value,
        description=output_spec.description,
        producer_node_id=task_package.node_id,
        provenance=provenance,
    )


def literal_artifact(
    *,
    field: str,
    value: float,
    description: str,
    producer_node_id: str,
) -> SemanticArtifact:
    return SemanticArtifact(
        field=field,
        artifact_type="value",
        value=value,
        description=description,
        producer_node_id=producer_node_id,
        provenance=[f"demo:{producer_node_id}:{field}"],
    )


def build_demo_plan() -> PlanGraph:
    return PlanGraph(
        question_text=(
            "Kim raises $320 more than Alexandra, who raises $430. "
            "Maryam raises $400 more than Sarah, who raises $300. "
            "How much do they raise in total?"
        ),
        nodes=[
            PlanNode(
                id="kim_amount",
                goal="Compute the amount of money Kim raised.",
                evidence_from_question=[
                    "Kim raises $320 more than Alexandra, who raises $430."
                ],
                inputs_from_subproblems=[],
                outputs=[
                    OutputSpec(
                        field="kim_amount",
                        artifact_type="value",
                        description="The amount of money Kim raised.",
                    )
                ],
                depends_on=[],
                agent_profile="math_worker",
                tool_policy=["add_numbers"],
            ),
            PlanNode(
                id="maryam_amount",
                goal="Compute the amount of money Maryam raised.",
                evidence_from_question=[
                    "Maryam raises $400 more than Sarah, who raises $300."
                ],
                inputs_from_subproblems=[],
                outputs=[
                    OutputSpec(
                        field="maryam_amount",
                        artifact_type="value",
                        description="The amount of money Maryam raised.",
                    )
                ],
                depends_on=[],
                agent_profile="math_worker",
                tool_policy=["add_numbers"],
            ),
            PlanNode(
                id="total_amount",
                goal="Compute the total amount raised by all four girls.",
                evidence_from_question=[
                    "Alexandra raises $430.",
                    "Sarah raises $300.",
                ],
                inputs_from_subproblems=[
                    ArtifactSelector(
                        source_node_id="kim_amount",
                        field="kim_amount",
                    ),
                    ArtifactSelector(
                        source_node_id="maryam_amount",
                        field="maryam_amount",
                    ),
                ],
                outputs=[
                    OutputSpec(
                        field="total_amount",
                        artifact_type="value",
                        description="The total amount raised by all four girls.",
                    )
                ],
                depends_on=["kim_amount", "maryam_amount"],
                agent_profile="aggregator",
                tool_policy=[],
            ),
        ],
    )


def build_worker_agent(
    task_package: RuntimeTaskPackage,
    identity: WorkerAgentIdentity,
) -> AdapterBackedWorkerAgent:
    if task_package.agent_profile == "math_worker":
        adapter = ContributionWorkerAdapter(task_package.node_id)
    elif task_package.agent_profile == "aggregator":
        adapter = AggregatorAdapter()
    elif task_package.agent_profile == "sum_worker":
        adapter = SumWorkerAdapter()
    else:
        raise KeyError(f"Unknown agent profile: {task_package.agent_profile}")

    return AdapterBackedWorkerAgent(identity=identity, adapter=adapter)


async def main() -> None:
    plan = build_demo_plan()

    capability_registry = CapabilityRegistry()
    capability_registry.register(AddNumbersCapability())

    transcript_store = InMemoryTranscriptStore()
    loop_engine = LoopEngine(
        capability_registry=capability_registry,
        permission_gate=PermissionGate(),
        output_validator=OutputValidator(),
        transcript_store=transcript_store,
    )

    agent_store = InMemoryWorkerAgentStore()
    worker_agent_manager = WorkerAgentManager(
        worker_agent_factory=build_worker_agent,
        agent_store=agent_store,
    )

    agent_registry = AgentRegistry()
    agent_registry.register(
        AgentDefinition(
            agent_type="sum_worker",
            description="A focused worker that sums delegated numeric inputs.",
            supported_capabilities=["add_numbers"],
            preferred_keywords=["add", "sum", "total"],
            default_instruction=(
                "Use the delegated numeric inputs and return one value artifact."
            ),
        )
    )
    loop_engine.child_agent_runtime = NestedAgentRuntime(
        agent_registry=agent_registry,
        worker_agent_manager=worker_agent_manager,
        loop_engine=loop_engine,
    )

    node_runner = NodeRunner(
        task_package_builder=TaskPackageBuilder(),
        loop_engine=loop_engine,
        worker_agent_manager=worker_agent_manager,
    )

    scheduler = ExecutionScheduler(
        node_runner=node_runner,
        artifact_store=InMemoryArtifactStore(),
        session_store=InMemorySessionStore(),
    )

    summary = await scheduler.run(plan)

    print("Session:", summary.session_id)
    print("Completed nodes:", summary.completed_node_ids)
    print("Failed nodes:", summary.failed_node_ids)
    print("Pending nodes:", summary.pending_node_ids)
    print()
    print("Artifacts:")
    for artifact in summary.artifacts:
        print(f"  - {artifact.producer_node_id}.{artifact.field} = {artifact.value}")
    print()
    print("Node states:")
    for node_id, state in summary.snapshot.node_states.items():
        print(f"  - {node_id}: {state.status} (attempts={state.attempt_count})")
    print()
    print("Worker agents:")
    for session in agent_store.list_all():
        print(
            "  - "
            f"{session.identity.display_name} -> {session.status}"
            f" (node={session.identity.node_id}, "
            f"parent={session.identity.parent_agent_id}, "
            f"transcript={session.transcript_id})"
        )
    print()
    print("Transcripts recorded:", len(transcript_store.list_all()))


def main_entry() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_entry()
