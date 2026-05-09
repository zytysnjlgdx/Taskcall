# TaskCall-PerceptionMap 接口文档 / 需求文档

## 1. 文档目的

本文档用于说明 `TaskCall-PerceptionMap` 的核心能力、模块职责、对外接口、数据契约与运行流程。

这不是 HTTP API 文档，而是面向二次开发、模块集成、能力接入、LLM 规划接入的系统接口文档。换句话说，它本质上也是一份当前版本的需求文档。

## 2. 系统定位

`TaskCall-PerceptionMap` 是一个轻量级的任务编排原型，目标是把一个复杂任务拆成可执行的 DAG 节点，再通过受控执行循环完成节点执行、能力调用、子 Agent 委托、产物沉淀与依赖推进。

系统重点解决以下问题：

- 如何把一个问题拆成显式计划图 `PlanGraph`
- 如何表达节点之间的顺序依赖和数据依赖
- 如何让单个节点在受控循环内执行，而不是直接让模型一轮出结果
- 如何沉淀中间产物 `SemanticArtifact`
- 如何支持子 Agent 嵌套执行
- 如何记录 transcript、session snapshot、artifact state 以支持调试和回放

## 3. 当前范围

### 3.1 已支持

- 计划图定义与解析
- 基于 DAG 的调度执行
- 节点级执行循环
- capability 注册与调用
- capability 权限门控
- 结构化输出校验
- 中间产物在节点之间传递
- 子 Agent 委托执行
- 内存态 session / artifact / transcript / worker agent 存储

### 3.2 未支持

- Web API
- CLI 产品化入口
- 持久化数据库
- 分布式执行
- 异步子 Agent 执行
- 完整生产级鉴权与审计

## 4. 总体架构

系统按职责分为 6 层：

1. `planner`
   负责生成计划图，输出 `PlanGraph`
2. `scheduler`
   负责按依赖推进节点执行，管理全局 session 状态
3. `runtime`
   负责把节点翻译成可执行任务包，并驱动节点执行循环
4. `capabilities`
   负责定义外部能力与调用注册中心
5. `agents`
   负责 worker agent 的生成、管理与子 Agent 运行时
6. `storage`
   负责 artifacts、session、transcript、worker agent 的存储

核心调用链如下：

`PlanGraph -> ExecutionScheduler -> NodeRunner -> TaskPackageBuilder -> LoopEngine -> Capability / ChildAgent -> NodeExecutionResult -> SessionSnapshot`

## 5. 核心业务需求

### 5.1 任务拆解需求

系统需要支持把一个用户问题拆解为多个可独立执行的节点，每个节点至少应包含：

- 节点唯一标识
- 节点目标
- 来自原问题的直接证据
- 来自上游节点的输入选择器
- 输出字段定义
- 依赖节点列表
- 执行所需 agent profile
- 允许使用的 capability 列表

### 5.2 调度需求

系统需要支持：

- 自动识别无依赖或依赖已满足的 ready 节点
- 按批次并发执行 ready 节点
- 在节点成功后解锁下游节点
- 在节点失败后按策略决定重试或终止
- 输出完整的 session 执行结果摘要

### 5.3 节点执行需求

每个节点必须通过统一 LoopEngine 执行，不允许 adapter 直接越过引擎调用能力。引擎需要统一处理：

- transcript 记录
- capability 权限检查
- capability 调用
- 子 Agent 委托
- 输出校验
- 失败收口

### 5.4 数据流需求

上游节点必须输出结构化产物 `SemanticArtifact`，下游节点通过 `ArtifactSelector` 明确引用，不能依赖隐式自然语言拼接。

### 5.5 可观测性需求

系统需要保存：

- 节点状态
- 节点尝试次数
- 节点失败原因
- 节点 transcript
- 全局 artifacts 快照
- worker agent 执行结果

## 6. 核心数据契约

以下结构来自 [models.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/domain/models.py)。

### 6.1 计划层对象

#### `ArtifactSelector`

用于声明“当前节点需要从哪个上游节点取哪个字段”。

字段：

- `source_node_id: str` 上游节点 ID
- `field: str` 上游输出字段名
- `required: bool = True` 是否必需

#### `OutputSpec`

用于声明“当前节点应该产出什么”。

字段：

- `field: str` 输出字段名
- `artifact_type: Literal["value", "evidence", "rule", "candidate", "judgement", "other"]`
- `description: str` 输出说明
- `required: bool = True`

#### `PlanNode`

单个任务节点定义。

字段：

- `id: str`
- `goal: str`
- `evidence_from_question: list[str]`
- `inputs_from_subproblems: list[ArtifactSelector]`
- `outputs: list[OutputSpec]`
- `depends_on: list[str]`
- `agent_profile: str`
- `tool_policy: list[str]`
- `instruction: str | None`
- `metadata: dict[str, Any]`

说明：

- `depends_on` 是调度依赖，决定执行顺序
- `inputs_from_subproblems` 是数据依赖，决定输入来源
- 二者通常相关，但语义不同

#### `PlanGraph`

完整任务图。

字段：

- `question_text: str`
- `nodes: list[PlanNode]`
- `metadata: dict[str, Any]`

### 6.2 运行层对象

#### `SemanticArtifact`

节点实际产出的结构化结果。

字段：

- `field: str`
- `artifact_type: ArtifactType`
- `value: Any`
- `description: str`
- `producer_node_id: str`
- `provenance: list[str]`
- `created_at: str`

#### `RuntimeTaskPackage`

节点执行前的最终任务包，由 `TaskPackageBuilder` 组装。

字段：

- `session_id: str`
- `question_text: str`
- `node_id: str`
- `goal: str`
- `agent_profile: str`
- `local_evidence: list[str]`
- `upstream_inputs: list[SemanticArtifact]`
- `expected_outputs: list[OutputSpec]`
- `instruction: str`
- `allowed_capabilities: list[str]`
- `metadata: dict[str, Any]`

#### `NodeRuntimeState`

调度器视角的节点状态。

字段：

- `node_id: str`
- `status: Literal["pending", "ready", "running", "success", "failed"]`
- `attempt_count: int`
- `last_error: str | None`
- `started_at: str | None`
- `finished_at: str | None`

#### `NodeExecutionResult`

节点一次执行完成后返回给调度器的结果。

字段：

- `node_id: str`
- `status: Literal["success", "failed", "partial"]`
- `artifacts: list[SemanticArtifact]`
- `transcript_id: str`
- `raw_output: Any | None`
- `failure_reason: str | None`
- `retryable: bool`
- `issues: list[ValidationIssue]`

### 6.3 Transcript 与 Session 对象

#### `TranscriptEntry`

- `kind: Literal["info", "model", "capability", "agent", "result", "error"]`
- `message: str`
- `data: Any | None`
- `timestamp: str`

#### `TranscriptRecord`

- `transcript_id: str`
- `node_id: str`
- `entries: list[TranscriptEntry]`

#### `SessionSnapshot`

- `session_id: str`
- `plan: PlanGraph`
- `node_states: dict[str, NodeRuntimeState]`
- `artifacts: list[SemanticArtifact]`

#### `SchedulerRunSummary`

- `session_id: str`
- `completed_node_ids: list[str]`
- `failed_node_ids: list[str]`
- `pending_node_ids: list[str]`
- `artifacts: list[SemanticArtifact]`
- `snapshot: SessionSnapshot`

## 7. Planner 接口

相关定义位于 [contracts.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/planner/contracts.py) 与 [json_plan_parser.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/planner/json_plan_parser.py)。

### 7.1 目标

Planner 层负责把自然语言问题转换为 `PlanGraph`。

### 7.2 协议接口

#### `OnlinePlanner`

```python
async def plan(
    question_text: str,
    retrieved_cases: list[RetrievedCase],
) -> PlanGraph
```

用途：

- 根据当前问题和历史 case 生成新计划

#### `PlanningAgent`

```python
async def plan(request: PlannerRequest) -> PlannerResult
```

用途：

- 面向更高层封装的规划接口

#### `CaseRetriever`

```python
async def retrieve(question_text: str, top_k: int) -> list[RetrievedCase]
```

用途：

- 检索相似历史案例

### 7.3 Planner JSON 输入要求

`JSONPlannerResponseParser.parse(text)` 支持从 LLM 返回的 JSON 文本中解析计划图。

支持以下外层结构：

- 直接返回 plan graph 对象
- 包在 `plan_graph`
- 包在 `plan`
- 包在 `graph`

### 7.4 推荐输出格式

建议 planner 生成以下结构，便于后续接入更严格的校验器或 schema。

顶层字段：

- `question_text: str`
- `nodes: list[object]`
- `metadata: object` 可选

节点字段：

- `id: str` 必填
- `goal: str` 必填
- `evidence_from_question: list[str]` 可选
- `inputs_from_subproblems: list[object]` 可选
- `outputs: list[object]`
- `depends_on: list[str]` 可选
- `agent_profile: str` 可选
- `tool_policy: list[str]` 可选
- `instruction: str | null` 可选
- `metadata: object` 可选

输入选择器字段：

- `source_node_id: str` 必填
- `field: str` 必填
- `required: bool` 可选，默认 `true`

输出定义字段：

- `field: str` 必填
- `artifact_type: str` 可选，默认 `value`
- `description: str` 可选，默认同 `field`
- `required: bool` 可选，默认 `true`

### 7.5 当前 Parser 的兼容格式

当前实现不是严格 schema 校验，而是宽松解析。除推荐格式外，还兼容以下别名和默认行为：

- 顶层 `question_text` 缺失时，允许回退为空字符串
- `evidence` 可作为 `evidence_from_question` 的别名
- `inputs` 可作为 `inputs_from_subproblems` 的别名
- `dependencies` 可作为 `depends_on` 的别名
- `agent_type` 可作为 `agent_profile` 的别名
- `allowed_capabilities` 可作为 `tool_policy` 的别名
- `agent_profile` 和 `agent_type` 都缺失时，默认 `general_worker`
- `artifact_type` 缺失时，默认 `value`
- `description` 缺失时，默认同 `field`
- `required` 缺失时，默认 `true`

其中以下字段仍然有明确约束：

- `id: str` 必填
- `goal: str` 必填
- `outputs: list[object]`
- `instruction: str | null` 可选
- `metadata: object` 可选

输入选择器字段：

- `source_node_id: str` 必填
- `source: str` 可作为兼容别名
- `field: str` 必填
- `required: bool` 可选，默认 `true`

输出定义字段：

- `field: str` 必填
- `artifact_type: str` 可选，默认 `value`
- `description: str` 可选，默认同 `field`
- `required: bool` 可选，默认 `true`

### 7.6 Planner 输出示例

```json
{
  "question_text": "Compute the total amount raised.",
  "nodes": [
    {
      "id": "kim_amount",
      "goal": "Compute Kim's amount.",
      "evidence_from_question": [
        "Kim raises $320 more than Alexandra, who raises $430."
      ],
      "inputs_from_subproblems": [],
      "outputs": [
        {
          "field": "kim_amount",
          "artifact_type": "value",
          "description": "Kim's amount",
          "required": true
        }
      ],
      "depends_on": [],
      "agent_profile": "math_worker",
      "tool_policy": ["add_numbers"]
    }
  ]
}
```

## 8. Scheduler 接口

相关实现位于 [execution_scheduler.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/scheduler/execution_scheduler.py)。

### 8.1 核心入口

```python
summary = await scheduler.run(plan, session_id=None)
```

输入：

- `plan: PlanGraph`
- `session_id: str | None`

输出：

- `SchedulerRunSummary`

### 8.2 调度行为要求

调度器必须：

- 创建 session snapshot
- 依据依赖同步 ready 状态
- 找出 ready 节点
- 按 `max_parallel` 分批并发执行
- 节点成功时写入 artifact store
- 节点失败时交给 retry policy 决策
- 最终输出 completed / failed / pending 节点列表

### 8.3 重试策略接口

位于 [retry_policy.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/scheduler/retry_policy.py)。

协议：

```python
def decide(
    state: NodeRuntimeState,
    result: NodeExecutionResult,
) -> RetryDecision
```

默认实现：

- `FixedRetryPolicy(max_attempts=1)`

默认规则：

- 若执行成功，不重试
- 若 `result.retryable == True` 且 `attempt_count < max_attempts`，则重试
- 否则标记失败

## 9. Runtime 接口

### 9.1 TaskPackageBuilder

位于 [task_package_builder.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/runtime/task_package_builder.py)。

入口：

```python
task_package = builder.build(
    session_id=session_id,
    question_text=plan.question_text,
    node=node,
    artifact_store=artifact_store,
)
```

职责：

- 解析节点声明的上游输入
- 检查必需 artifacts 是否缺失
- 补齐默认 instruction
- 生成 `RuntimeTaskPackage`

失败条件：

- 缺少必需上游输入时抛出 `MissingArtifactsError`

### 9.2 NodeRunner

位于 [node_runner.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/runtime/node_runner.py)。

入口：

```python
result = await node_runner.run_node(
    session_id=session_id,
    plan=plan,
    node=node,
    artifact_store=artifact_store,
    attempt_count=attempt_count,
)
```

职责：

- 构建 `RuntimeTaskPackage`
- 分配 worker agent
- 把 worker 信息写入 task metadata
- 调用 `LoopEngine`
- 回传 `NodeExecutionResult`

### 9.3 LoopEngine

位于 [loop_engine.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/runtime/loop_engine.py)。

入口：

```python
result = await loop_engine.run(
    task_package=task_package,
    adapter=worker_agent,
    attempt_count=attempt_count,
)
```

职责：

- 创建 transcript
- 创建 scratchpad
- 循环调用 adapter 获取下一步意图
- 执行 capability
- 执行子 Agent 委托
- 校验完成输出
- 在超出最大轮数时失败收口

默认限制：

- `max_iterations = 6`

### 9.4 Adapter 协议

位于 [adapter.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/runtime/adapter.py)。

接口：

```python
async def run_step(request: AgentStepRequest) -> AgentStepResponse
```

其中 `AgentStepResponse` 只能是以下之一：

- `ContinueStep`
- `CapabilityCallStep`
- `SpawnAgentStep`
- `CompleteStep`
- `FailStep`

## 10. Step 级接口约束

### 10.1 `ContinueStep`

含义：

- 当前轮不完成任务，继续下一轮

字段：

- `message: str | None`

### 10.2 `CapabilityCallStep`

含义：

- 请求 LoopEngine 调用一个 capability

字段：

- `capability_name: str`
- `payload: Any`
- `save_as: str | None`
- `message: str | None`

要求：

- `capability_name` 必须在 `allowed_capabilities` 中
- capability 结果会写入 `scratchpad.capability_outputs`

### 10.3 `SpawnAgentStep`

含义：

- 请求 LoopEngine 启动一个子 Agent

字段：

- `task_goal: str`
- `requested_agent_type: str | None`
- `required_capabilities: list[str]`
- `local_evidence: list[str]`
- `provided_inputs: list[SemanticArtifact]`
- `expected_outputs: list[OutputSpec]`
- `instruction: str | None`
- `save_as: str | None`
- `wait_for_result: bool = True`
- `metadata: dict[str, Any]`
- `message: str | None`

当前限制：

- 仅支持 `wait_for_result=True`
- 若未配置 `child_agent_runtime`，则直接失败

### 10.4 `CompleteStep`

含义：

- 节点声明执行完成，并返回最终 artifacts

字段：

- `artifacts: list[SemanticArtifact]`
- `raw_output: Any | None`

要求：

- 返回结果必须通过 `OutputValidator`
- 当前 `OutputValidator` 只校验必需输出字段是否存在，以及 `artifact_type` 是否与 `OutputSpec` 一致
- 当前不会校验 `value` 的内部结构、语义正确性、`description` 内容或额外字段

### 10.5 `FailStep`

含义：

- 节点主动声明失败

字段：

- `reason: str`
- `retryable: bool = False`

## 11. Capability 接口

Capability 的正式协议定义在 [base.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/capabilities/base.py)。

一个 capability 至少需要提供：

- `name`
- `description`
- `async invoke(payload, context)`

示例：

```python
class AddNumbersCapability:
    name = "add_numbers"
    description = "Add a list of numeric values."

    async def invoke(self, payload, context):
        values = payload["values"]
        return float(sum(values))
```

运行时上下文 `CapabilityInvocationContext` 会包含：

- `session_id`
- `node_id`
- `attempt_count`
- `transcript_id`

能力接入要求：

- 必须先注册到 `CapabilityRegistry`
- 必须被节点 `tool_policy` 明确允许
- capability 内异常会被视为节点失败

## 12. 存储接口

### 12.1 ArtifactStore

位于 [artifact_store.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/storage/artifact_store.py)。

核心能力：

- `put(artifact)`
- `put_many(artifacts)`
- `get(source_node_id, field)`
- `list_all()`
- `list_by_node(node_id)`
- `resolve_inputs(selectors)`

需求说明：

- 按 `(producer_node_id, field)` 唯一定位 artifact
- 需要支持节点输入解析

### 12.2 SessionStore

位于 [session_store.py](/d:/荔枝/OneDrive/丰富/Agent/claude-code/TaskCall—PerceptionMap/taskcall_perception_map/storage/session_store.py)。

核心能力：

- `create(plan, session_id=None)`
- `get(session_id)`
- `update_node_state(session_id, state)`
- `replace_artifacts(session_id, artifacts)`
- `list_sessions()`

需求说明：

- 保存全局 session 快照
- 对外返回副本，避免调用方直接篡改内部状态

### 12.3 TranscriptStore

从 LoopEngine 的使用方式可知，transcript store 需要支持：

- 创建 transcript
- 追加日志 entry
- 获取单条 transcript
- 查询 transcript 列表

## 13. 子 Agent 需求

系统支持在一个节点执行过程中委托子 Agent 完成部分任务。

要求：

- 子 Agent 必须有独立 identity
- 子 Agent 的输入必须结构化传入
- 子 Agent 也走统一 LoopEngine
- 子 Agent 执行结果回填到父节点 scratchpad
- 父节点可继续使用子 Agent 产物完成自身输出

当前版本限制：

- 仅支持同步等待子 Agent 结果
- 子 Agent 路由由 `AgentRegistry` 和 `WorkerAgentManager` 负责

## 14. 成功与失败判定

### 14.1 节点成功

节点满足以下条件时记为成功：

- adapter 返回 `CompleteStep`
- `OutputValidator` 校验通过

说明：

- 这里的“校验通过”目前只表示输出字段齐全且 `artifact_type` 匹配，不代表结果值已经过更深层的业务校验

### 14.2 节点失败

以下任一情况会导致节点失败：

- capability 调用异常
- 子 Agent 执行异常
- 子 Agent 返回非 success
- 输出校验失败
- adapter 返回 `FailStep`
- 超过最大迭代次数
- 缺少必需上游输入

### 14.3 全局运行结束

Scheduler 在以下情况停止：

- 没有任何 ready 节点

此时可能有三种结果：

- 全部完成
- 部分失败
- 因上游失败导致部分节点永久 pending

## 15. 典型接入方式

### 15.1 最小运行链路

1. 构建 `PlanGraph`
2. 注册 capabilities
3. 初始化 transcript / artifact / session / worker agent store
4. 初始化 `LoopEngine`
5. 初始化 `NodeRunner`
6. 初始化 `ExecutionScheduler`
7. 调用 `await scheduler.run(plan)`

### 15.2 最小对接代码骨架

```python
plan = ...

capability_registry = CapabilityRegistry()
capability_registry.register(MyCapability())

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
```

说明：

- `build_worker_agent` 需要由接入方提供，用于根据 `RuntimeTaskPackage` 和 `WorkerAgentIdentity` 返回具体的 worker agent
- 如果节点内会使用 `SpawnAgentStep`，还需要额外配置 `AgentRegistry`、`NestedAgentRuntime` 和 child-agent 相关的 worker 实现

## 16. 非功能性要求

- 类型化数据流必须贯穿 planner、runtime、scheduler
- 节点执行过程必须可追踪
- 失败原因必须可回溯
- 数据结构应支持后续替换为持久化存储
- planner、runtime、capability 必须保持解耦

## 17. 后续建议

如果要把这个原型升级成更完整的产品版本，建议优先补齐以下能力：

- 增加统一的外部调用入口
- 为 `PlanGraph` 增加结构校验和循环依赖校验
- 把内存 store 替换为可持久化实现
- 为 transcript 和 artifact 增加查询接口
- 为 planner 增加严格的 JSON schema
- 增加 session 级恢复能力
- 增加异步子 Agent 与超时控制
