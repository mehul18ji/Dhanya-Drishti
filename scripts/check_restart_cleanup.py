"""Real-process restart-cleanup check (PRD §16).

Proves the temporary-storage contract with the **real** application, not a test
double:

1. start a real ``uvicorn app.main:app`` process with an explicit ``RUNTIME_DIR``;
2. create one real prediction from a real image;
3. confirm the history row and its PNG artifacts exist;
4. stop the process completely (and prove it is gone, not merely orphaned);
5. start a **fresh** process with the **same** ``RUNTIME_DIR``;
6. confirm history is empty and the old artifacts are gone.

Any failure exits non-zero. The check deliberately verifies that the first process
is dead and the port is free before starting the second one, so a reused server
process can never masquerade as a successful restart.

Usage (from the repository root)::

    python scripts/check_restart_cleanup.py
    python scripts/check_restart_cleanup.py --image "data/raw/rice_leaf_diseases/Brown spot/DSC_0105.jpg"
    python scripts/check_restart_cleanup.py --runtime-dir backend/.runtime-restart-check

The runtime directory is deleted before the check and after a successful run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_RUNTIME_DIR = BACKEND_DIR / ".runtime-restart-check"
DEFAULT_IMAGE = (
    REPO_ROOT
    / "data"
    / "raw"
    / "rice_leaf_diseases"
    / "Brown spot"
    / "DSC_0105.jpg"
)
STARTUP_TIMEOUT_S = 120.0
SHUTDOWN_TIMEOUT_S = 30.0


class CheckFailure(RuntimeError):
    """A restart-cleanup invariant failed."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_is_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _artifact_dirs(runtime_dir: Path) -> list[Path]:
    artifacts = runtime_dir / "artifacts"
    if not artifacts.is_dir():
        return []
    return sorted(path for path in artifacts.iterdir() if path.is_dir())


def _artifact_files(runtime_dir: Path) -> list[Path]:
    artifacts = runtime_dir / "artifacts"
    if not artifacts.is_dir():
        return []
    return sorted(path for path in artifacts.rglob("*") if path.is_file())


def _server_env(runtime_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "ENVIRONMENT": "restart-check",
            "RUNTIME_DIR": str(runtime_dir),
            "LOG_LEVEL": "WARNING",
            # Never let a caller's dotenv/prefix leak in and change the storage path.
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _start_server(runtime_dir: Path, port: int, log_path: Path) -> subprocess.Popen[bytes]:
    log_file = log_path.open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_DIR,
        env=_server_env(runtime_dir),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    # Keep the handle closed in the parent once the child owns it.
    log_file.close()
    return process


def _wait_for_health(
    process: subprocess.Popen[bytes], port: int, log_path: Path, label: str
) -> dict[str, object]:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    url = f"http://127.0.0.1:{port}/api/v1/health"
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CheckFailure(
                f"{label}: server exited early with code {process.returncode}. "
                f"Log:\n{log_path.read_text(errors='replace')[-4000:]}"
            )
        try:
            response = httpx.get(url, timeout=2.0)
        except httpx.HTTPError as exc:  # not up yet
            last_error = str(exc)
        else:
            if response.status_code == 200:
                payload = response.json()
                if not payload.get("model_loaded"):
                    raise CheckFailure(
                        f"{label}: backend started but the model bundle is not loaded: {payload}"
                    )
                return payload
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
        time.sleep(0.25)
    raise CheckFailure(
        f"{label}: backend did not become healthy within {STARTUP_TIMEOUT_S:.0f}s "
        f"({last_error}). Log:\n{log_path.read_text(errors='replace')[-4000:]}"
    )


def _stop_server(
    process: subprocess.Popen[bytes], port: int, log_path: Path, label: str
) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=SHUTDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=SHUTDOWN_TIMEOUT_S)
    if process.poll() is None:  # pragma: no cover - defensive
        raise CheckFailure(f"{label}: process {process.pid} is still running")

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if _port_is_closed(port):
            return
        time.sleep(0.1)
    raise CheckFailure(
        f"{label}: port {port} is still accepting connections after the process "
        f"exited (code {process.returncode}); something else is serving on that port. "
        f"Log:\n{log_path.read_text(errors='replace')[-4000:]}"
    )


def _create_prediction(port: int, image: Path) -> dict[str, object]:
    with image.open("rb") as handle:
        files = {"file": (image.name, handle, "image/jpeg")}
        response = httpx.post(
            f"http://127.0.0.1:{port}/api/v1/predict",
            files=files,
            timeout=120.0,
        )
    if response.status_code != 200:
        raise CheckFailure(
            f"prediction failed: HTTP {response.status_code}: {response.text[:1000]}"
        )
    payload = response.json()
    if payload.get("status") not in {"predicted", "uncertain"}:
        raise CheckFailure(
            f"expected a labelled result, got status={payload.get('status')!r} "
            f"({json.dumps(payload)[:1000]}); pick a different --image"
        )
    if not payload.get("prediction_id"):
        raise CheckFailure("labelled prediction carried no prediction_id")
    return payload


def _get_json(url: str) -> dict[str, object]:
    response = httpx.get(url, timeout=30.0)
    if response.status_code != 200:
        raise CheckFailure(f"GET {url} -> HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


def run(runtime_dir: Path, image: Path, keep_runtime: bool) -> dict[str, object]:
    if not image.is_file():
        raise CheckFailure(f"image not found: {image}")

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    evidence: dict[str, object] = {
        "runtime_dir": str(runtime_dir),
        "port": port,
        "image": str(image.relative_to(REPO_ROOT)) if image.is_relative_to(REPO_ROOT) else str(image),
    }

    first_log = runtime_dir / "first-run.log"
    second_log = runtime_dir / "second-run.log"
    first = _start_server(runtime_dir, port, first_log)
    try:
        health_first = _wait_for_health(first, port, first_log, "first start")
        prediction = _create_prediction(port, image)
        prediction_id = str(prediction["prediction_id"])

        history_before = _get_json(f"http://127.0.0.1:{port}/api/v1/history")
        if history_before.get("count") != 1:
            raise CheckFailure(
                f"expected exactly 1 history row before restart, got {history_before.get('count')}"
            )
        if str(history_before["items"][0]["prediction_id"]) != prediction_id:
            raise CheckFailure("stored history row does not match the prediction id")

        artifact_urls = dict(prediction.get("artifacts") or {})
        if not artifact_urls:
            raise CheckFailure(f"prediction {prediction_id} returned no artifact URLs")
        artifact_status: dict[str, int] = {}
        for kind, url in artifact_urls.items():
            artifact_status[kind] = httpx.get(
                f"http://127.0.0.1:{port}{url}", timeout=30.0
            ).status_code

        before_dirs = _artifact_dirs(runtime_dir)
        before_files = _artifact_files(runtime_dir)
        if not before_dirs or not before_files:
            raise CheckFailure(
                f"expected artifact files under {runtime_dir / 'artifacts'} before restart"
            )
        if not (runtime_dir / "history.sqlite3").is_file():
            raise CheckFailure(f"expected {runtime_dir / 'history.sqlite3'} before restart")

        evidence["first_start"] = {
            "health": health_first,
            "prediction_id": prediction_id,
            "status": prediction.get("status"),
            "disease": prediction.get("disease"),
            "severity": prediction.get("severity"),
            "decision_scores": prediction.get("decision_scores"),
            "margin": prediction.get("margin"),
            "artifact_http_status": artifact_status,
            "history_count": history_before.get("count"),
            "artifact_dirs": [p.name for p in before_dirs],
            "artifact_files": len(before_files),
            "sqlite_present": True,
        }
    finally:
        _stop_server(first, port, first_log, "first stop")
        evidence["first_stop"] = {
            "exit_code": first.returncode,
            "port_closed": _port_is_closed(port),
        }

    # Leftovers a hard stop could leave behind; the next startup must remove them.
    evidence["leftover_after_stop"] = {
        "sqlite_present": (runtime_dir / "history.sqlite3").is_file(),
        "artifact_dirs": [p.name for p in _artifact_dirs(runtime_dir)],
        "artifact_files": len(_artifact_files(runtime_dir)),
    }

    second = _start_server(runtime_dir, port, second_log)
    try:
        health_second = _wait_for_health(second, port, second_log, "second start")
        history_after = _get_json(f"http://127.0.0.1:{port}/api/v1/history")
        after_dirs = _artifact_dirs(runtime_dir)
        after_files = _artifact_files(runtime_dir)
        after_artifact_status = {
            kind: httpx.get(f"http://127.0.0.1:{port}{url}", timeout=30.0).status_code
            for kind, url in artifact_urls.items()
        }

        if history_after.get("count") != 0:
            raise CheckFailure(
                "restart did not clear history: "
                f"{history_after.get('count')} row(s) survived ({json.dumps(history_after)[:1000]})"
            )
        if after_dirs or after_files:
            raise CheckFailure(
                "restart did not clear artifacts: "
                f"dirs={[p.name for p in after_dirs]} files={[str(p) for p in after_files]}"
            )
        if any(status != 404 for status in after_artifact_status.values()):
            raise CheckFailure(
                f"old artifact URLs still served after restart: {after_artifact_status}"
            )

        evidence["second_start"] = {
            "health": health_second,
            "history_count": history_after.get("count"),
            "artifact_dirs": [p.name for p in after_dirs],
            "artifact_files": len(after_files),
            "old_artifact_http_status": after_artifact_status,
        }
    finally:
        _stop_server(second, port, second_log, "second stop")
        evidence["second_stop"] = {
            "exit_code": second.returncode,
            "port_closed": _port_is_closed(port),
        }

    if not keep_runtime:
        shutil.rmtree(runtime_dir, ignore_errors=True)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument(
        "--keep-runtime",
        action="store_true",
        help="leave the runtime directory in place for inspection",
    )
    args = parser.parse_args()

    runtime_dir = args.runtime_dir
    if not runtime_dir.is_absolute():
        runtime_dir = (REPO_ROOT / runtime_dir).resolve()
    image = args.image if args.image.is_absolute() else (REPO_ROOT / args.image)

    try:
        evidence = run(runtime_dir, image, args.keep_runtime)
    except CheckFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(evidence, indent=2))
    print(
        "PASS: a fresh process with the same RUNTIME_DIR cleared history and artifacts "
        f"(prediction {evidence['first_start']['prediction_id']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
