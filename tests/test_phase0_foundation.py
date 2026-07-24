from __future__ import annotations

import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select

from marketing_os.db import create_db_engine, init_db, require_current_schema, session_factory
from marketing_os.db_models import (
    AutomationJobRecord,
    AuditEventRecord,
    Base,
    DemandEvidenceRecord,
    OperatorSessionRecord,
    PrincipalRecord,
    ProductRecord,
    ServiceCredentialRecord,
    utc_now,
)
from marketing_os.jobs.durable_scheduler import emit_due_jobs
from marketing_os.jobs.migrate_sqlite_to_postgres import migrate, plan_migration
from marketing_os.jobs.operational_status import collect_status
from marketing_os.secure_app import create_secure_app
from marketing_os.services.auth import (
    authenticate_password,
    change_password,
    create_principal,
    create_service_credential,
)
from marketing_os.services.capability_preflight import capability_report
from marketing_os.services.durable_jobs import cancel_job, enqueue_job
from marketing_os.services.growth_contracts import (
    evidence_signal_state,
    funnel_contract_complete,
    record_growth_event,
    tracked_destination_url,
)
from marketing_os.services.product_identity import reconcile_product_identities


class Phase0FoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_alembic_baseline_versions_empty_database(self) -> None:
        baseline = Path(
            "migrations/versions/0001_service_foundation_service_foundation_baseline.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Base.metadata", baseline)
        path = self.root / "migrated.sqlite"
        url = f"sqlite:///{path}"
        config = Config("alembic.ini")
        with patch.dict(os.environ, {"MARKETING_OS_DB_URL": url}):
            command.upgrade(config, "head")
        engine = create_engine(url, future=True)
        require_current_schema(engine)
        self.assertIn("automation_jobs", set(inspect(engine).get_table_names()))
        engine.dispose()

    def test_cutover_dry_run_and_copy_preserve_ids(self) -> None:
        source = create_engine(f"sqlite:///{self.root / 'source.sqlite'}", future=True)
        destination = create_engine(f"sqlite:///{self.root / 'destination.sqlite'}", future=True)
        Base.metadata.create_all(source)
        Base.metadata.create_all(destination)
        with source.begin() as connection:
            connection.execute(
                ProductRecord.__table__.insert(),
                {
                    "id": 41,
                    "name": "Mapped product",
                    "secondary_audiences_json": "[]",
                    "best_channels_json": "[]",
                    "use_cases_json": "[]",
                    "seasonality_json": "[]",
                    "sales_momentum_note": "",
                    "external_source": "etsy",
                    "external_id": "987",
                    "canonical_url": "https://example.test/listing/987",
                    "sync_status": "synced",
                    "sync_error": "",
                    "staleness_state": "fresh",
                    "manual_override_state": "",
                    "manual_override_note": "",
                    "updated_at": utc_now(),
                },
            )
        dry_run = plan_migration(source, destination)
        product_plan = next(item for item in dry_run if item.table == "products")
        self.assertEqual((1, 0, ""), (product_plan.source_rows, product_plan.destination_rows_before, product_plan.conflict))
        report = migrate(source, destination)
        product_report = next(item for item in report if item.table == "products")
        self.assertEqual((1, 1), (product_report.copied_rows, product_report.destination_rows_after))
        with destination.connect() as connection:
            copied = connection.execute(select(ProductRecord)).scalar_one()
            self.assertEqual(41, copied)
        source.dispose()
        destination.dispose()

    def test_scheduler_emission_is_idempotent(self) -> None:
        engine = create_db_engine(self.root / "jobs.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        now = utc_now().replace(hour=3, minute=12, second=0, microsecond=0)
        self.assertEqual(5, emit_due_jobs(factory, now))
        self.assertEqual(1, emit_due_jobs(factory, now + timedelta(minutes=20)))
        engine.dispose()

    def test_operational_status_enforces_queue_and_lease_attention_contract(self) -> None:
        engine = create_db_engine(self.root / "status.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        now = utc_now()
        with factory.begin() as session:
            queued, _ = enqueue_job(
                session,
                job_type="system.noop",
                scheduled_at=now - timedelta(minutes=20),
            )
            expired, _ = enqueue_job(session, job_type="system.noop")
            expired.state = "running"
            expired.lease_owner = "worker-1"
            expired.lease_expires_at = now - timedelta(seconds=1)
            expired.heartbeat_at = now - timedelta(minutes=5)
            session.flush()
            queued_id, expired_id = queued.id, expired.id

        report = collect_status(factory, attention_seconds=900)
        self.assertEqual("attention_required", report["status"])
        self.assertTrue(report["queue_attention"])
        self.assertGreaterEqual(report["queue_lag_seconds"], 1200)
        self.assertEqual(1, report["expired_leases"])

        with factory.begin() as session:
            session.delete(session.get(AutomationJobRecord, queued_id))
            session.delete(session.get(AutomationJobRecord, expired_id))
        healthy = collect_status(factory, attention_seconds=900)
        self.assertEqual("ok", healthy["status"])
        engine.dispose()

    def test_job_control_requires_active_admin(self) -> None:
        engine = create_db_engine(self.root / "control.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        with factory.begin() as session:
            viewer = PrincipalRecord(principal_type="human", username="viewer", roles_json='["viewer"]')
            session.add(viewer)
            session.flush()
            job, _ = enqueue_job(session, job_type="system.noop")
            viewer_id, job_id = viewer.id, job.id
        with factory.begin() as session:
            with self.assertRaises(PermissionError):
                cancel_job(session, job_id=job_id, principal_id=viewer_id, reason="not mine")
        with factory() as session:
            denied = session.scalar(select(AuditEventRecord).where(AuditEventRecord.event_type == "automation_job_cancel_denied"))
            self.assertIsNotNone(denied)
        engine.dispose()

    def test_secure_app_denies_anonymous_and_enforces_csrf_and_roles(self) -> None:
        db_path = self.root / "secure.sqlite"
        with patch.dict(
            os.environ,
            {"MARKETING_OS_SECRET": "test-secret-that-is-long-and-random-enough"},
            clear=False,
        ):
            app = create_secure_app(str(db_path), bootstrap_data=False)
        app.config.update(TESTING=True)
        factory = app.config["SESSION_FACTORY"]
        with factory.begin() as session:
            create_principal(session, username="operator", password="correct horse battery staple", roles={"operator", "viewer"})
            admin = create_principal(
                session,
                username="admin-token-owner",
                password="correct horse battery staple",
                roles={"admin"},
            )
            raw_admin_service, _ = create_service_credential(
                session,
                admin,
                scopes={"read"},
            )
            service = PrincipalRecord(
                principal_type="service",
                username="test-service",
                roles_json='["service"]',
                password_hash="",
            )
            session.add(service)
            session.flush()
            raw_service, credential = create_service_credential(session, service, scopes={"read"})
            credential_id = credential.id

        client = app.test_client()
        adapter = app.url_map.bind("localhost")
        for rule in app.url_map.iter_rules():
            if rule.endpoint in {"health", "ready", "login", "static"}:
                continue
            values = {argument: 1 for argument in rule.arguments}
            path = adapter.build(rule.endpoint, values=values)
            method = "GET" if "GET" in rule.methods else next(
                candidate for candidate in rule.methods if candidate not in {"HEAD", "OPTIONS"}
            )
            anonymous = client.open(path, method=method, base_url="https://localhost")
            expected = 401 if path.startswith("/api/") else 302
            self.assertEqual(expected, anonymous.status_code, f"{method} {path}")
        self.assertEqual(302, client.get("/", base_url="https://localhost").status_code)
        self.assertEqual(200, client.get("/health", base_url="https://localhost").status_code)
        self.assertEqual(
            403,
            client.post(
                "/auth/login",
                data={
                    "username": "operator",
                    "password": "correct horse battery staple",
                    "_login_csrf": "forged",
                },
                base_url="https://localhost",
            ).status_code,
        )
        client.get("/auth/login", base_url="https://localhost")
        login_csrf = client.get_cookie("marketing_os_login_csrf").value
        response = client.post(
            "/auth/login",
            data={
                "username": "operator",
                "password": "correct horse battery staple",
                "_login_csrf": login_csrf,
            },
            base_url="https://localhost",
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual(200, client.get("/", base_url="https://localhost").status_code)
        self.assertEqual(403, client.post("/auth/logout", base_url="https://localhost").status_code)
        csrf = client.get_cookie("marketing_os_csrf").value
        client.set_cookie("marketing_os_csrf", "attacker-chosen-token", domain="localhost")
        self.assertEqual(
            403,
            client.post(
                "/auth/logout",
                headers={"X-CSRF-Token": "attacker-chosen-token"},
                base_url="https://localhost",
            ).status_code,
        )
        client.set_cookie("marketing_os_csrf", csrf, domain="localhost")
        self.assertEqual(
            302,
            client.post(
                "/auth/logout",
                headers={"X-CSRF-Token": csrf},
                base_url="https://localhost",
            ).status_code,
        )
        self.assertEqual(
            200,
            client.get(
                "/api/today",
                headers={"Authorization": f"Bearer {raw_service}"},
                base_url="https://localhost",
            ).status_code,
        )
        self.assertEqual(
            403,
            client.post(
                "/api/tasks/1/status",
                headers={"Authorization": f"Bearer {raw_service}"},
                base_url="https://localhost",
            ).status_code,
        )
        self.assertEqual(
            403,
            client.post(
                "/api/tasks/1/status",
                headers={"Authorization": f"Bearer {raw_admin_service}"},
                base_url="https://localhost",
            ).status_code,
        )
        with factory.begin() as session:
            credential = session.get(ServiceCredentialRecord, credential_id)
            credential.revoked_at = utc_now()
        self.assertEqual(
            401,
            client.get(
                "/api/today",
                headers={"Authorization": f"Bearer {raw_service}"},
                base_url="https://localhost",
            ).status_code,
        )
        factory.kw["bind"].dispose()

    def test_expired_session_is_rejected(self) -> None:
        db_path = self.root / "expired.sqlite"
        with patch.dict(os.environ, {"MARKETING_OS_SECRET": "another-test-secret-long-enough"}, clear=False):
            app = create_secure_app(str(db_path), bootstrap_data=False)
        app.config.update(TESTING=True)
        factory = app.config["SESSION_FACTORY"]
        with factory.begin() as session:
            create_principal(session, username="admin", password="correct horse battery staple", roles={"admin"})
        client = app.test_client()
        client.get("/auth/login", base_url="https://localhost")
        login_csrf = client.get_cookie("marketing_os_login_csrf").value
        client.post(
            "/auth/login",
            data={
                "username": "admin",
                "password": "correct horse battery staple",
                "_login_csrf": login_csrf,
            },
            base_url="https://localhost",
        )
        with factory.begin() as session:
            record = session.scalar(select(OperatorSessionRecord))
            record.idle_expires_at = utc_now() - timedelta(seconds=1)
        self.assertEqual(302, client.get("/", base_url="https://localhost").status_code)
        factory.kw["bind"].dispose()

    def test_product_identity_and_funnel_contract(self) -> None:
        engine = create_db_engine(self.root / "contracts.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        with factory.begin() as session:
            product = ProductRecord(
                name="Mapped duck",
                external_source="etsy",
                external_id="12345",
                canonical_url="https://etsy.test/listing/12345/mapped-duck",
            )
            session.add(product)
        with factory.begin() as session:
            report = reconcile_product_identities(
                session,
                [{"id": 77, "etsyUrl": "https://etsy.test/listing/12345/mapped-duck"}],
            )
            self.assertEqual((1, []), (report["mapped"], report["exceptions"]))
            tracked = tracked_destination_url(
                "https://mattmademe.test/product/77",
                campaign_id="camp-1",
                content_id="content-1",
                publication_id="pin-1",
            )
            event, created = record_growth_event(
                session,
                {
                    "event_id": "event-1",
                    "event_type": "etsy_outbound_click",
                    "campaign_id": "camp-1",
                    "content_id": "content-1",
                    "publication_id": "pin-1",
                    "product_id": 1,
                    "source_timestamp": utc_now(),
                    "destination_url": tracked,
                    "attribution_quality": "utm_complete",
                },
            )
            self.assertTrue(created)
            self.assertTrue(funnel_contract_complete(event))
            duplicate, duplicate_created = record_growth_event(
                session,
                {
                    "event_id": "event-1",
                    "event_type": "etsy_outbound_click",
                    "source_timestamp": utc_now(),
                },
            )
            self.assertFalse(duplicate_created)
            self.assertEqual(event.id, duplicate.id)
        engine.dispose()

    def test_stale_evidence_is_not_a_negative_signal(self) -> None:
        now = utc_now()
        evidence = DemandEvidenceRecord(
            source_name="manual",
            evidence_type="topic",
            topic="gift idea",
            deduplication_key="manual:gift-idea",
            confidence="low",
            evidence_state="observed",
            source_timestamp=now - timedelta(days=3),
        )
        self.assertEqual("stale", evidence_signal_state(evidence, now=now))
        evidence.evidence_state = "hypothesis"
        self.assertEqual("hypothesis", evidence_signal_state(evidence, now=now))

    def test_capability_preflight_reports_safe_degraded_mode(self) -> None:
        report = capability_report("pinterest_publish", {})
        self.assertFalse(report["ready"])
        self.assertEqual("publishing_disabled", report["degraded_mode"])
        ready = capability_report(
            "foundation",
            {
                "MARKETING_OS_DB_URL": "postgresql+psycopg://example",
                "MARKETING_OS_SECRET": "configured",
            },
        )
        self.assertTrue(ready["ready"])

    def test_production_auth_refuses_sqlite_and_incomplete_proxy_contract(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MARKETING_OS_ENV": "production",
                "MARKETING_OS_SECRET": "production-test-secret-long-enough",
                "MARKETING_OS_DB_URL": f"sqlite:///{self.root / 'unsafe.sqlite'}",
                "MARKETING_OS_TRUSTED_HOSTS": "marketing.example.test",
                "MARKETING_OS_PROXY_HOPS": "1",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "requires PostgreSQL"):
                create_secure_app(bootstrap_data=False)

    def test_all_production_processes_refuse_sqlite_fallback(self) -> None:
        target = self.root / "must-not-exist.sqlite"
        with patch.dict(
            os.environ,
            {
                "MARKETING_OS_ENV": "production",
                "MARKETING_OS_DB_URL": f"sqlite:///{target}",
            },
            clear=False,
        ):
            engine = create_db_engine()
            with self.assertRaisesRegex(RuntimeError, "require PostgreSQL"):
                init_db(engine)
            engine.dispose()
        self.assertFalse(target.exists())

    def test_restore_script_requires_attestation_checksum_and_authority_override(self) -> None:
        script = Path("scripts/postgres-restore.sh").read_text(encoding="utf-8")
        self.assertIn("MARKETING_OS_RESTORE_TARGET_CLASS", script)
        self.assertIn("shasum -a 256 -c", script)
        self.assertIn("YES_I_ACCEPT_DATA_LOSS", script)
        self.assertIn("inet_server_addr()", script)

    def test_password_change_revokes_existing_sessions(self) -> None:
        engine = create_db_engine(self.root / "password.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        with factory.begin() as session:
            principal = create_principal(
                session,
                username="owner",
                password="old password long enough",
                roles={"admin"},
            )
            from marketing_os.services.auth import create_operator_session

            create_operator_session(session, principal)
        with factory.begin() as session:
            principal = session.scalar(select(PrincipalRecord).where(PrincipalRecord.username == "owner"))
            change_password(
                session,
                principal,
                current_password="old password long enough",
                new_password="new password long enough",
            )
        with factory() as session:
            record = session.scalar(select(OperatorSessionRecord))
            self.assertIsNotNone(record.revoked_at)
            self.assertEqual("password_changed", record.revoke_reason)
        engine.dispose()

    def test_repeated_login_failures_lock_account(self) -> None:
        engine = create_db_engine(self.root / "lockout.sqlite")
        init_db(engine)
        factory = session_factory(engine)
        with factory.begin() as session:
            create_principal(
                session,
                username="locked-owner",
                password="correct password long enough",
                roles={"admin"},
            )
        for _ in range(5):
            with factory.begin() as session:
                self.assertIsNone(authenticate_password(session, "locked-owner", "wrong"))
        with factory.begin() as session:
            self.assertIsNone(
                authenticate_password(session, "locked-owner", "correct password long enough")
            )
            principal = session.scalar(
                select(PrincipalRecord).where(PrincipalRecord.username == "locked-owner")
            )
            self.assertIsNotNone(principal.locked_until)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
