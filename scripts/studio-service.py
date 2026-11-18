import os
import signal
import subprocess
import sys
import time


def run_service(commands) -> int:
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, stop)

    try:
        for command, cwd, env in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env))
        while not stopping:
            for child in children:
                status = child.poll()
                if status is not None:
                    return status or 1
            time.sleep(0.25)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def main(service: str) -> int:
    studio_dir = "/app/next-studio"
    next_env = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "MARKETING_OS_DB_URL", "STUDIO_OPENAI_DAILY_JOBS")
        if name in os.environ
    }
    next_env.update(STUDIO_HOSTED="1", NODE_ENV="production", NEXT_TELEMETRY_DISABLED="1")
    legacy_env = dict(os.environ)
    credential = legacy_env.pop("OPENAI_API_KEY", "")
    if service == "web":
        return run_service([
            (["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3037"], studio_dir, next_env),
            (["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "2",
              "--timeout", "45", "--access-logfile", "-", "marketing_os.wsgi:app"], "/app", legacy_env),
        ])
    if service == "worker":
        limit = next_env.get("STUDIO_OPENAI_DAILY_JOBS", "0")
        if limit == "0":
            os.environ.pop("OPENAI_API_KEY", None)
            os.execvpe("marketing-os-worker", ["marketing-os-worker"], legacy_env)
        next_env["OPENAI_API_KEY"] = credential
        return run_service([
            (["marketing-os-worker"], "/app", legacy_env),
            (["node", "scripts/worker.mjs"], studio_dir, next_env),
        ])
    raise SystemExit("Expected web or worker.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
