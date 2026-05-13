"""内存级产物存储，用于在节点之间传递结构化结果。"""

from __future__ import annotations

from dataclasses import dataclass, field

from taskcall_perception_map.domain.models import ArtifactSelector, SemanticArtifact


@dataclass(slots=True)
class ResolvedInputs:
    """
    输入解析结果：把 ArtifactSelector 列表解析成实际的 SemanticArtifact 列表。

    字段:
        artifacts: 成功解析到的产物列表
        missing:   未找到的、但标记为 required 的 selector 列表
    """

    artifacts: list[SemanticArtifact] = field(default_factory=list)
    missing: list[ArtifactSelector] = field(default_factory=list)


class InMemoryArtifactStore:
    """
    内存级产物仓库，以 (producer_node_id, field) 为 key 存储所有节点的输出。

    作用：节点执行完成后把产出的 SemanticArtifact 存进来，下游节点需要输入时
         拿着 ArtifactSelector（source_node_id + field）来取。

    内部结构：
        _artifacts = {
            ("q1", "total_pounds"): SemanticArtifact(...),
            ("q1", "kim_amount"):   SemanticArtifact(...),
            ("q2", "total_cost"):   SemanticArtifact(...),
        }
    """

    def __init__(self) -> None:
        self._artifacts: dict[tuple[str, str], SemanticArtifact] = {}

    def put(self, artifact: SemanticArtifact) -> None:
        """
        存入一个产物，已存在则覆盖。

        输入:
            artifact: 节点产出的 SemanticArtifact（包含 producer_node_id 和 field）
        """
        key = (artifact.producer_node_id, artifact.field)
        self._artifacts[key] = artifact

    def put_many(self, artifacts: list[SemanticArtifact]) -> None:
        """
        批量存入一个节点产出的所有产物。

        输入:
            artifacts: 某节点一次执行产出的所有 SemanticArtifact 列表
        """
        for artifact in artifacts:
            self.put(artifact)

    def get(self, source_node_id: str, field: str) -> SemanticArtifact | None:
        """
        按节点 id 和字段名取一个产物。

        输入:
            source_node_id: 产出该产物的节点 id
            field:          产物字段名

        输出:
            找到则返回 SemanticArtifact，找不到返回 None
        """
        return self._artifacts.get((source_node_id, field))

    def list_all(self) -> list[SemanticArtifact]:
        """返回当前仓库中所有产物。"""
        return list(self._artifacts.values())

    def list_by_node(self, node_id: str) -> list[SemanticArtifact]:
        """
        返回某个节点产出的所有产物。

        输入:
            node_id: 节点 id

        输出:
            该节点产出的所有 SemanticArtifact 列表
        """
        return [
            artifact
            for (source_node_id, _field), artifact in self._artifacts.items()
            if source_node_id == node_id
        ]

    def resolve_inputs(self, selectors: list[ArtifactSelector]) -> ResolvedInputs:
        """
        解析一个节点的所有输入引用：拿着 ArtifactSelector 去仓库里找实际产物。

        输入:
            selectors: 节点的 inputs_from_subproblems（ArtifactSelector 列表）

        输出:
            ResolvedInputs:
                artifacts: 成功找到的产物列表
                missing:   未找到但 required=True 的 selector 列表
        """
        resolved = ResolvedInputs()
        for selector in selectors:
            artifact = self.get(selector.source_node_id, selector.field)  # get 的返回类型是 SemanticArtifact | None。找到就是 SemanticArtifact，找不到就是 None
            if artifact is None:
                if selector.required:
                    resolved.missing.append(selector)
                continue
            resolved.artifacts.append(artifact)
        return resolved
