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
DEFAULT_BASE_URL = "https://api.magnific.com"


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
