from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


JobHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


class NonRetryableJobError(RuntimeError):
    pass


class AmbiguousExternalWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegisteredHandler:
    job_type: str
    schema_version: int
    function: JobHandler


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, int], RegisteredHandler] = {}

    def register(self, job_type: str, schema_version: int, function: JobHandler) -> None:
        key = (job_type, schema_version)
        if key in self._handlers:
            raise ValueError(f"handler already registered: {job_type} v{schema_version}")
        self._handlers[key] = RegisteredHandler(job_type, schema_version, function)

    def resolve(self, job_type: str, schema_version: int) -> RegisteredHandler | None:
        return self._handlers.get((job_type, schema_version))


def default_registry() -> HandlerRegistry:
    from ..jobs.coverage_intelligence import (
        catalog_reconcile_handler,
        coverage_materialize_handler,
        editorial_reconcile_handler,
        measurement_ingest_handler,
    )

    registry = HandlerRegistry()
    registry.register("system.noop", 1, lambda payload: {"echo": payload})
    registry.register("catalog.reconcile", 1, catalog_reconcile_handler)
    registry.register("editorial.reconcile", 1, editorial_reconcile_handler)
    registry.register("coverage.materialize", 1, coverage_materialize_handler)
    registry.register("measurement.ingest", 1, measurement_ingest_handler)
    return registry
