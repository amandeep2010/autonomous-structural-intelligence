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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        three_payload = _build_three_payload(geometry_result)

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
            "materials": material_result,
            "report": report,
        }

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
            "three_js": _build_three_payload(geometry_result),
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

def _build_three_payload(geometry_result: dict) -> dict:
    """
    Convert geometry to Three.js-ready format.
    Coordinates scaled to meters and centered at origin.
    """
    walls = geometry_result.get("walls", [])
    rooms = geometry_result.get("rooms", [])
    boundary = geometry_result.get("boundary", {})
    scale = geometry_result.get("scale_px_to_m", 0.05)

    if not walls:
        return {"walls": [], "rooms": [], "floor_dimensions": {}}

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

    return {
        "walls": three_walls,
        "rooms": three_rooms,
        "floor_dimensions": {
            "width_m": floor_w_m,
            "depth_m": floor_d_m,
            "height_m": 3.0,
        },
        "scale_used": float(scale),
    }


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
