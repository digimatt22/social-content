from http.client import HTTPConnection
from urllib.parse import quote

from flask import Flask, Response, abort, redirect, request


MAX_REQUEST = 10 * 1024 * 1024 + 16_384
MAX_RESPONSE = 12 * 1024 * 1024


def register_studio_gateway(app: Flask) -> None:
    @app.before_request
    def studio_home():
        if request.path == "/" and request.method in {"GET", "HEAD"}:
            return redirect("/studio/")
        return None

    @app.route("/studio/", defaults={"path": ""}, methods=["GET", "HEAD"])
    @app.route("/studio/<path:path>", methods=["GET", "HEAD", "POST"])
    def studio_proxy(path: str):
        api = path.startswith("api/studio/")
        static = path.startswith("_next/static/")
        if any(segment in {".", ".."} for segment in path.split("/")) or (path and not (api or static)):
            abort(404)
        if request.method == "POST":
            if not api:
                abort(405)
            if request.headers.get("Origin") != f"https://{request.host}":
                return {"error": "Open Social Studio at its secure address to make changes."}, 403
            if not request.content_length or request.content_length > MAX_REQUEST:
                return {"error": "The form exceeds the studio upload limit."}, 413

        headers = {"Accept-Encoding": "identity"}
        if request.content_type:
            headers["Content-Type"] = request.content_type
        if request.method == "POST":
            headers["Origin"] = "http://127.0.0.1:3037"
        target = "/studio/" + quote(path, safe="/")
        if request.query_string:
            target += "?" + request.query_string.decode("ascii", errors="replace")

        connection = HTTPConnection("127.0.0.1", 3037, timeout=28)
        try:
            body = request.get_data() if request.method == "POST" else None
            connection.request(request.method, target, body=body, headers=headers)
            upstream = connection.getresponse()
            content = upstream.read(MAX_RESPONSE + 1)
            if len(content) > MAX_RESPONSE:
                return {"error": "The studio response exceeds its serving limit."}, 502
            forwarded = {key: value for key, value in upstream.getheaders() if key.lower() in {
                "content-type", "content-disposition", "content-encoding", "cache-control", "etag", "location"
            }}
            if not static:
                forwarded["Cache-Control"] = "no-store"
            response = Response(content, upstream.status, headers=forwarded)
            if not static:
                response.vary.add("Cookie")
            return response
        except OSError:
            return {"error": "Social Studio is temporarily unavailable."}, 503
        finally:
            connection.close()


def studio_process_ready() -> bool:
    connection = HTTPConnection("127.0.0.1", 3037, timeout=3)
    try:
        connection.request("GET", "/studio/api/health")
        return connection.getresponse().status == 200
    except OSError:
        return False
    finally:
        connection.close()
