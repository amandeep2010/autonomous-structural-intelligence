"""
FastAPI Backend — Autonomous Structural Intelligence System
Exposes:
  POST /api/parse          → Stage 1+2: parse image, reconstruct geometry
  POST /api/analyse        → Stage 4+5: material tradeoff + explainability
  POST /api/pipeline       → Full pipeline in one call (primary endpoint)
  GET  /api/health         → Health check
  POST /api/fallback       → Manual coordinate input (fallback clause)
"""

import os
import json
import math
import logging
import traceback
import hashlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pipeline.parser import parse_floor_plan, build_manual_result
from pipeline.geometry import reconstruct_geometry
from pipeline.material import analyse_materials
from pipeline.explainer import generate_report
from pipeline.validator import verify_generated_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
UPLOADS_DIR = Path(__file__).resolve().parent / "data" / "uploads"

# ── Numpy JSON Fix ────────────────────────────────────────────────────────────

class NumpyEncoder(json.JSONEncoder):
    """Converts numpy types to native Python types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)

def to_json_safe(data):
    """Recursively convert all numpy types in a dict to JSON-safe Python types."""
    return json.loads(json.dumps(data, cls=NumpyEncoder))


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Autonomous Structural Intelligence System",
    description="Floor Plan Parser · 3D Generator · Material Optimiser",
    version="1.0.0"
)

# CORS — allow React frontend on any port during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "pipeline": "ready"}


@app.get("/api/history")
def get_history(limit: int = 20):
    limit = max(1, min(limit, 100))
    return {"success": True, "items": _list_saved_analyses(limit=limit)}


@app.get("/api/history/{analysis_id}")
def get_history_item(analysis_id: str):
    payload = _load_saved_analysis_payload(analysis_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Saved analysis not found")
    return JSONResponse(to_json_safe(payload))


# ── Full Pipeline (primary endpoint) ─────────────────────────────────────────

@app.post("/api/pipeline")
async def run_pipeline(file: UploadFile = File(...)):
    """
    Main endpoint. Upload a floor plan image.
    Returns: walls, rooms, 3D data, material recommendations, explanations.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        logger.info(f"Pipeline started: {file.filename}, size={img.shape}")

        # Stage 1+2: Parse + Geometry
        parse_result = parse_floor_plan(img)
        geometry_result = reconstruct_geometry(parse_result)

        # Stage 4: Material analysis
        material_result = analyse_materials(geometry_result)

        # Stage 5: Explainability
        report = generate_report(material_result, geometry_result)

        # Build 3D-ready payload for Three.js
        three_payload = _build_three_payload(
            geometry_result,
            parse_result.get("openings", []),
            parse_result.get("labels", []),
        )
        verification = verify_generated_model(img, parse_result, three_payload)
        artifacts = _build_artifacts(img, parse_result.get("openings", []))

        payload = {
            "success": True,
            "fallback_used": geometry_result.get("fallback_used", False),
            "parse": {
                "stats": parse_result.get("stats", {}),
                "image_size": parse_result.get("image_size", {}),
                "scale_px_to_m": parse_result.get("scale_px_to_m", 0.05),
                "openings": parse_result.get("openings", []),
            },
            "geometry": {
                "stats": geometry_result.get("stats", {}),
                "walls": geometry_result.get("walls", []),
                "rooms": geometry_result.get("rooms", []),
                "boundary": geometry_result.get("boundary", {}),
                "structural_concerns": geometry_result.get("structural_concerns", []),
            },
            "three_js": three_payload,
            "artifacts": artifacts,
            "verification": verification,
            "materials": material_result,
            "report": report,
        }
        payload["storage"] = _persist_analysis(file.filename, contents, payload)

        return JSONResponse(to_json_safe(payload))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline error: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


# ── Stage 1+2 Only ────────────────────────────────────────────────────────────

@app.post("/api/parse")
async def parse_only(file: UploadFile = File(...)):
    """Parse floor plan image — returns walls, rooms, junctions."""
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        parse_result = parse_floor_plan(img)
        geometry_result = reconstruct_geometry(parse_result)

        payload = {
            "success": True,
            "parse": parse_result,
            "geometry": geometry_result,
            "artifacts": _build_artifacts(img, parse_result.get("openings", [])),
            "three_js": _build_three_payload(
                geometry_result,
                parse_result.get("openings", []),
                parse_result.get("labels", []),
            ),
        }

        return JSONResponse(to_json_safe(payload))

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ── Fallback: Manual Coordinates ──────────────────────────────────────────────

@app.post("/api/fallback")
async def manual_input(data: dict = Body(...)):
    """
    Fallback clause: team manually defines wall coordinates.
    Disclosed during demo as per hackathon rules.

    Body format:
    {
      "walls": [{"x1":0,"y1":0,"x2":500,"y2":0,"orientation":"horizontal"}, ...],
      "image_size": {"width": 800, "height": 600},
      "disclose_fallback": true
    }
    """
    try:
        walls = data.get("walls", [])
        image_size = data.get("image_size", {"width": 800, "height": 600})

        if not walls:
            raise HTTPException(
                status_code=400,
                detail="Provide at least one wall in 'walls' array"
            )

        parse_result = build_manual_result(walls, image_size)
        geometry_result = reconstruct_geometry(parse_result)
        material_result = analyse_materials(geometry_result)
        report = generate_report(material_result, geometry_result)
        three_payload = _build_three_payload(geometry_result)
        verification = {
            "summary": "Verification skipped for manual fallback input.",
            "confidence": "medium",
            "issues": [],
            "counts": {"parsed_windows": 0, "verified_window_candidates": 0, "unmatched_window_candidates": 0, "doors": 0, "labels": 0},
            "missing_window_candidates": [],
        }

        payload = {
            "success": True,
            "fallback_used": True,
            "fallback_disclosed": data.get("disclose_fallback", True),
            "geometry": {
                "stats": geometry_result.get("stats", {}),
                "walls": geometry_result.get("walls", []),
                "rooms": geometry_result.get("rooms", []),
                "boundary": geometry_result.get("boundary", {}),
            },
            "three_js": three_payload,
            "verification": verification,
            "materials": material_result,
            "report": report,
        }

        return JSONResponse(to_json_safe(payload))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ── Three.js Payload Builder ──────────────────────────────────────────────────

def _build_three_payload(
    geometry_result: dict,
    openings: Optional[list] = None,
    labels: Optional[list] = None,
) -> dict:
    """
    Convert geometry to Three.js-ready format.
    Coordinates scaled to meters and centered at origin.
    """
    walls = geometry_result.get("walls", [])
    rooms = geometry_result.get("rooms", [])
    boundary = geometry_result.get("boundary", {})
    scale = geometry_result.get("scale_px_to_m", 0.05)

    openings = openings or []
    labels = labels or []

    if not walls:
        return {"walls": [], "rooms": [], "labels": [], "doors": [], "windows": [], "floor_dimensions": {}}

    # Center offset — move building to origin
    center_x = (boundary.get("min_x", 0) + boundary.get("max_x", 0)) / 2
    center_y = (boundary.get("min_y", 0) + boundary.get("max_y", 0)) / 2

    three_walls = []
    for wall in walls:
        x1_m = (wall["x1"] - center_x) * scale
        y1_m = (wall["y1"] - center_y) * scale
        x2_m = (wall["x2"] - center_x) * scale
        y2_m = (wall["y2"] - center_y) * scale

        length_m = wall.get("length_m", wall["length_px"] * scale)

        pos_x = (x1_m + x2_m) / 2
        pos_z = (y1_m + y2_m) / 2

        rotation_y = 0.0 if wall["orientation"] == "horizontal" else math.pi / 2

        three_walls.append({
            "id": wall.get("id", "wall"),
            "position": {
                "x": round(float(pos_x), 3),
                "y": 1.5,
                "z": round(float(pos_z), 3),
            },
            "rotation_y": rotation_y,
            "dimensions": {
                "width": round(float(length_m), 3),
                "height": 3.0,
                "depth": 0.3,
            },
            "load_bearing": bool(wall.get("load_bearing", False)),
            "color": "#8B4513" if wall.get("load_bearing") else "#D2B48C",
            "orientation": wall.get("orientation"),
            "span_class": wall.get("span_class", "short"),
        })

    floor_w_m = round(float(boundary.get("width_px", 0)) * scale, 2)
    floor_d_m = round(float(boundary.get("height_px", 0)) * scale, 2)

    three_rooms = []
    for room in rooms:
        cx_m = round((float(room["centroid"]["x"]) - center_x) * scale, 3)
        cz_m = round((float(room["centroid"]["y"]) - center_y) * scale, 3)
        three_rooms.append({
            "id": room.get("id"),
            "label": room.get("label", "Room"),
            "centroid_3d": {"x": cx_m, "y": 0.1, "z": cz_m},
            "area_m2": float(room.get("area_m2", 0)),
        })

    three_doors = []
    three_windows = []
    for opening in openings:
        arc = opening.get("door_arc")
        if opening.get("type") == "door" and arc:
            hinge_x = round((float(arc["hinge"]["x"]) - center_x) * scale, 3)
            hinge_z = round((float(arc["hinge"]["y"]) - center_y) * scale, 3)
            leaf_x = round((float(arc["leaf_end"]["x"]) - center_x) * scale, 3)
            leaf_z = round((float(arc["leaf_end"]["y"]) - center_y) * scale, 3)
            three_doors.append({
                "id": opening.get("id", f"door_{len(three_doors)}"),
                "hinge": {"x": hinge_x, "y": 0.03, "z": hinge_z},
                "leaf_end": {"x": leaf_x, "y": 0.03, "z": leaf_z},
                "radius_m": round(float(arc["radius_px"]) * scale, 3),
                "start_angle_rad": round(math.radians(float(arc["start_angle_deg"])), 6),
                "end_angle_rad": round(math.radians(float(arc["end_angle_deg"])), 6),
            })
        elif opening.get("type") == "window":
            cx = opening.get("center", {}).get("x", (opening["x1"] + opening["x2"]) / 2)
            cy = opening.get("center", {}).get("y", (opening["y1"] + opening["y2"]) / 2)
            width_m = max(abs(opening["x2"] - opening["x1"]), abs(opening["y2"] - opening["y1"])) * scale
            thickness_m = max(min(abs(opening["x2"] - opening["x1"]), abs(opening["y2"] - opening["y1"])) * scale, 0.08)
            three_windows.append({
                "id": opening.get("id", f"window_{len(three_windows)}"),
                "position": {
                    "x": round((float(cx) - center_x) * scale, 3),
                    "y": 1.45,
                    "z": round((float(cy) - center_y) * scale, 3),
                },
                "orientation": opening.get("orientation"),
                "dimensions": {
                    "width": round(float(width_m), 3),
                    "height": 1.2,
                    "depth": round(float(thickness_m), 3),
                },
                "edge": opening.get("edge"),
            })

    three_labels = []
    for region in labels:
        cx_m = round((float(region["center"]["x"]) - center_x) * scale, 3)
        cz_m = round((float(region["center"]["y"]) - center_y) * scale, 3)
        three_labels.append({
            "id": f"label_{len(three_labels)}",
            "text": region.get("text", ""),
            "position": {"x": cx_m, "y": 0.03, "z": cz_m},
        })

    return {
        "walls": three_walls,
        "rooms": three_rooms,
        "labels": three_labels,
        "doors": three_doors,
        "windows": three_windows,
        "floor_dimensions": {
            "width_m": floor_w_m,
            "depth_m": floor_d_m,
            "height_m": 3.0,
        },
        "scale_used": float(scale),
    }


def _persist_analysis(filename: str, contents: bytes, payload: dict) -> dict:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    analysis_id = _build_analysis_id(filename, contents)
    run_dir = UPLOADS_DIR / analysis_id
    run_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(filename or "upload.png")
    image_path = run_dir / safe_name
    json_path = run_dir / "analysis.json"
    meta_path = run_dir / "meta.json"

    image_path.write_bytes(contents)
    json_path.write_text(json.dumps(to_json_safe(payload), indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps({
        "analysis_id": analysis_id,
        "original_filename": filename,
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "sha256": hashlib.sha256(contents).hexdigest(),
    }, indent=2), encoding="utf-8")

    return {
        "analysis_id": analysis_id,
        "saved": True,
        "image_path": str(image_path),
        "analysis_path": str(json_path),
    }


def _build_artifacts(image: np.ndarray, openings: list) -> dict:
    annotated = _render_annotated_image(image, openings)
    success, buffer = cv2.imencode(".png", annotated)
    if not success:
        raise ValueError("Could not encode annotated image artifact")

    return {
        "annotated_image_base64": base64.b64encode(buffer.tobytes()).decode("ascii"),
        "annotated_image_mime": "image/png",
        "door_count": sum(1 for opening in openings if opening.get("type") == "door"),
    }


def _render_annotated_image(image: np.ndarray, openings: list) -> np.ndarray:
    annotated = image.copy()
    for opening in openings:
        if opening.get("type") != "door":
            continue

        bbox = opening.get("bbox")
        if not bbox:
            bbox = _fallback_bbox_from_opening(opening, image.shape)

        x1 = max(0, int(bbox.get("x", 0)))
        y1 = max(0, int(bbox.get("y", 0)))
        x2 = min(image.shape[1] - 1, x1 + max(1, int(bbox.get("width", 1))))
        y2 = min(image.shape[0] - 1, y1 + max(1, int(bbox.get("height", 1))))

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (36, 28, 237), 3)
        label_y = max(20, y1 - 10)
        cv2.putText(
            annotated,
            "DOOR",
            (x1, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (36, 28, 237),
            2,
            cv2.LINE_AA,
        )

    return annotated


def _fallback_bbox_from_opening(opening: dict, image_shape: tuple) -> dict:
    image_h, image_w = image_shape[:2]
    x1 = min(int(opening.get("x1", 0)), int(opening.get("x2", 0)))
    y1 = min(int(opening.get("y1", 0)), int(opening.get("y2", 0)))
    x2 = max(int(opening.get("x1", 0)), int(opening.get("x2", 0)))
    y2 = max(int(opening.get("y1", 0)), int(opening.get("y2", 0)))
    padding = max(8, int(round(float(opening.get("width_px", 24)) * 0.2)))

    return {
        "x": max(0, x1 - padding),
        "y": max(0, y1 - padding),
        "width": max(1, min(image_w - 1, x2 + padding) - max(0, x1 - padding)),
        "height": max(1, min(image_h - 1, y2 + padding) - max(0, y1 - padding)),
    }


def _build_analysis_id(filename: str, contents: bytes) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(contents).hexdigest()[:10]
    stem = Path(filename or "upload").stem
    return f"{timestamp}_{_safe_slug(stem)}_{digest}"


def _safe_filename(filename: str) -> str:
    path = Path(filename or "upload.png")
    return f"{_safe_slug(path.stem)}{path.suffix or '.png'}"


def _list_saved_analyses(limit: int = 20) -> list:
    if not UPLOADS_DIR.exists():
        return []

    items = []
    run_dirs = sorted(
        [path for path in UPLOADS_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )

    for run_dir in run_dirs:
        meta_path = run_dir / "meta.json"
        analysis_path = run_dir / "analysis.json"
        if not meta_path.exists() or not analysis_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Skipping unreadable saved analysis in %s", run_dir)
            continue

        items.append(_summarize_saved_analysis(meta, payload))
        if len(items) >= limit:
            break

    return items


def _load_saved_analysis_payload(analysis_id: str) -> Optional[dict]:
    if not analysis_id or "/" in analysis_id or "\\" in analysis_id or ".." in analysis_id:
        return None

    run_dir = UPLOADS_DIR / analysis_id
    analysis_path = run_dir / "analysis.json"
    if not analysis_path.exists():
        return None

    try:
        return json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load saved analysis %s", analysis_id)
        return None


def _summarize_saved_analysis(meta: dict, payload: dict) -> dict:
    three_data = payload.get("three_js", {})
    geometry = payload.get("geometry", {})
    verification = payload.get("verification", {})

    return {
        "analysis_id": meta.get("analysis_id"),
        "original_filename": meta.get("original_filename"),
        "saved_at": meta.get("saved_at"),
        "fallback_used": bool(payload.get("fallback_used", False)),
        "wall_count": len(three_data.get("walls", [])),
        "room_count": len(three_data.get("rooms", [])),
        "window_count": len(three_data.get("windows", [])),
        "door_count": len(three_data.get("doors", [])),
        "load_bearing_count": sum(1 for wall in three_data.get("walls", []) if wall.get("load_bearing")),
        "issue_count": len(verification.get("issues", [])),
        "boundary": geometry.get("boundary", {}),
    }


def _safe_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return "-".join(part for part in slug.split("-") if part) or "upload"


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
