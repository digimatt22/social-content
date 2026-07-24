from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import time

from ..db import create_db_engine, init_db, session_factory, session_scope
from ..services.durable_jobs import (
    claim_next_job,
    fail_job,
    mark_running,
    heartbeat_job,
    reclaim_expired_leases,
    reconcile_run,
    succeed_job,
)
from ..services.job_handlers import (
    AmbiguousExternalWriteError,
    NonRetryableJobError,
    default_registry,
)


def run_worker(*, once: bool = False, poll_seconds: float = 2.0, lease_seconds: int = 120) -> int:
    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    registry = default_registry()
    stopping = threading.Event()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def request_stop(_signum, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        while not stopping.is_set():
            with session_scope(factory) as session:
                reclaim_expired_leases(session)
                claimed = claim_next_job(session, worker_id=worker_id, lease_seconds=lease_seconds)
            if claimed is None:
                if once:
                    return 0
                stopping.wait(poll_seconds)
                continue
            handler = registry.resolve(claimed.job_type, claimed.schema_version)
            if handler is None:
                with session_scope(factory) as session:
                    mark_running(session, job_id=claimed.id, worker_id=worker_id)
                    fail_job(
                        session,
                        job_id=claimed.id,
                        worker_id=worker_id,
                        error_code="unknown_handler_schema",
                        error_message=f"No handler for {claimed.job_type} v{claimed.schema_version}",
                        retryable=False,
                        ambiguous_external_write=True,
                    )
                continue
            try:
                with session_scope(factory) as session:
                    mark_running(session, job_id=claimed.id, worker_id=worker_id)
                heartbeat_stop = threading.Event()
                heartbeat_failures: list[Exception] = []

                def keep_lease() -> None:
                    interval = max(lease_seconds / 3, 1)
                    while not heartbeat_stop.wait(interval):
                        try:
                            with session_scope(factory) as session:
                                heartbeat_job(
                                    session,
                                    job_id=claimed.id,
                                    worker_id=worker_id,
                                    lease_seconds=lease_seconds,
                                )
                        except Exception as exc:
                            heartbeat_failures.append(exc)
                            heartbeat_stop.set()

                heartbeat_thread = threading.Thread(target=keep_lease, daemon=True)
                heartbeat_thread.start()
                try:
                    result = handler.function(claimed.payload)
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join(timeout=max(lease_seconds / 3, 1) + 1)
                if heartbeat_failures:
                    raise RuntimeError(f"job heartbeat failed: {heartbeat_failures[0]}")
                with session_scope(factory) as session:
                    succeed_job(session, job_id=claimed.id, worker_id=worker_id, result=result)
                    if claimed.run_id is not None:
                        reconcile_run(session, claimed.run_id)
            except AmbiguousExternalWriteError as exc:
                _record_failure(factory, claimed.id, worker_id, "ambiguous_write", str(exc), True, True)
            except NonRetryableJobError as exc:
                _record_failure(factory, claimed.id, worker_id, "nonretryable", str(exc), False, False)
            except Exception as exc:
                _record_failure(factory, claimed.id, worker_id, "handler_error", str(exc), True, False)
            if once:
                return 0
    finally:
        engine.dispose()
    return 0


def _record_failure(factory, job_id, worker_id, code, message, retryable, ambiguous) -> None:
    with session_scope(factory) as session:
        job = fail_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            error_code=code,
            error_message=message,
            retryable=retryable,
            ambiguous_external_write=ambiguous,
        )
        if job.run_id is not None:
            reconcile_run(session, job.run_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the durable Marketing OS worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    return run_worker(once=args.once, poll_seconds=args.poll_seconds, lease_seconds=args.lease_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
