"""Full localhost acceptance matrix (real backend, real pipeline, real model).

Runs the complete Phase 6 / local-acceptance checklist against one real
``uvicorn app.main:app`` process with an explicit ``RUNTIME_DIR``:

* real dataset image smoke prediction;
* held-out manifest image smoke prediction (functional only — never for tuning);
* landscape, rotated portrait and EXIF-portrait uploads;
* multiple leaves, poor-quality, healthy-looking and non-rice images;
* a valid image that must be rejected with HTTP 200 and no history row;
* invalid uploads (413 / 415 / 422);
* history, single-record and artifact retrieval;
* clear history (rows and files);
* a restart into a **fresh process** with the **same** ``RUNTIME_DIR`` that must
  start empty (the restart-cleanup acceptance requirement);
* request timings and the preprocessing resize/crop/letterbox geometry.

Writes a machine-readable evidence file (default
``docs/local_acceptance/api_evidence.json``) and prints a pass/fail summary.
Exits non-zero when a required check fails.

Usage (from the repository root)::

    python scripts/run_local_acceptance.py
    python scripts/run_local_acceptance.py --keep-runtime
    python scripts/run_local_acceptance.py --runtime-dir backend/.runtime-local-acceptance

The runtime directory is deleted before the run. Raw dataset images are read in
place and never copied; the rotated/EXIF/poor-quality variants are produced in
memory.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_restart_cleanup as restart_check  # noqa: E402  (local helper module)

from app.vision.config import load_segmentation_config  # noqa: E402
from app.vision.pipeline import run_segmentation  # noqa: E402

DATASET_DIR = REPO_ROOT / "data" / "raw" / "rice_leaf_diseases"
INPUTS_DIR = REPO_ROOT / "data" / "local_acceptance_inputs"
TEST_MANIFEST = REPO_ROOT / "data" / "splits" / "test.json"
DEFAULT_RUNTIME_DIR = BACKEND_DIR / ".runtime-local-acceptance"
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "docs" / "local_acceptance" / "api_evidence.json"

CLASSES = {"bacterial_leaf_blight", "brown_spot", "leaf_smut"}
LABELLED_STATUSES = {"predicted", "uncertain"}
SEVERITY_DISCLAIMER_PREFIX = "Severity is an experimental estimate"


class AcceptanceFailure(RuntimeError):
    """A required acceptance check failed."""


def display_path(path: Path) -> str:
    """Return a repository-relative path, or the full path when it is external.

    The evidence file is allowed to live outside the repository (for example in a
    temporary directory during CI). Reporting it must therefore never raise a
    ``ValueError`` from ``Path.relative_to``; this helper only affects the printed
    and recorded path, not any acceptance check.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class Recorder:
    """Collects pass/fail rows and the supporting evidence."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def add(
        self,
        name: str,
        *,
        passed: bool,
        detail: str,
        category: str = "functional",
        evidence: dict[str, object] | None = None,
    ) -> None:
        self.rows.append(
            {
                "check": name,
                "category": category,
                "result": "pass" if passed else "fail",
                "detail": detail,
                "evidence": evidence or {},
            }
        )
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name} - {detail}")

    def require(self, *args, **kwargs) -> None:
        """Record a row and raise when it failed (fail fast on contract breaks)."""
        self.add(*args, **kwargs)
        if not self.rows[-1]["result"] == "pass":
            raise AcceptanceFailure(str(self.rows[-1]["detail"]))

    @property
    def failures(self) -> list[dict[str, object]]:
        return [row for row in self.rows if row["result"] == "fail"]


# --------------------------------------------------------------------------- #
# Image inputs (in memory only)
# --------------------------------------------------------------------------- #


def held_out_path() -> Path:
    manifest = json.loads(TEST_MANIFEST.read_text(encoding="utf-8"))
    relative = manifest["items"][0]["path"]
    return REPO_ROOT / relative


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def rotated_portrait_bytes(source: Path) -> bytes:
    """Rotate real pixels 90° in memory: a genuine portrait-shaped upload."""
    with Image.open(source) as image:
        rotated = image.convert("RGB").transpose(Image.Transpose.ROTATE_90)
        buffer = io.BytesIO()
        rotated.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()


def exif_portrait_bytes(source: Path) -> bytes:
    """Landscape pixels tagged EXIF orientation 6 (decoder must rotate to portrait)."""
    with Image.open(source) as image:
        rgb = image.convert("RGB")
        # Keep the upload small enough to be quick; EXIF still drives orientation.
        rgb.thumbnail((1600, 1600))
        exif = Image.Exif()
        exif[274] = 6
        buffer = io.BytesIO()
        rgb.save(buffer, format="JPEG", quality=92, exif=exif.tobytes())
        return buffer.getvalue()


def poor_quality_bytes(source: Path) -> bytes:
    """Dark, heavily blurred, low-resolution variant of a real leaf."""
    with Image.open(source) as image:
        small = image.convert("RGB")
        # Stay above the 64 px hard dimension gate so this exercises quality
        # warnings, not the IMAGE_TOO_SMALL upload error.
        small.thumbnail((360, 360))
        arr = np.asarray(small).astype(np.float32) * 0.18
        blurred = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius=3.0)
        )
        buffer = io.BytesIO()
        blurred.save(buffer, format="JPEG", quality=70)
        return buffer.getvalue()


def blank_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 640), (250, 250, 248)).save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


class Backend:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=180.0)

    def close(self) -> None:
        self.client.close()

    def history(self) -> dict:
        response = self.client.get("/api/v1/history")
        response.raise_for_status()
        return response.json()

    def predict(
        self, content: bytes, filename: str, content_type: str
    ) -> tuple[httpx.Response, float]:
        start = time.perf_counter()
        response = self.client.post(
            "/api/v1/predict",
            files={"file": (filename, content, content_type)},
        )
        return response, (time.perf_counter() - start) * 1000.0


def _labelled_contract(
    recorder: Recorder,
    name: str,
    body: dict,
    elapsed_ms: float,
    *,
    category: str = "functional",
    expect_warning: str | None = None,
) -> None:
    problems: list[str] = []
    status = body.get("status")
    if status not in LABELLED_STATUSES:
        problems.append(f"status={status!r} is not a labelled result")
    try:
        uuid.UUID(str(body.get("prediction_id")))
    except (ValueError, TypeError):
        problems.append("missing/invalid prediction_id")

    scores = body.get("decision_scores") or {}
    if set(scores) != CLASSES:
        problems.append(f"decision_scores keys={sorted(scores)}")
    if body.get("score_kind") != "decision_margin":
        problems.append(f"score_kind={body.get('score_kind')!r}")
    if body.get("disease") not in CLASSES:
        problems.append(f"disease={body.get('disease')!r}")
    if "confidence" in body or "probability" in body:
        problems.append("response exposes confidence/probability")
    if any("confidence" in key for key in body):
        problems.append("response key mentions confidence")

    margin = body.get("margin")
    if scores and margin is not None:
        ordered = sorted(scores.values(), reverse=True)
        expected_margin = ordered[0] - ordered[1]
        if abs(float(margin) - expected_margin) > 1e-6:
            problems.append(f"margin {margin} != top-second {expected_margin}")

    severity = body.get("severity")
    if severity not in {None, "Mild", "Moderate", "Severe"}:
        problems.append(f"severity={severity!r}")
    if severity is not None and body.get("lesion_area_percentage") is None:
        problems.append("severity present without a lesion area")
    if not str(body.get("severity_disclaimer", "")).startswith(SEVERITY_DISCLAIMER_PREFIX):
        problems.append("severity disclaimer missing or reworded")

    artifacts = body.get("artifacts") or {}
    if set(artifacts) != {"original_url", "leaf_mask_url", "lesion_mask_url"}:
        problems.append(f"artifact URLs={sorted(artifacts)}")

    if body.get("status") == "uncertain" and not (
        body.get("warnings") or body.get("missing_features") or body.get("rejections")
    ):
        problems.append("uncertain result carries no warning/reason")

    warnings = list(body.get("warnings") or [])
    if expect_warning is not None and expect_warning not in warnings:
        problems.append(f"expected warning {expect_warning!r}, got {warnings}")

    recorder.add(
        name,
        category=category,
        passed=not problems,
        detail=(
            f"{status} | {body.get('disease')} | margin={margin} | "
            f"severity={severity} | lesion={body.get('lesion_area_percentage')} | "
            f"{elapsed_ms:.0f} ms | warnings={warnings}"
            + ("" if not problems else f" | PROBLEMS: {'; '.join(problems)}")
        ),
        evidence={
            "status": status,
            "disease": body.get("disease"),
            "decision_scores": scores,
            "margin": margin,
            "severity": severity,
            "lesion_area_percentage": body.get("lesion_area_percentage"),
            "lesion_reliable": body.get("lesion_reliable"),
            "warnings": warnings,
            "missing_features": body.get("missing_features"),
            "prediction_id": body.get("prediction_id"),
            "request_ms": round(elapsed_ms, 1),
            "stage_ms": body.get("stage_ms"),
        },
    )
    if problems:
        raise AcceptanceFailure(f"{name}: {'; '.join(problems)}")


def _expect_status(
    recorder: Recorder,
    name: str,
    response: httpx.Response,
    expected: int,
    *,
    category: str = "invalid-upload",
    required_reason: str | None = None,
) -> dict:
    body: dict = {}
    try:
        body = response.json()
    except ValueError:  # pragma: no cover - defensive
        body = {"raw": response.text[:200]}

    reason = body.get("reason_code")
    passed = response.status_code == expected and (
        required_reason is None or reason == required_reason
    )
    recorder.add(
        name,
        category=category,
        passed=passed,
        detail=(
            f"HTTP {response.status_code} (expected {expected}) | "
            f"reason={reason} | {body.get('message', '')}"
        ),
        evidence={"status_code": response.status_code, "body": body},
    )
    if not passed:
        raise AcceptanceFailure(f"{name}: expected HTTP {expected} ({required_reason})")
    return body


# --------------------------------------------------------------------------- #
# Preprocessing geometry evidence
# --------------------------------------------------------------------------- #


def geometry_evidence(label: str, content: bytes) -> dict[str, object]:
    result = run_segmentation(content, segmentation_config=load_segmentation_config())
    transform = result.transform
    if transform is None:
        return {"label": label, "leaf_found": False, "warning": "leaf not found"}

    crop_w, crop_h = transform.crop_box[2], transform.crop_box[3]
    # Integer pixel rounding makes the x/y scale factors differ slightly; a real
    # stretch would make the difference large. 0.5 % is the documentation boundary.
    working_deviation = abs(transform.working_scale_x - transform.working_scale_y) / max(
        transform.working_scale_x, transform.working_scale_y
    )
    resize_deviation = abs(transform.resize_scale_x - transform.resize_scale_y) / max(
        transform.resize_scale_x, transform.resize_scale_y
    )
    return {
        "label": label,
        "leaf_found": True,
        "source_width": transform.source_width,
        "source_height": transform.source_height,
        "source_aspect": round(transform.source_width / transform.source_height, 4),
        "working_width": transform.working_width,
        "working_height": transform.working_height,
        "working_scale": [round(transform.working_scale_x, 6), round(transform.working_scale_y, 6)],
        "crop_box": list(transform.crop_box),
        "crop_aspect": round(crop_w / crop_h, 4),
        "resize_scale": [round(transform.resize_scale_x, 6), round(transform.resize_scale_y, 6)],
        "resized_size": [transform.resized_width, transform.resized_height],
        "resized_aspect": round(transform.resized_width / transform.resized_height, 4),
        "pad": [transform.pad_left, transform.pad_top],
        "canvas_size": transform.canvas_size,
        "uniform_scale_max_deviation_pct": round(
            max(working_deviation, resize_deviation) * 100.0, 3
        ),
        "uniform_scale": working_deviation <= 0.005 and resize_deviation <= 0.005,
    }


# --------------------------------------------------------------------------- #
# Main acceptance flow
# --------------------------------------------------------------------------- #


def run(runtime_dir: Path, keep_runtime: bool, evidence_path: Path) -> int:
    recorder = Recorder()
    timings: list[float] = []
    stage_totals: list[float] = []
    labelled_ids: set[str] = set()

    def labelled(name: str, body: dict, elapsed_ms: float, **kwargs) -> None:
        """Record a labelled-result contract and remember its id for history checks."""
        _labelled_contract(recorder, name, body, elapsed_ms, **kwargs)
        labelled_ids.add(str(body["prediction_id"]))
    evidence: dict[str, object] = {
        "runtime_dir": display_path(runtime_dir),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    dataset_image = DATASET_DIR / "Brown spot" / "DSC_0105.jpg"
    held_out = held_out_path()
    for required in (
        dataset_image,
        held_out,
        INPUTS_DIR / "healthy rice leaf.jpg",
        INPUTS_DIR / "multiple leaves.jpg",
        INPUTS_DIR / "non rice leaf (wheat).jpg",
    ):
        if not required.is_file():
            print(f"FAIL: required input missing: {required}", file=sys.stderr)
            return 1

    # -- preprocessing geometry (in-process, before any server work) --------- #
    landscape_bytes = read_bytes(held_out)
    portrait_bytes = rotated_portrait_bytes(held_out)
    portrait_exif_bytes = exif_portrait_bytes(held_out)
    geometry = [
        geometry_evidence("held_out_landscape", landscape_bytes),
        geometry_evidence("portrait_rotated", portrait_bytes),
        geometry_evidence("portrait_exif_orientation_6", portrait_exif_bytes),
    ]
    for item in geometry:
        recorder.add(
            f"preprocessing resize/crop/letterbox - {item['label']}",
            category="preprocessing",
            passed=bool(item.get("leaf_found")) and bool(item.get("uniform_scale")),
            detail=(
                f"source={item.get('source_width')}x{item.get('source_height')} -> "
                f"working={item.get('working_width')}x{item.get('working_height')} -> "
                f"crop={item.get('crop_box')} -> resize={item.get('resized_size')} -> "
                f"pad={item.get('pad')} -> canvas={item.get('canvas_size')}x{item.get('canvas_size')} | "
                f"uniform scale={item.get('uniform_scale')} "
                f"(max deviation {item.get('uniform_scale_max_deviation_pct')} %)"
            ),
            evidence=item,
        )
    evidence["preprocessing_geometry"] = geometry

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    port = restart_check._free_port()
    first_log = runtime_dir / "acceptance-first.log"
    second_log = runtime_dir / "acceptance-restart.log"

    server = restart_check._start_server(runtime_dir, port, first_log)
    backend = Backend(f"http://127.0.0.1:{port}")
    try:
        health = restart_check._wait_for_health(server, port, first_log, "acceptance start")
        recorder.require(
            "health / model bundle",
            category="service",
            passed=bool(health.get("model_loaded")) and health.get("model_version") == "svm-v1.0.0",
            detail=f"{health}",
            evidence=health,
        )
        evidence["health_first"] = health

        # -- required-valid uploads ----------------------------------------- #
        dataset_response, dataset_ms = backend.predict(
            read_bytes(dataset_image), dataset_image.name, "image/jpeg"
        )
        _expect_status(recorder, "real dataset image is accepted", dataset_response, 200, category="smoke")
        dataset_body = dataset_response.json()
        labelled(
            "real dataset smoke prediction",
            dataset_body,
            dataset_ms,
            category="smoke",
        )
        timings.append(dataset_ms)
        stage_totals.append(float((dataset_body.get("stage_ms") or {}).get("total", 0.0)))
        evidence["dataset_smoke"] = dataset_body

        held_response, held_ms = backend.predict(
            landscape_bytes, held_out.name, "image/jpeg"
        )
        _expect_status(recorder, "held-out image is accepted", held_response, 200, category="smoke")
        held_body = held_response.json()
        labelled(
            "held-out smoke prediction (functional only, no tuning)",
            held_body,
            held_ms,
            category="smoke",
        )
        timings.append(held_ms)
        stage_totals.append(float((held_body.get("stage_ms") or {}).get("total", 0.0)))
        evidence["held_out_smoke"] = {
            "manifest_path": str(held_out.relative_to(REPO_ROOT)),
            "manifest_label": "bacterial_leaf_blight",
            "response": held_body,
        }

        landscape_response, landscape_ms = backend.predict(
            landscape_bytes, "landscape.jpg", "image/jpeg"
        )
        _expect_status(recorder, "landscape upload", landscape_response, 200)
        labelled(
            "landscape upload result", landscape_response.json(), landscape_ms,
            category="orientation",
        )
        timings.append(landscape_ms)

        portrait_response, portrait_ms = backend.predict(
            portrait_bytes, "portrait.jpg", "image/jpeg"
        )
        _expect_status(recorder, "portrait upload", portrait_response, 200)
        labelled(
            "portrait upload result (rotated real pixels)", portrait_response.json(),
            portrait_ms, category="orientation",
        )
        timings.append(portrait_ms)
        evidence["portrait_rotated"] = portrait_response.json()

        exif_response, exif_ms = backend.predict(
            portrait_exif_bytes, "portrait_exif.jpg", "image/jpeg"
        )
        _expect_status(recorder, "EXIF orientation 6 upload", exif_response, 200)
        labelled(
            "EXIF-portrait result", exif_response.json(), exif_ms,
            category="orientation",
        )
        timings.append(exif_ms)
        evidence["portrait_exif"] = exif_response.json()

        # -- multiple leaves / poor quality / unsupported content ------------ #
        multiple = INPUTS_DIR / "multiple leaves.jpg"
        multiple_response, multiple_ms = backend.predict(
            read_bytes(multiple), multiple.name, "image/jpeg"
        )
        _expect_status(recorder, "multiple-leaf image is handled without crashing", multiple_response, 200)
        multiple_body = multiple_response.json()
        multiple_ok = multiple_body.get("status") in LABELLED_STATUSES | {"rejected"}
        recorder.require(
            "multiple-leaf handling",
            category="edge-case",
            passed=multiple_ok,
            detail=(
                f"status={multiple_body.get('status')} | "
                f"warnings={multiple_body.get('warnings')} | "
                f"MULTIPLE_LEAVES={'MULTIPLE_LEAVES' in (multiple_body.get('warnings') or [])}"
            ),
            evidence=multiple_body,
        )
        if multiple_body.get("status") in LABELLED_STATUSES:
            labelled(
                "multiple-leaf result contract", multiple_body, multiple_ms,
                category="edge-case",
            )
            timings.append(multiple_ms)
        evidence["multiple_leaves"] = multiple_body

        poor_bytes = poor_quality_bytes(held_out)
        poor_response, poor_ms = backend.predict(poor_bytes, "poor_quality.jpg", "image/jpeg")
        _expect_status(recorder, "poor-quality image is handled", poor_response, 200)
        poor_body = poor_response.json()
        recorder.require(
            "poor-quality image honesty",
            category="edge-case",
            passed=poor_body.get("status") in LABELLED_STATUSES | {"rejected"},
            detail=(
                f"status={poor_body.get('status')} | warnings={poor_body.get('warnings')} | "
                f"rejections={poor_body.get('rejections')}"
            ),
            evidence=poor_body,
        )
        evidence["poor_quality"] = poor_body
        if poor_body.get("status") in LABELLED_STATUSES:
            labelled(
                "poor-quality labelled contract", poor_body, poor_ms,
                category="edge-case",
            )
            timings.append(poor_ms)

        for name, filename in (
            ("healthy-looking image", "healthy rice leaf.jpg"),
            ("non-rice image (wheat)", "non rice leaf (wheat).jpg"),
        ):
            path = INPUTS_DIR / filename
            response, elapsed = backend.predict(read_bytes(path), filename, "image/jpeg")
            _expect_status(recorder, f"{name} is handled", response, 200, category="edge-case")
            body = response.json()
            status = body.get("status")
            no_healthy_claim = status in LABELLED_STATUSES | {"rejected"} and status != "healthy"
            recorder.require(
                f"{name} makes no healthy claim",
                category="edge-case",
                passed=no_healthy_claim,
                detail=(
                    f"status={status} | disease={body.get('disease')} | "
                    f"warnings={body.get('warnings')} | rejections={body.get('rejections')}"
                ),
                evidence=body,
            )
            if status in LABELLED_STATUSES:
                labelled(
                    f"{name} labelled contract", body, elapsed, category="edge-case"
                )
                timings.append(elapsed)
            evidence["healthy" if "healthy" in name else "non_rice"] = body

        # -- valid image that must be rejected ------------------------------- #
        history_before_rejection = backend.history()
        rejected_response, rejected_ms = backend.predict(
            blank_bytes(), "blank.png", "image/png"
        )
        _expect_status(
            recorder,
            "valid but rejected image returns HTTP 200 + no prediction",
            rejected_response,
            200,
            category="rejection",
        )
        rejected_body = rejected_response.json()
        rejection_ok = (
            rejected_body.get("status") == "rejected"
            and "prediction_id" not in rejected_body
            and "artifacts" not in rejected_body
            and rejected_body.get("disease") is None
            and rejected_body.get("severity") is None
        )
        history_after_rejection = backend.history()
        recorder.require(
            "rejected valid image leaves no history row or artifact",
            category="rejection",
            passed=rejection_ok
            and history_after_rejection.get("count") == history_before_rejection.get("count"),
            detail=(
                f"status={rejected_body.get('status')} | reason={rejected_body.get('reason_code')} | "
                f"id={rejected_body.get('prediction_id')!r} | artifacts={rejected_body.get('artifacts')!r} | "
                f"history {history_before_rejection.get('count')} -> "
                f"{history_after_rejection.get('count')} | {rejected_ms:.0f} ms"
            ),
            evidence=rejected_body,
        )
        evidence["rejected_valid_image"] = rejected_body

        # -- invalid uploads ------------------------------------------------- #
        too_large = b"\x00" * (11 * 1024 * 1024)
        large_response, _ = backend.predict(too_large, "too_large.jpg", "image/jpeg")
        _expect_status(
            recorder, "oversize upload (11 MB) -> 413", large_response, 413,
            required_reason="FILE_TOO_LARGE",
        )

        text_response, _ = backend.predict(b"not an image", "notes.txt", "text/plain")
        _expect_status(
            recorder, "unsupported extension (txt) -> 415", text_response, 415,
            required_reason="UNSUPPORTED_FILE_TYPE",
        )

        corrupt_response, _ = backend.predict(b"\x89PNG\r\n\x1a\n_broken", "broken.png", "image/png")
        _expect_status(
            recorder, "corrupt image bytes -> 422", corrupt_response, 422,
            required_reason="INVALID_UPLOAD",
        )

        # -- history + artifacts -------------------------------------------- #
        history = backend.history()
        stored_ids = {item["prediction_id"] for item in history.get("items", [])}
        recorder.require(
            "history holds exactly the labelled results",
            category="history",
            passed=history.get("count") == len(labelled_ids) and stored_ids == labelled_ids,
            detail=(
                f"count={history.get('count')} expected={len(labelled_ids)} | "
                f"id mismatch={sorted(stored_ids ^ labelled_ids)}"
            ),
            evidence={
                "count": history.get("count"),
                "expected": len(labelled_ids),
                "id_mismatch": sorted(stored_ids ^ labelled_ids),
            },
        )
        evidence["history_before_clear"] = {
            "count": history.get("count"),
            "prediction_ids": [item["prediction_id"] for item in history.get("items", [])],
        }

        single = backend.client.get(f"/api/v1/history/{held_body['prediction_id']}")
        recorder.require(
            "single history row retrieval",
            category="history",
            passed=single.status_code == 200
            and single.json().get("prediction_id") == held_body["prediction_id"],
            detail=f"HTTP {single.status_code}",
            evidence=single.json() if single.status_code == 200 else {},
        )

        artifact_status: dict[str, int] = {}
        for kind, url in held_body["artifacts"].items():
            response = backend.client.get(url)
            artifact_status[kind] = response.status_code
            if response.status_code == 200:
                assert response.headers["content-type"] == "image/png"
                assert len(response.content) > 0
        recorder.require(
            "artifact retrieval returns real PNGs",
            category="artifacts",
            passed=set(artifact_status.values()) == {200},
            detail=f"{artifact_status}",
            evidence=artifact_status,
        )
        evidence["artifact_http_status"] = artifact_status

        rows_before_restart = backend.history().get("count")
        files_before_restart = sorted(
            str(path.relative_to(runtime_dir))
            for path in (runtime_dir / "artifacts").rglob("*")
            if path.is_file()
        )
    finally:
        backend.close()
        restart_check._stop_server(server, port, first_log, "acceptance stop")

    evidence["before_restart"] = {
        "history_rows": rows_before_restart,
        "artifact_files": files_before_restart,
        "exit_code": server.returncode,
    }

    # -- fresh process, same RUNTIME_DIR ------------------------------------ #
    restart = restart_check._start_server(runtime_dir, port, second_log)
    restarted = Backend(f"http://127.0.0.1:{port}")
    try:
        health_second = restart_check._wait_for_health(restart, port, second_log, "acceptance restart")
        history_after_restart = restarted.history()
        files_after_restart = [
            path
            for path in (runtime_dir / "artifacts").rglob("*")
            if path.is_file()
        ]
        old_artifact_status = {
            kind: restarted.client.get(url).status_code
            for kind, url in held_body["artifacts"].items()
        }
        recorder.require(
            "backend restart clears temporary history and artifacts",
            category="restart",
            passed=history_after_restart.get("count") == 0
            and not files_after_restart
            and set(old_artifact_status.values()) == {404},
            detail=(
                f"fresh pid={restart.pid} | same RUNTIME_DIR | "
                f"history {rows_before_restart} -> {history_after_restart.get('count')} | "
                f"artifact files {len(files_before_restart)} -> {len(files_after_restart)} | "
                f"old URLs {old_artifact_status}"
            ),
            evidence={
                "history_before": rows_before_restart,
                "history_after": history_after_restart.get("count"),
                "artifact_files_before": len(files_before_restart),
                "artifact_files_after": len(files_after_restart),
                "old_artifact_http_status": old_artifact_status,
                "health": health_second,
            },
        )
        evidence["restart"] = {
            "pid": restart.pid,
            "health": health_second,
            "history_after": history_after_restart.get("count"),
            "old_artifact_http_status": old_artifact_status,
        }

        # -- clear history on the restarted process -------------------------- #
        clear_target, clear_ms = restarted.predict(
            landscape_bytes, "clear-target.jpg", "image/jpeg"
        )
        _expect_status(recorder, "restarted process can predict", clear_target, 200, category="service")
        clear_body = clear_target.json()
        _labelled_contract(
            recorder, "restarted-process prediction contract", clear_body, clear_ms,
            category="service",
        )
        before_clear = restarted.history()
        deleted = restarted.client.delete("/api/v1/history")
        after_clear = restarted.history()
        artifact_after_clear = {
            kind: restarted.client.get(url).status_code
            for kind, url in clear_body["artifacts"].items()
        }
        remaining_files = [
            path for path in (runtime_dir / "artifacts").rglob("*") if path.is_file()
        ]
        recorder.require(
            "clear history removes rows, files and artifact URLs",
            category="history",
            passed=deleted.status_code == 200
            and deleted.json().get("deleted") == before_clear.get("count")
            and after_clear.get("count") == 0
            and not remaining_files
            and set(artifact_after_clear.values()) == {404},
            detail=(
                f"deleted={deleted.json().get('deleted')} | "
                f"history {before_clear.get('count')} -> {after_clear.get('count')} | "
                f"artifact files left={len(remaining_files)} | urls={artifact_after_clear}"
            ),
            evidence={
                "deleted": deleted.json().get("deleted"),
                "history_after": after_clear.get("count"),
                "artifact_http_status": artifact_after_clear,
            },
        )
        evidence["clear_history"] = {
            "deleted": deleted.json().get("deleted"),
            "history_after": after_clear.get("count"),
            "artifact_http_status": artifact_after_clear,
        }
    finally:
        restarted.close()
        restart_check._stop_server(restart, port, second_log, "acceptance restart stop")

    # -- timings ------------------------------------------------------------ #
    if timings:
        warm = timings[1:] if len(timings) > 1 else timings
        ordered = sorted(warm)
        p95_index = max(0, min(len(ordered) - 1, -(-95 * len(ordered) // 100) - 1))
        timing_summary = {
            "labelled_samples": len(timings),
            "first_request_cold_ms": round(timings[0], 1),
            "warm_samples": len(warm),
            "warm_mean_ms": round(statistics.fmean(warm), 1),
            "warm_p50_ms": round(statistics.median(warm), 1),
            "warm_p95_ms": round(ordered[p95_index], 1),
            "warm_max_ms": round(max(warm), 1),
            "warm_pipeline_stage_total_mean_ms": round(
                statistics.fmean(stage_totals[1:] if len(stage_totals) > 1 else stage_totals), 1
            )
            if stage_totals
            else None,
        }
        recorder.add(
            "response-time measurement (labelled uploads)",
            category="performance",
            passed=timing_summary["warm_p95_ms"] < 5000,
            detail=(
                f"first/cold={timing_summary['first_request_cold_ms']} ms | "
                f"warm n={timing_summary['warm_samples']} mean={timing_summary['warm_mean_ms']} ms | "
                f"p50={timing_summary['warm_p50_ms']} ms | p95={timing_summary['warm_p95_ms']} ms | "
                f"max={timing_summary['warm_max_ms']} ms"
            ),
            evidence=timing_summary,
        )
        evidence["timings"] = timing_summary

    evidence["checks"] = recorder.rows
    evidence["failures"] = recorder.failures
    evidence["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Evidence written to {display_path(evidence_path)}")

    if not keep_runtime:
        shutil.rmtree(runtime_dir, ignore_errors=True)

    if recorder.failures:
        print(f"\n{len(recorder.failures)} check(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nAll {len(recorder.rows)} acceptance checks passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--keep-runtime", action="store_true")
    args = parser.parse_args()

    runtime_dir = args.runtime_dir
    if not runtime_dir.is_absolute():
        runtime_dir = (REPO_ROOT / runtime_dir).resolve()
    evidence_path = args.evidence
    if not evidence_path.is_absolute():
        evidence_path = (REPO_ROOT / evidence_path).resolve()

    try:
        return run(runtime_dir, args.keep_runtime, evidence_path)
    except (AcceptanceFailure, restart_check.CheckFailure) as exc:
        print(f"\nACCEPTANCE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
