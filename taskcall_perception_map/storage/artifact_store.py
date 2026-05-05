"""In-memory storage for structured artifacts passed between nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from taskcall_perception_map.domain.models import ArtifactSelector, SemanticArtifact


@dataclass(slots=True)
class ResolvedInputs:
    """Result of resolving a node's upstream artifact selectors."""

    artifacts: list[SemanticArtifact] = field(default_factory=list)
    missing: list[ArtifactSelector] = field(default_factory=list)


class InMemoryArtifactStore:
    """Store artifacts by (producer node id, field) for deterministic lookup."""

    def __init__(self) -> None:
        self._artifacts: dict[tuple[str, str], SemanticArtifact] = {}

    def put(self, artifact: SemanticArtifact) -> None:
        """Insert or replace one artifact for a node field."""
        key = (artifact.producer_node_id, artifact.field)
        self._artifacts[key] = artifact

    def put_many(self, artifacts: list[SemanticArtifact]) -> None:
        """Persist a batch of artifacts produced by one successful node run."""
        for artifact in artifacts:
            self.put(artifact)

    def get(self, source_node_id: str, field: str) -> SemanticArtifact | None:
        """Fetch one artifact by the upstream node id and output field."""
        return self._artifacts.get((source_node_id, field))

    def list_all(self) -> list[SemanticArtifact]:
        """Return every artifact currently known to the session."""
        return list(self._artifacts.values())

    def list_by_node(self, node_id: str) -> list[SemanticArtifact]:
        """Return all artifacts produced by a single node."""
        return [
            artifact
            for (source_node_id, _field), artifact in self._artifacts.items()
            if source_node_id == node_id
        ]

    def resolve_inputs(self, selectors: list[ArtifactSelector]) -> ResolvedInputs:
        """Resolve all upstream references needed to build a task package."""
        resolved = ResolvedInputs()
        for selector in selectors:
            artifact = self.get(selector.source_node_id, selector.field)
            if artifact is None:
                if selector.required:
                    resolved.missing.append(selector)
                continue
            resolved.artifacts.append(artifact)
        return resolved
