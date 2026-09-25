from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from marketing_os.db import session_scope
from marketing_os.db_models import AssetRecord, AutomationJobRecord, CreativeGenerationJobRecord, ProductRecord
from marketing_os.magnific_api import (
    MagnificApiConfig,
    MagnificClient,
    MagnificReferenceImage,
    https_asset_url,
    magnific_api_configured,
)
from marketing_os.services.art_studio import (
    art_studio_provider_status_label,
    enqueue_social_image_generation,
)
from marketing_os.services.job_handlers import NonRetryableJobError, default_registry
from marketing_os.web_app import create_app


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MagnificApiClientTests(unittest.TestCase):
    def test_configured_flag_and_https_url_helper(self) -> None:
        with patch.dict("os.environ", {"MAGNIFIC_API_KEY": ""}, clear=False):
            self.assertFalse(magnific_api_configured())
        with patch.dict("os.environ", {"MAGNIFIC_API_KEY": "test-key-not-real"}, clear=False):
            self.assertTrue(magnific_api_configured())
        self.assertEqual(
            https_asset_url("https://i.etsystatic.com/a.jpg", "/local/path.jpg"),
            "https://i.etsystatic.com/a.jpg",
        )
        self.assertIsNone(https_asset_url("/local/only.jpg", "http://insecure.example/a.jpg"))

    def test_create_and_poll_task_with_mocked_http(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_urlopen(request: Request, timeout: float = 0):
            method = request.get_method()
            url = request.full_url
            calls.append((method, url))
            headers = {k.lower(): v for k, v in request.header_items()}
            if "api.magnific.com" in url:
                self.assertEqual(headers.get("x-magnific-api-key"), "test-key-not-real")
            self.assertNotIn("test-key-not-real", url)
            if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                body = json.loads(request.data.decode("utf-8"))
                self.assertEqual(body["aspect_ratio"], "1:1")
                self.assertEqual(len(body["reference_images"]), 1)
                return _FakeResponse(
                    json.dumps(
                        {
                            "data": {
                                "task_id": "task-123",
                                "status": "IN_PROGRESS",
                                "generated": [],
                            }
                        }
                    ).encode()
                )
            if method == "GET" and url.endswith("/nano-banana-pro-flash/task-123"):
                return _FakeResponse(
                    json.dumps(
                        {
                            "data": {
                                "task_id": "task-123",
                                "status": "COMPLETED",
                                "generated": ["https://cdn.example/out.png"],
                            }
                        }
                    ).encode()
                )
            if method == "GET" and url == "https://cdn.example/out.png":
                return _FakeResponse(TINY_PNG)
            raise AssertionError(f"unexpected request {method} {url}")

        client = MagnificClient(
            MagnificApiConfig(api_key="test-key-not-real"),
            opener=fake_urlopen,
        )
        created = client.create_nano_banana_pro_flash(
            prompt="duck scene",
            reference_images=[
                MagnificReferenceImage(
                    image="https://i.etsystatic.com/ref.jpg",
                    text="Primary",
                    mime_type="image/jpeg",
                )
            ],
        )
        self.assertEqual(created.task_id, "task-123")
        finished = client.wait_for_nano_banana_pro_flash(
            created.task_id,
            poll_seconds=0.01,
            timeout_seconds=1.0,
            sleeper=lambda _s: None,
        )
        self.assertTrue(finished.completed)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.png"
            client.download_to_path(finished.generated[0], dest)
            self.assertEqual(dest.read_bytes(), TINY_PNG)
        self.assertEqual(calls[0][0], "POST")
        self.assertTrue(any(method == "GET" and "task-123" in url for method, url in calls))

    def test_http_error_is_retryable_for_503(self) -> None:
        def fake_urlopen(request: Request, timeout: float = 0):
            raise HTTPError(request.full_url, 503, "Unavailable", hdrs=None, fp=io.BytesIO(b'{"message":"busy"}'))

        client = MagnificClient(MagnificApiConfig(api_key="test-key-not-real"), opener=fake_urlopen)
        with self.assertRaises(Exception) as ctx:
            client.get_nano_banana_pro_flash_task("task-123")
        self.assertTrue(ctx.exception.retryable)
        self.assertNotIn("test-key-not-real", str(ctx.exception))


class ArtStudioMagnificApiDrainTests(unittest.TestCase):
    def test_registry_includes_social_image_handler(self) -> None:
        handler = default_registry().resolve("art_studio.social_image.generate", 1)
        self.assertIsNotNone(handler)
        self.assertEqual(art_studio_provider_status_label("generating"), "generating via Magnific API")

    def test_enqueue_without_api_key_stays_manual_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "no-key.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            with patch.dict("os.environ", {"MAGNIFIC_API_KEY": ""}, clear=False):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Manual Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Manual source",
                        asset_type="source photo",
                        source_path=source_path.as_posix(),
                        preview_path=source_path.as_posix(),
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    self.assertEqual(job.provider, "magnific_mcp")
                    self.assertIn("not drained by marketing-os-worker", job.review_notes)
                    automation = list(
                        session.query(AutomationJobRecord).filter_by(
                            job_type="art_studio.social_image.generate"
                        )
                    )
                    self.assertEqual(automation, [])

    def test_enqueue_with_api_key_creates_automation_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "with-key.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            with patch.dict("os.environ", {"MAGNIFIC_API_KEY": "test-key-not-real"}, clear=False):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="API Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="API source",
                        asset_type="Etsy product photo",
                        source_path="https://i.etsystatic.com/ref.jpg",
                        preview_path="https://i.etsystatic.com/ref.jpg",
                        canonical_url="https://i.etsystatic.com/ref.jpg",
                        mime_type="image/jpeg",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=0,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    self.assertEqual(job.provider, "magnific_api")
                    self.assertIn("Magnific API drain", job.review_notes)
                    automation = session.query(AutomationJobRecord).filter_by(
                        job_type="art_studio.social_image.generate",
                        idempotency_key=f"art_studio.social_image.generate:{job.id}",
                    ).one()
                    self.assertEqual(json.loads(automation.payload_json)["creativeJobId"], job.id)

    def test_handler_skips_when_api_key_empty(self) -> None:
        handler = default_registry().resolve("art_studio.social_image.generate", 1)
        assert handler is not None
        with patch.dict("os.environ", {"MAGNIFIC_API_KEY": ""}, clear=False):
            result = handler.function({"creativeJobId": 1})
        self.assertEqual(result, {"skipped": True, "reason": "MAGNIFIC_API_KEY unset"})

    def test_handler_generates_downloads_and_registers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "drain.sqlite"
            output_dir = tmp_path / "outputs" / "graphics" / "social-worthy" / "drain-duck"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)

            with patch.dict(
                "os.environ",
                {"MAGNIFIC_API_KEY": "test-key-not-real", "MARKETING_OS_DB_PATH": str(db_path)},
                clear=False,
            ):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Drain Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Drain source",
                        asset_type="Etsy product photo",
                        source_path="https://i.etsystatic.com/drain.jpg",
                        preview_path="https://i.etsystatic.com/drain.jpg",
                        canonical_url="https://i.etsystatic.com/drain.jpg",
                        mime_type="image/jpeg",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=0,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    # Point output into the temp dir for the test.
                    metadata = json.loads(job.response_metadata_json)
                    metadata["output_dir"] = output_dir.as_posix()
                    job.response_metadata_json = json.dumps(metadata)
                    session.flush()
                    creative_job_id = job.id

                poll_state = {"count": 0}

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                        return _FakeResponse(
                            json.dumps(
                                {"data": {"task_id": "drain-task", "status": "IN_PROGRESS", "generated": []}}
                            ).encode()
                        )
                    if method == "GET" and url.endswith("/nano-banana-pro-flash/drain-task"):
                        poll_state["count"] += 1
                        if poll_state["count"] < 2:
                            return _FakeResponse(
                                json.dumps(
                                    {"data": {"task_id": "drain-task", "status": "IN_PROGRESS", "generated": []}}
                                ).encode()
                            )
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "data": {
                                        "task_id": "drain-task",
                                        "status": "COMPLETED",
                                        "generated": ["https://cdn.example/drain-out.png"],
                                    }
                                }
                            ).encode()
                        )
                    if method == "GET" and url == "https://cdn.example/drain-out.png":
                        return _FakeResponse(TINY_PNG)
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
                    # Use real client wired to fake opener so handler path stays realistic.
                    client_cls.side_effect = lambda *a, **k: MagnificClient(
                        MagnificApiConfig(api_key="test-key-not-real"),
                        opener=fake_urlopen,
                    )
                    handler = default_registry().resolve("art_studio.social_image.generate", 1)
                    assert handler is not None
                    result = handler.function(
                        {
                            "creativeJobId": creative_job_id,
                            "pollSeconds": 0.01,
                            "timeoutSeconds": 2.0,
                        }
                    )

                self.assertEqual(result["providerJobId"], "drain-task")
                self.assertEqual(result["providerStatus"], "generated")
                self.assertTrue(Path(result["outputPath"]).is_file())

                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    job = session.get(CreativeGenerationJobRecord, creative_job_id)
                    assert job is not None
                    self.assertEqual(job.provider, "magnific_api")
                    self.assertEqual(job.provider_status, "generated")
                    self.assertEqual(job.provider_job_id, "drain-task")
                    self.assertIsNotNone(job.candidate_asset_id)
                    self.assertEqual(job.candidate_asset.external_source, "magnific_api")

    def test_handler_rejects_local_only_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "local-only.sqlite"
            source_path = tmp_path / "local.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            with patch.dict(
                "os.environ",
                {"MAGNIFIC_API_KEY": "test-key-not-real", "MARKETING_OS_DB_PATH": str(db_path)},
                clear=False,
            ):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Local Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Local source",
                        asset_type="source photo",
                        source_path=source_path.as_posix(),
                        preview_path=source_path.as_posix(),
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=1,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    creative_job_id = job.id

                handler = default_registry().resolve("art_studio.social_image.generate", 1)
                assert handler is not None
                with self.assertRaises(NonRetryableJobError) as ctx:
                    handler.function({"creativeJobId": creative_job_id})
                self.assertIn("https", str(ctx.exception).lower())
                self.assertIn("local-only", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
