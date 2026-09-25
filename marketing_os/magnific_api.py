"""Thin Magnific REST client for Art Studio social-image automation.

Auth uses header ``x-magnific-api-key`` from ``MAGNIFIC_API_KEY``.
Never log or print the API key value.

``MAGNIFIC_WEBHOOK_SECRET`` is reserved for a future webhook verification path;
this module does not verify webhooks yet.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_local_env

NANO_BANANA_PRO_FLASH_PATH = "/v1/ai/text-to-image/nano-banana-pro-flash"
UPLOAD_REQUEST_URL_PATH = "/v1/ai/uploads/request-url"
UPLOADS_LIST_PATH = "/v1/ai/uploads"
DEFAULT_BASE_URL = "https://api.magnific.com"
SUPPORTED_UPLOAD_IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


@dataclass(frozen=True)
class MagnificApiConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    @classmethod
    def from_env(cls) -> "MagnificApiConfig":
        load_local_env()
        return cls(
            api_key=os.environ.get("MAGNIFIC_API_KEY", "").strip(),
            base_url=(os.environ.get("MAGNIFIC_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        )


@dataclass(frozen=True)
class MagnificReferenceImage:
    image: str
    text: str = ""
    mime_type: str = "image/jpeg"

    def as_payload(self) -> dict[str, str]:
        return {
            "image": self.image,
            "text": self.text,
            "mime_type": self.mime_type or "image/jpeg",
        }


@dataclass(frozen=True)
class MagnificTaskResult:
    task_id: str
    status: str
    generated: list[str]
    raw: dict[str, Any]

    @property
    def completed(self) -> bool:
        return self.status.upper() == "COMPLETED"

    @property
    def failed(self) -> bool:
        return self.status.upper() == "FAILED"

    @property
    def in_progress(self) -> bool:
        return self.status.upper() in {"CREATED", "IN_PROGRESS"}


@dataclass(frozen=True)
class MagnificUploadedFile:
    """Result of staging a local file via Magnific Upload Files API."""

    file_id: str
    asset_url: str
    content_type: str = "image/jpeg"
    asset_url_expires_in: int | None = None


class MagnificApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class MagnificClient:
    """Minimal REST client for Nano Banana Pro Flash create + poll + download."""

    def __init__(self, config: MagnificApiConfig | None = None, *, opener=None) -> None:
        self.config = config or MagnificApiConfig.from_env()
        self._opener = opener or urllib.request.urlopen

    def require_configured(self) -> None:
        if not self.config.configured:
            raise MagnificApiError("MAGNIFIC_API_KEY is not configured.", retryable=False)

    def create_nano_banana_pro_flash(
        self,
        *,
        prompt: str,
        reference_images: list[MagnificReferenceImage] | None = None,
        aspect_ratio: str = "1:1",
        resolution: str = "2K",
        use_google_search_tool: bool = False,
        webhook_url: str | None = None,
    ) -> MagnificTaskResult:
        self.require_configured()
        body: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "use_google_search_tool": use_google_search_tool,
        }
        if reference_images:
            body["reference_images"] = [item.as_payload() for item in reference_images]
        if webhook_url:
            body["webhook_url"] = webhook_url
        payload = self._request("POST", NANO_BANANA_PRO_FLASH_PATH, body=body)
        return _task_from_payload(payload)

    def get_nano_banana_pro_flash_task(self, task_id: str) -> MagnificTaskResult:
        self.require_configured()
        if not task_id.strip():
            raise MagnificApiError("task_id is required.", retryable=False)
        path = f"{NANO_BANANA_PRO_FLASH_PATH}/{urllib.parse.quote(task_id.strip(), safe='')}"
        payload = self._request("GET", path)
        return _task_from_payload(payload)

    def wait_for_nano_banana_pro_flash(
        self,
        task_id: str,
        *,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 300.0,
        sleeper=time.sleep,
    ) -> MagnificTaskResult:
        deadline = time.monotonic() + max(timeout_seconds, 1.0)
        latest = self.get_nano_banana_pro_flash_task(task_id)
        while latest.in_progress:
            if time.monotonic() >= deadline:
                raise MagnificApiError(
                    f"Magnific task {task_id} timed out after {timeout_seconds:.0f}s (status={latest.status}).",
                    retryable=True,
                )
            sleeper(max(poll_seconds, 0.1))
            latest = self.get_nano_banana_pro_flash_task(task_id)
        if latest.failed:
            raise MagnificApiError(f"Magnific task {task_id} failed.", retryable=False)
        if not latest.completed:
            raise MagnificApiError(
                f"Magnific task {task_id} ended in unexpected status {latest.status}.",
                retryable=True,
            )
        return latest

    def request_upload_urls(self, content_types: list[str]) -> list[dict[str, Any]]:
        """POST /v1/ai/uploads/request-url — get short-lived PUT targets + asset_urls."""
        self.require_configured()
        if not content_types:
            raise MagnificApiError("content_types is required for upload request.", retryable=False)
        if len(content_types) > 14:
            raise MagnificApiError("Magnific upload request-url accepts at most 14 files.", retryable=False)
        body = {"files": [{"content_type": item} for item in content_types]}
        payload = self._request("POST", UPLOAD_REQUEST_URL_PATH, body=body)
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise MagnificApiError("Magnific upload request-url returned no files.", retryable=True)
        return [item for item in files if isinstance(item, dict)]

    def put_upload_bytes(self, upload_url: str, headers: dict[str, str], data: bytes) -> None:
        """PUT raw bytes to a Magnific pre-signed upload_url (no API key)."""
        if not (upload_url or "").strip().startswith(("http://", "https://")):
            raise MagnificApiError("upload_url must be http(s).", retryable=False)
        request_headers = {str(key): str(value) for key, value in (headers or {}).items()}
        request = urllib.request.Request(
            upload_url.strip(),
            data=data,
            headers=request_headers,
            method="PUT",
        )
        try:
            with self._opener(request, timeout=120) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = _safe_error_body(exc)
            raise MagnificApiError(
                f"Magnific upload PUT failed (HTTP {exc.code}){detail}.",
                status_code=exc.code,
                retryable=exc.code in {408, 425, 429, 500, 502, 503, 504},
            ) from exc
        except urllib.error.URLError as exc:
            raise MagnificApiError(f"Magnific upload PUT transport error: {exc.reason}", retryable=True) from exc

    def list_uploads(self) -> list[dict[str, Any]]:
        """GET /v1/ai/uploads — list staged uploads with freshly signed asset_urls."""
        self.require_configured()
        payload = self._request("GET", UPLOADS_LIST_PATH)
        files = payload.get("files")
        if files is None:
            return []
        if not isinstance(files, list):
            raise MagnificApiError("Magnific uploads list returned unexpected JSON shape.", retryable=True)
        return [item for item in files if isinstance(item, dict)]

    def refresh_upload_asset_url(self, file_id: str) -> str:
        """Return a freshly signed asset_url for a previously staged file_id."""
        wanted = (file_id or "").strip()
        if not wanted:
            raise MagnificApiError("file_id is required to refresh an upload URL.", retryable=False)
        for item in self.list_uploads():
            if str(item.get("file_id") or "").strip() != wanted:
                continue
            asset_url = str(item.get("asset_url") or "").strip()
            if asset_url.startswith("https://"):
                return asset_url
            raise MagnificApiError(
                f"Magnific upload {wanted} listed without an https asset_url.",
                retryable=True,
            )
        raise MagnificApiError(
            f"Magnific upload {wanted} was not found (expired or deleted).",
            retryable=False,
        )

    def upload_local_image(self, path: str | Path, *, content_type: str | None = None) -> MagnificUploadedFile:
        """Stage a local image via Magnific Upload Files API and return file_id + asset_url."""
        file_path = Path(path).expanduser()
        if not file_path.is_file():
            raise MagnificApiError(f"Local reference file not found: {file_path}", retryable=False)
        mime = (content_type or "").strip() or guess_mime_type(file_path.name)
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in SUPPORTED_UPLOAD_IMAGE_TYPES:
            raise MagnificApiError(
                f"Unsupported reference image type for Magnific upload: {mime} "
                f"(supported: {', '.join(sorted(SUPPORTED_UPLOAD_IMAGE_TYPES))}).",
                retryable=False,
            )
        slots = self.request_upload_urls([mime])
        slot = slots[0]
        upload_url = str(slot.get("upload_url") or "").strip()
        asset_url = str(slot.get("asset_url") or "").strip()
        file_id = str(slot.get("file_id") or "").strip()
        raw_headers = slot.get("headers") if isinstance(slot.get("headers"), dict) else {}
        headers = {str(k): str(v) for k, v in raw_headers.items()}
        if not upload_url or not asset_url or not file_id:
            raise MagnificApiError("Magnific upload request-url missing upload_url/asset_url/file_id.", retryable=True)
        if "Content-Type" not in headers and "content-type" not in {k.lower() for k in headers}:
            headers["Content-Type"] = mime
        self.put_upload_bytes(upload_url, headers, file_path.read_bytes())
        expires = slot.get("asset_url_expires_in")
        expires_int = int(expires) if isinstance(expires, int) else None
        return MagnificUploadedFile(
            file_id=file_id,
            asset_url=asset_url,
            content_type=mime,
            asset_url_expires_in=expires_int,
        )

    def download_to_path(self, url: str, destination: str | Path) -> Path:
        if not url.strip().startswith(("http://", "https://")):
            raise MagnificApiError("download URL must be http(s).", retryable=False)
        dest = Path(destination).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url.strip(), method="GET")
        try:
            with self._opener(request, timeout=60) as response:
                dest.write_bytes(response.read())
        except urllib.error.HTTPError as exc:
            raise MagnificApiError(
                f"Failed to download Magnific output (HTTP {exc.code}).",
                status_code=exc.code,
                retryable=exc.code in {408, 425, 429, 500, 502, 503, 504},
            ) from exc
        except urllib.error.URLError as exc:
            raise MagnificApiError(f"Failed to download Magnific output: {exc.reason}", retryable=True) from exc
        return dest

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "x-magnific-api-key": self.config.api_key,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = _safe_error_body(exc)
            raise MagnificApiError(
                f"Magnific API {method} {path} failed (HTTP {exc.code}){detail}.",
                status_code=exc.code,
                retryable=exc.code in {408, 425, 429, 500, 502, 503, 504},
            ) from exc
        except urllib.error.URLError as exc:
            raise MagnificApiError(f"Magnific API transport error: {exc.reason}", retryable=True) from exc
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MagnificApiError("Magnific API returned non-JSON response.", retryable=True) from exc
        if not isinstance(parsed, dict):
            raise MagnificApiError("Magnific API returned unexpected JSON shape.", retryable=True)
        return parsed


def magnific_api_configured() -> bool:
    return MagnificApiConfig.from_env().configured


def guess_mime_type(url_or_path: str, fallback: str = "image/jpeg") -> str:
    guessed, _ = mimetypes.guess_type(url_or_path)
    if guessed and guessed.startswith("image/"):
        return guessed
    return fallback


def https_asset_url(*candidates: str | None) -> str | None:
    """Prefer publicly reachable https URLs for Magnific reference_images."""
    for value in candidates:
        text = (value or "").strip()
        if text.startswith("https://"):
            return text
    return None


def _task_from_payload(payload: dict[str, Any]) -> MagnificTaskResult:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise MagnificApiError("Magnific API task payload missing data object.", retryable=True)
    task_id = str(data.get("task_id") or "").strip()
    status = str(data.get("status") or "").strip() or "UNKNOWN"
    generated_raw = data.get("generated") or []
    generated: list[str] = []
    if isinstance(generated_raw, list):
        for item in generated_raw:
            if isinstance(item, str) and item.strip():
                generated.append(item.strip())
            elif isinstance(item, dict):
                url = str(item.get("url") or item.get("image") or "").strip()
                if url:
                    generated.append(url)
    if not task_id:
        raise MagnificApiError("Magnific API response missing task_id.", retryable=True)
    return MagnificTaskResult(task_id=task_id, status=status, generated=generated, raw=payload)


def _safe_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    if not body:
        return ""
    # Avoid leaking credentials if a proxy echoed headers; keep message short.
    truncated = body[:240].replace("\n", " ")
    return f": {truncated}"
