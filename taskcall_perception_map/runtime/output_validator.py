"""Validation of node outputs against the plan's declared contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from taskcall_perception_map.domain.models import (
    RuntimeTaskPackage,
    SemanticArtifact,
    ValidationIssue,
)


@dataclass(slots=True)
class ValidationResult:
    """Boolean outcome plus the list of concrete contract violations."""

    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


class OutputValidator:
    """Check that returned artifacts satisfy required fields and types."""

    def validate(
        self,
        task_package: RuntimeTaskPackage,
        artifacts: list[SemanticArtifact],
    ) -> ValidationResult:
        # Output validation is intentionally simple here: it enforces the
        # declared schema but does not inspect the semantic correctness of data.
        by_field = {artifact.field: artifact for artifact in artifacts}
        issues: list[ValidationIssue] = []

        for output_spec in task_package.expected_outputs:
            artifact = by_field.get(output_spec.field)
            if artifact is None:
                if output_spec.required:
                    issues.append(
                        ValidationIssue(
                            field=output_spec.field,
                            message=f"Missing required output field '{output_spec.field}'.",
                        )
                    )
                continue

            if artifact.artifact_type != output_spec.artifact_type:
                issues.append(
                    ValidationIssue(
                        field=output_spec.field,
                        message=(
                            f"Output field '{output_spec.field}' has type "
                            f"'{artifact.artifact_type}' but expected "
                            f"'{output_spec.artifact_type}'."
                        ),
                    )
                )

        return ValidationResult(ok=not issues, issues=issues)
