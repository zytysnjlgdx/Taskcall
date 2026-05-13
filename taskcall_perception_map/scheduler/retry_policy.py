"""节点失败后的重试策略。

调度器本身不决定“该不该重试”，而是把这个判断委托给 policy。
这样以后你可以很容易替换成：
- 固定次数重试
- 指数退避
- 按错误类型决定是否重试
- 按节点类型决定是否重试
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from taskcall_perception_map.domain.models import NodeExecutionResult, NodeRuntimeState


@dataclass(slots=True)
class RetryDecision:
    """一次失败评估后的决策结果。"""

    should_retry: bool
    reason: str | None = None


class RetryPolicy(Protocol):
    """重试策略协议，方便后面替换具体实现。"""

    def decide(
        self,
        state: NodeRuntimeState,
        result: NodeExecutionResult,
    ) -> RetryDecision:
        ...


@dataclass(slots=True)
class FixedRetryPolicy:
    """最简单的固定次数重试策略。"""

    max_attempts: int = 1

    def decide(
        self,
        state: NodeRuntimeState,
        result: NodeExecutionResult,
    ) -> RetryDecision:
        # 成功了就不需要重试。
        if result.status == "success":
            return RetryDecision(should_retry=False)
        # “这个错误能不能重试”由 runtime 先给一个语义判断，
        # policy 再叠加“最多重试几次”的数量限制。
        if result.retryable and state.attempt_count < self.max_attempts:
            return RetryDecision(
                should_retry=True,
                reason=f"Retryable failure on attempt {state.attempt_count}.",
            )
        return RetryDecision(should_retry=False)
