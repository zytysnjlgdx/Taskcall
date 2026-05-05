"""整个任务图运行时的公共数据协议。

可以把这个文件理解成系统各层之间共同遵守的“说话格式”：

1. planner 先产出 ``PlanGraph`` / ``PlanNode``
2. scheduler 根据依赖关系推进节点
3. runtime 把节点组装成 ``RuntimeTaskPackage``
4. loop engine 在节点内部循环，最终产出 ``NodeExecutionResult``
5. store 层把过程和结果沉淀成 transcript / snapshot / artifacts

所以这个文件本身不负责执行逻辑，它负责回答一个更底层的问题：
“这个系统在不同阶段，到底传递的是什么数据？”
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_timestamp() -> str:
    """返回统一的 UTC 时间戳。

    这类时间戳主要用于：
    - 记录节点什么时候开始、结束
    - 记录 transcript 什么时候写入
    - 方便之后做回放、审计、排错
    """
    return datetime.now(timezone.utc).isoformat()


# Artifact and state enums keep the runtime vocabulary explicit.
ArtifactType = Literal[
    "value",
    "evidence",
    "rule",
    "candidate",
    "judgement",
    "other",
]
NodeStatus = Literal["pending", "ready", "running", "success", "failed"]
NodeExecutionStatus = Literal["success", "failed", "partial"]
TranscriptKind = Literal["info", "model", "capability", "agent", "result", "error"]


# Plan definition structures -------------------------------------------------

@dataclass(slots=True)
class ArtifactSelector:
    """声明“我要从上游节点拿什么输入”。

    谁来创建：
    - planner 在构建 ``PlanNode`` 时写入

    谁来使用：
    - ``TaskPackageBuilder`` 在节点真正执行前解析它

    字段说明：
    - ``source_node_id``: 上游节点 id
    - ``field``: 上游节点产出的字段名
    - ``required``: 如果拿不到这个输入，是否直接视为不能执行
    """

    source_node_id: str
    field: str
    required: bool = True


@dataclass(slots=True)
class OutputSpec:
    """声明“这个节点应该产出什么”。

    它是输出契约，不是实际结果。

    谁来创建：
    - planner 在定义 ``PlanNode`` 时写入

    谁来使用：
    - adapter 执行时参考它组织输出
    - ``OutputValidator`` 在节点完成时拿它做校验

    字段说明：
    - ``field``: 输出字段名
    - ``artifact_type``: 输出属于哪类语义产物
    - ``description``: 这个字段的语义说明
    - ``required``: 是否必须返回
    """

    field: str
    artifact_type: ArtifactType
    description: str
    required: bool = True


@dataclass(slots=True)
class PlanNode:
    """任务图中的一个节点。

    它代表“一个可独立执行的子任务单元”。

    一个节点同时包含四类信息：
    - 目标：这个节点要解决什么子问题
    - 依赖：它必须等谁先完成
    - 输入输出契约：它拿什么、吐出什么
    - 执行约束：它能调用哪些能力，用什么 agent profile

    字段说明：
    - ``id``: 节点唯一标识
    - ``goal``: 节点要完成的子目标
    - ``evidence_from_question``: 直接从原问题中抽出的本地证据
    - ``inputs_from_subproblems``: 依赖其他节点时要引用的结构化输入
    - ``outputs``: 这个节点承诺返回的输出字段定义
    - ``depends_on``: 调度层依赖，决定执行顺序
    - ``agent_profile``: 这个节点适合交给哪类执行器/代理画像
    - ``tool_policy``: 允许使用哪些 capability
    - ``instruction``: 给执行器的额外指令，没有时可由 runtime 自动补默认值
    - ``metadata``: 预留扩展信息，不参与核心调度规则

    注意：
    ``depends_on`` 是“顺序依赖”，
    ``inputs_from_subproblems`` 是“数据依赖”。
    两者通常相关，但不是一个概念。
    """

    id: str
    goal: str
    evidence_from_question: list[str]
    inputs_from_subproblems: list[ArtifactSelector]
    outputs: list[OutputSpec]
    depends_on: list[str]
    agent_profile: str
    tool_policy: list[str]
    instruction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlanGraph:
    """整道问题被拆解后的任务图。

    谁来创建：
    - planner

    谁来使用：
    - scheduler 读取它来推进全局执行
    - runtime 在执行单节点时从中取原问题和节点定义

    字段说明：
    - ``question_text``: 用户原始问题
    - ``nodes``: 被拆分出的全部节点
    - ``metadata``: 图级别的补充信息
    """

    question_text: str
    nodes: list[PlanNode]
    metadata: dict[str, Any] = field(default_factory=dict)


# Artifact and task-package structures ---------------------------------------

@dataclass(slots=True)
class SemanticArtifact:
    """节点真正产出的结构化结果。

    它和 ``OutputSpec`` 的区别非常关键：
    - ``OutputSpec`` 是“应该产出什么”
    - ``SemanticArtifact`` 是“实际产出了什么”

    谁来创建：
    - adapter 在 ``CompleteStep`` 中返回

    谁来使用：
    - ``ArtifactStore`` 保存
    - 下游节点通过 ``ArtifactSelector`` 引用
    - scheduler 汇总进 session snapshot

    字段说明：
    - ``field``: 结果字段名
    - ``artifact_type``: 结果类型
    - ``value``: 真正的值
    - ``description``: 这个值的语义说明
    - ``producer_node_id``: 是哪个节点产出的
    - ``provenance``: 来源链路、推理依据或证据说明
    - ``created_at``: 产出时间
    """

    field: str
    artifact_type: ArtifactType
    value: Any
    description: str
    producer_node_id: str
    provenance: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)


@dataclass(slots=True)
class RuntimeTaskPackage:
    """节点执行前的最终任务包。

    这是静态计划被翻译成“可执行上下文”之后的样子。

    谁来创建：
    - ``TaskPackageBuilder``

    谁来使用：
    - ``LoopEngine``
    - ``AgentAdapter``

    字段说明：
    - ``session_id``: 当前运行属于哪个 session
    - ``question_text``: 原始问题文本
    - ``node_id``: 当前执行的是哪个节点
    - ``goal``: 当前节点目标
    - ``agent_profile``: 当前节点对应的执行器画像
    - ``local_evidence``: 从原问题直接带下来的上下文证据
    - ``upstream_inputs``: 从上游节点解析出来的结构化输入
    - ``expected_outputs``: 本节点必须遵守的输出契约
    - ``instruction``: 最终给 adapter 的执行指令
    - ``allowed_capabilities``: 本节点允许调用的能力名单
    - ``metadata``: 扩展信息
    """

    session_id: str
    question_text: str
    node_id: str
    goal: str
    agent_profile: str
    local_evidence: list[str]
    upstream_inputs: list[SemanticArtifact]
    expected_outputs: list[OutputSpec]
    instruction: str
    allowed_capabilities: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


# Validation and execution state ---------------------------------------------

@dataclass(slots=True)
class ValidationIssue:
    """描述一次输出校验失败。

    它不代表系统异常，而代表：
    “节点返回了结果，但结果不符合节点契约”。
    """

    message: str
    field: str | None = None


@dataclass(slots=True)
class NodeRuntimeState:
    """调度器眼中的节点状态。

    这是 scheduler 维护的“外部状态”，不是节点内部思考状态。

    字段说明：
    - ``node_id``: 节点 id
    - ``status``: 当前处于 pending/ready/running/success/failed 哪一步
    - ``attempt_count``: 已尝试执行了几次
    - ``last_error``: 最近一次失败原因
    - ``started_at``: 最近一次开始执行时间
    - ``finished_at``: 最近一次结束执行时间
    """

    node_id: str
    status: NodeStatus = "pending"
    attempt_count: int = 0
    last_error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class NodeExecutionResult:
    """节点运行层返回给调度层的结果包。

    谁来创建：
    - ``LoopEngine`` 正常结束或失败时创建
    - ``ExecutionScheduler`` 捕获底层异常时也可能兜底创建

    谁来使用：
    - ``ExecutionScheduler._apply_result()``

    字段说明：
    - ``node_id``: 哪个节点的结果
    - ``status``: success / failed / partial
    - ``artifacts``: 实际产出的结构化结果
    - ``transcript_id``: 对应的过程记录 id
    - ``raw_output``: 原始输出，主要用于调试或回放
    - ``failure_reason``: 失败原因
    - ``retryable``: 失败时是否值得重试
    - ``issues``: 输出校验问题列表
    """

    node_id: str
    status: NodeExecutionStatus
    artifacts: list[SemanticArtifact]
    transcript_id: str
    raw_output: Any | None = None
    failure_reason: str | None = None
    retryable: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)


# Transcript and session records ---------------------------------------------

@dataclass(slots=True)
class TranscriptEntry:
    """节点内部循环里产生的一条日志。"""

    kind: TranscriptKind
    message: str
    data: Any | None = None
    timestamp: str = field(default_factory=utc_timestamp)


@dataclass(slots=True)
class TranscriptRecord:
    """某个节点一次执行过程的完整记录。

    它是“过程可解释性”的核心数据结构。
    以后你们要做调试、回放、可视化，都会先看这里。
    """

    transcript_id: str
    node_id: str
    entries: list[TranscriptEntry] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)


@dataclass(slots=True)
class SessionSnapshot:
    """某次全局运行的快照。

    可以把它看成 scheduler 当前时刻对整个世界的认知：
    - 原始 plan 是什么
    - 每个节点跑到哪了
    - 到目前为止累计出了哪些 artifacts
    """

    session_id: str
    plan: PlanGraph
    node_states: dict[str, NodeRuntimeState]
    artifacts: list[SemanticArtifact] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)


@dataclass(slots=True)
class SchedulerRunSummary:
    """scheduler 停止推进后给出的总结对象。

    它不是过程状态，而是“收尾汇总”：
    - 哪些节点完成了
    - 哪些失败了
    - 哪些还悬着
    - 最终快照是什么
    """

    session_id: str
    completed_node_ids: list[str]
    failed_node_ids: list[str]
    pending_node_ids: list[str]
    artifacts: list[SemanticArtifact]
    snapshot: SessionSnapshot


# Adapter loop protocol ------------------------------------------------------

@dataclass(slots=True)
class AdapterScratchpad:
    """节点内部循环的临时工作区。

    它解决的是：同一个节点跑多轮时，前几轮拿到的工具结果、
    中间笔记、局部结论，后几轮还能继续用。
    """

    capability_outputs: dict[str, Any] = field(default_factory=dict)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentStepRequest:
    """LoopEngine 每一轮发给 adapter 的请求对象。

    它把“当前节点上下文”和“当前循环状态”一起交给 adapter。
    adapter 不需要自己去查 store，它只读这个包就够了。
    """

    task_package: RuntimeTaskPackage
    iteration: int
    transcript_id: str
    scratchpad: AdapterScratchpad


@dataclass(slots=True)
class ContinueStep:
    """告诉 LoopEngine：先别结束，继续下一轮。"""

    message: str | None = None


@dataclass(slots=True)
class CapabilityCallStep:
    """告诉 LoopEngine：这一轮我要调用一个 capability。

    注意这里的设计思想：
    adapter 不直接调用能力，
    adapter 只是“声明意图”，真正的调用由 LoopEngine 执行。
    这样权限控制、日志记录、异常处理才能统一收口。
    """

    capability_name: str
    payload: Any
    save_as: str | None = None
    message: str | None = None


@dataclass(slots=True)
class SpawnAgentStep:
    """Tell the loop engine to delegate a subtask to a child worker-agent."""

    task_goal: str
    requested_agent_type: str | None = None
    required_capabilities: list[str] = field(default_factory=list)
    local_evidence: list[str] = field(default_factory=list)
    provided_inputs: list[SemanticArtifact] = field(default_factory=list)
    expected_outputs: list[OutputSpec] = field(default_factory=list)
    instruction: str | None = None
    save_as: str | None = None
    wait_for_result: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    message: str | None = None


@dataclass(slots=True)
class CompleteStep:
    """告诉 LoopEngine：节点已经完成，并返回最终 artifacts。"""

    artifacts: list[SemanticArtifact]
    raw_output: Any | None = None


@dataclass(slots=True)
class FailStep:
    """告诉 LoopEngine：节点明确失败了，并附带失败原因。"""

    reason: str
    retryable: bool = False
