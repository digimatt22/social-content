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
    SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS,
    art_studio_provider_status_label,
    enqueue_social_image_generation,
    resolve_social_image_frame,
    social_image_platform_options,
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


    def test_upload_local_image_request_put_flow(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_urlopen(request: Request, timeout: float = 0):
            method = request.get_method()
            url = request.full_url
            calls.append((method, url))
            if method == "POST" and url.endswith("/v1/ai/uploads/request-url"):
                return _FakeResponse(
                    json.dumps(
                        {
                            "files": [
                                {
                                    "file_id": "upl_img_unit1",
                                    "upload_url": "https://upload.example/put",
                                    "headers": {"Content-Type": "image/png", "x-goog-content-length-range": "0,1"},
                                    "asset_url": "https://cdn.example/unit.png",
                                    "asset_url_expires_in": 100,
                                }
                            ]
                        }
                    ).encode()
                )
            if method == "PUT" and url == "https://upload.example/put":
                self.assertEqual(request.data, TINY_PNG)
                return _FakeResponse(b"")
            raise AssertionError(f"unexpected {method} {url}")

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "ref.png"
            local.write_bytes(TINY_PNG)
            client = MagnificClient(MagnificApiConfig(api_key="test-key-not-real"), opener=fake_urlopen)
            uploaded = client.upload_local_image(local, content_type="image/png")
            self.assertEqual(uploaded.file_id, "upl_img_unit1")
            self.assertEqual(uploaded.asset_url, "https://cdn.example/unit.png")
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[1][0], "PUT")

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

    def test_handler_stages_local_reference_via_magnific_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "local-stage.sqlite"
            output_dir = tmp_path / "outputs" / "graphics" / "social-worthy" / "local-duck"
            source_path = tmp_path / "local.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            posted: dict[str, object] = {}
            upload_calls = {"request": 0, "put": 0, "list": 0}

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
                        mime_type="image/png",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=1,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    metadata = json.loads(job.response_metadata_json)
                    metadata["output_dir"] = output_dir.as_posix()
                    job.response_metadata_json = json.dumps(metadata)
                    session.flush()
                    creative_job_id = job.id
                    asset_id = source.id

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if method == "POST" and url.endswith("/v1/ai/uploads/request-url"):
                        upload_calls["request"] += 1
                        body = json.loads(request.data.decode("utf-8"))
                        self.assertEqual(body["files"][0]["content_type"], "image/png")
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "files": [
                                        {
                                            "file_id": "upl_img_local123",
                                            "upload_url": "https://upload.example/put-local",
                                            "headers": {
                                                "Content-Type": "image/png",
                                                "x-goog-content-length-range": "0,1073741824",
                                            },
                                            "expires_in": 120,
                                            "asset_url": "https://cdn.example/staged-local.png?token=abc",
                                            "asset_url_expires_in": 86400,
                                        }
                                    ]
                                }
                            ).encode()
                        )
                    if method == "PUT" and url == "https://upload.example/put-local":
                        upload_calls["put"] += 1
                        self.assertEqual(request.data, TINY_PNG)
                        headers = {k.lower(): v for k, v in request.header_items()}
                        self.assertEqual(headers.get("content-type"), "image/png")
                        return _FakeResponse(b"")
                    if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                        body = json.loads(request.data.decode("utf-8"))
                        posted["reference_images"] = body["reference_images"]
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "data": {
                                        "task_id": "local-task",
                                        "status": "COMPLETED",
                                        "generated": ["https://cdn.example/local-out.png"],
                                    }
                                }
                            ).encode()
                        )
                    if method == "GET" and url == "https://cdn.example/local-out.png":
                        return _FakeResponse(TINY_PNG)
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
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

                self.assertEqual(upload_calls["request"], 1)
                self.assertEqual(upload_calls["put"], 1)
                refs = posted["reference_images"]
                assert isinstance(refs, list)
                self.assertEqual(refs[0]["image"], "https://cdn.example/staged-local.png?token=abc")
                self.assertEqual(result["providerJobId"], "local-task")
                self.assertTrue(Path(result["outputPath"]).is_file())

                from marketing_os.db_models import SyncMetadata
                from sqlalchemy import select

                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    staged = session.scalar(
                        select(SyncMetadata).where(
                            SyncMetadata.source_name == f"magnific_upload_asset_{asset_id}"
                        )
                    )
                    assert staged is not None
                    staged_notes = json.loads(staged.notes)
                    self.assertEqual(staged_notes["file_id"], "upl_img_local123")
                    self.assertTrue(staged_notes["checksum"])

    def test_handler_reuses_staged_upload_without_reupload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "reuse-stage.sqlite"
            output_dir = tmp_path / "outputs" / "graphics" / "social-worthy" / "reuse-duck"
            source_path = tmp_path / "local.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            upload_calls = {"request": 0, "put": 0, "list": 0}
            posted: dict[str, object] = {}

            with patch.dict(
                "os.environ",
                {"MAGNIFIC_API_KEY": "test-key-not-real", "MARKETING_OS_DB_PATH": str(db_path)},
                clear=False,
            ):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Reuse Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Reuse source",
                        asset_type="source photo",
                        source_path=source_path.as_posix(),
                        preview_path=source_path.as_posix(),
                        mime_type="image/png",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=1,
                    )
                    session.add(source)
                    session.flush()
                    import hashlib
                    from marketing_os.db_models import SyncMetadata

                    checksum = hashlib.sha256(TINY_PNG).hexdigest()
                    session.add(
                        SyncMetadata(
                            source_name=f"magnific_upload_asset_{source.id}",
                            source_path=source_path.as_posix(),
                            notes=json.dumps(
                                {
                                    "file_id": "upl_img_reuse99",
                                    "checksum": checksum,
                                    "content_type": "image/png",
                                    "local_path": source_path.as_posix(),
                                }
                            ),
                        )
                    )
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    metadata = json.loads(job.response_metadata_json)
                    metadata["output_dir"] = output_dir.as_posix()
                    job.response_metadata_json = json.dumps(metadata)
                    session.flush()
                    creative_job_id = job.id

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if method == "POST" and url.endswith("/v1/ai/uploads/request-url"):
                        upload_calls["request"] += 1
                        raise AssertionError("should not re-request upload for matching checksum")
                    if method == "PUT":
                        upload_calls["put"] += 1
                        raise AssertionError("should not re-PUT for matching checksum")
                    if method == "GET" and url.endswith("/v1/ai/uploads"):
                        upload_calls["list"] += 1
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "files": [
                                        {
                                            "file_id": "upl_img_reuse99",
                                            "content_type": "image/png",
                                            "asset_url": "https://cdn.example/refreshed.png?token=new",
                                            "asset_url_expires_in": 86400,
                                        }
                                    ]
                                }
                            ).encode()
                        )
                    if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                        body = json.loads(request.data.decode("utf-8"))
                        posted["reference_images"] = body["reference_images"]
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "data": {
                                        "task_id": "reuse-task",
                                        "status": "COMPLETED",
                                        "generated": ["https://cdn.example/reuse-out.png"],
                                    }
                                }
                            ).encode()
                        )
                    if method == "GET" and url == "https://cdn.example/reuse-out.png":
                        return _FakeResponse(TINY_PNG)
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
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

                self.assertEqual(upload_calls["request"], 0)
                self.assertEqual(upload_calls["put"], 0)
                self.assertEqual(upload_calls["list"], 1)
                refs = posted["reference_images"]
                assert isinstance(refs, list)
                self.assertEqual(refs[0]["image"], "https://cdn.example/refreshed.png?token=new")
                self.assertEqual(result["providerJobId"], "reuse-task")

    def test_handler_skips_upload_for_https_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "https-skip.sqlite"
            output_dir = tmp_path / "outputs" / "graphics" / "social-worthy" / "https-duck"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            upload_calls = {"request": 0, "put": 0}
            posted: dict[str, object] = {}

            with patch.dict(
                "os.environ",
                {"MAGNIFIC_API_KEY": "test-key-not-real", "MARKETING_OS_DB_PATH": str(db_path)},
                clear=False,
            ):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Https Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Https source",
                        asset_type="Etsy product photo",
                        source_path="https://i.etsystatic.com/https-skip.jpg",
                        preview_path="https://i.etsystatic.com/https-skip.jpg",
                        canonical_url="https://i.etsystatic.com/https-skip.jpg",
                        mime_type="image/jpeg",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=0,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    metadata = json.loads(job.response_metadata_json)
                    metadata["output_dir"] = output_dir.as_posix()
                    job.response_metadata_json = json.dumps(metadata)
                    session.flush()
                    creative_job_id = job.id

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if "/v1/ai/uploads" in url:
                        upload_calls["request" if method == "POST" else "put"] += 1
                        raise AssertionError("https refs must not call Magnific upload API")
                    if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                        body = json.loads(request.data.decode("utf-8"))
                        posted["reference_images"] = body["reference_images"]
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "data": {
                                        "task_id": "https-task",
                                        "status": "COMPLETED",
                                        "generated": ["https://cdn.example/https-out.png"],
                                    }
                                }
                            ).encode()
                        )
                    if method == "GET" and url == "https://cdn.example/https-out.png":
                        return _FakeResponse(TINY_PNG)
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
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

                self.assertEqual(upload_calls["request"], 0)
                self.assertEqual(upload_calls["put"], 0)
                refs = posted["reference_images"]
                assert isinstance(refs, list)
                self.assertEqual(refs[0]["image"], "https://i.etsystatic.com/https-skip.jpg")
                self.assertEqual(result["providerJobId"], "https-task")

    def test_handler_clear_error_when_local_upload_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "upload-fail.sqlite"
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
                    product = ProductRecord(name="Fail Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Fail source",
                        asset_type="source photo",
                        source_path=source_path.as_posix(),
                        preview_path=source_path.as_posix(),
                        mime_type="image/png",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=1,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(session, product.id, source.id)
                    creative_job_id = job.id

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if method == "POST" and url.endswith("/v1/ai/uploads/request-url"):
                        raise HTTPError(
                            url,
                            400,
                            "Bad Request",
                            hdrs=None,
                            fp=io.BytesIO(b'{"message":"bad content_type"}'),
                        )
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
                    client_cls.side_effect = lambda *a, **k: MagnificClient(
                        MagnificApiConfig(api_key="test-key-not-real"),
                        opener=fake_urlopen,
                    )
                    handler = default_registry().resolve("art_studio.social_image.generate", 1)
                    assert handler is not None
                    with self.assertRaises(NonRetryableJobError) as ctx:
                        handler.function({"creativeJobId": creative_job_id})
                self.assertIn("stage local reference", str(ctx.exception).lower())


class SocialImagePlatformAspectTests(unittest.TestCase):
    def test_platform_aspect_map_covers_requested_ratios(self) -> None:
        expected = {
            "ig_feed": "1:1",
            "fb_feed": "1:1",
            "ig_portrait": "4:5",
            "fb_portrait": "4:5",
            "stories": "9:16",
            "reels": "9:16",
            "tiktok": "9:16",
            "x": "16:9",
            "landscape_link": "16:9",
            "pinterest": "2:3",
        }
        self.assertEqual(SOCIAL_IMAGE_PLATFORM_ASPECT_RATIOS, expected)
        self.assertEqual(resolve_social_image_frame(), ("ig_feed", "1:1"))
        self.assertEqual(resolve_social_image_frame("stories"), ("stories", "9:16"))
        self.assertEqual(resolve_social_image_frame(aspect_ratio="2:3"), ("", "2:3"))
        labels = [option["label"] for option in social_image_platform_options()]
        self.assertTrue(any("IG Feed (1:1)" == label for label in labels))
        self.assertTrue(any("Pinterest (2:3)" == label for label in labels))

    def test_enqueue_stores_platform_and_aspect_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "aspect-meta.sqlite"
            source_path = tmp_path / "source.png"
            source_path.write_bytes(TINY_PNG)
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            with patch.dict("os.environ", {"MAGNIFIC_API_KEY": ""}, clear=False):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Aspect Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Aspect source",
                        asset_type="source photo",
                        source_path=source_path.as_posix(),
                        preview_path=source_path.as_posix(),
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                    )
                    session.add(source)
                    session.flush()
                    default_job = enqueue_social_image_generation(session, product.id, source.id)
                    stories_job = enqueue_social_image_generation(
                        session, product.id, source.id, platform="stories", option_number=2
                    )
                    default_meta = json.loads(default_job.response_metadata_json)
                    stories_meta = json.loads(stories_job.response_metadata_json)
                    self.assertEqual(default_meta["platform"], "ig_feed")
                    self.assertEqual(default_meta["aspect_ratio"], "1:1")
                    self.assertEqual(default_job.requested_dimensions, "1:1 IG Feed")
                    self.assertIn("1:1 square social image (IG Feed)", default_job.prompt)
                    self.assertEqual(stories_meta["platform"], "stories")
                    self.assertEqual(stories_meta["aspect_ratio"], "9:16")
                    self.assertEqual(stories_job.requested_dimensions, "9:16 Stories")
                    self.assertIn("9:16 vertical stories/reels social image (Stories)", stories_job.prompt)
                    self.assertNotEqual(default_job.id, stories_job.id)

    def test_handler_passes_stored_aspect_ratio_to_magnific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "aspect-drain.sqlite"
            output_dir = tmp_path / "outputs" / "graphics" / "social-worthy" / "aspect-duck"
            app = create_app(db_path)
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            posted: dict[str, object] = {}

            with patch.dict(
                "os.environ",
                {"MAGNIFIC_API_KEY": "test-key-not-real", "MARKETING_OS_DB_PATH": str(db_path)},
                clear=False,
            ):
                with session_scope(app.config["SESSION_FACTORY"]) as session:
                    product = ProductRecord(name="Aspect Drain Duck")
                    session.add(product)
                    session.flush()
                    source = AssetRecord(
                        product_id=product.id,
                        name="Aspect drain source",
                        asset_type="Etsy product photo",
                        source_path="https://i.etsystatic.com/aspect.jpg",
                        preview_path="https://i.etsystatic.com/aspect.jpg",
                        canonical_url="https://i.etsystatic.com/aspect.jpg",
                        mime_type="image/jpeg",
                        readiness_state="ready",
                        review_state="approved",
                        default_reference=1,
                        file_exists=0,
                    )
                    session.add(source)
                    session.flush()
                    job = enqueue_social_image_generation(
                        session, product.id, source.id, platform="stories"
                    )
                    metadata = json.loads(job.response_metadata_json)
                    metadata["output_dir"] = output_dir.as_posix()
                    job.response_metadata_json = json.dumps(metadata)
                    session.flush()
                    creative_job_id = job.id

                def fake_urlopen(request: Request, timeout: float = 0):
                    method = request.get_method()
                    url = request.full_url
                    if method == "POST" and url.endswith("/nano-banana-pro-flash"):
                        body = json.loads(request.data.decode("utf-8"))
                        posted["aspect_ratio"] = body["aspect_ratio"]
                        return _FakeResponse(
                            json.dumps(
                                {
                                    "data": {
                                        "task_id": "aspect-task",
                                        "status": "COMPLETED",
                                        "generated": ["https://cdn.example/aspect-out.png"],
                                    }
                                }
                            ).encode()
                        )
                    if method == "GET" and url == "https://cdn.example/aspect-out.png":
                        return _FakeResponse(TINY_PNG)
                    raise AssertionError(f"unexpected {method} {url}")

                with patch("marketing_os.magnific_api.urllib.request.urlopen", fake_urlopen), patch(
                    "marketing_os.jobs.art_studio_social_image.MagnificClient"
                ) as client_cls:
                    from marketing_os.magnific_api import MagnificApiConfig, MagnificClient

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

                self.assertEqual(posted["aspect_ratio"], "9:16")
                self.assertEqual(result["providerJobId"], "aspect-task")
                self.assertTrue(Path(result["outputPath"]).is_file())
                self.assertIn("stories", Path(result["outputPath"]).name)



if __name__ == "__main__":
    unittest.main()
