"""
Stage 1 & 2: Floor Plan Parser
- Detects walls (lines), rooms (enclosed regions), openings (doors/windows)
- Applies all hidden-trap mitigations:
  * Angle snapping (non-90 degree layouts)
  * Junction clustering (T vs L corners)
  * Coordinate rounding (3D handoff quality)
"""

import cv2
import numpy as np
from collections import defaultdict
from typing import Optional
import base64
import logging

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

ANGLE_SNAP_TOLERANCE = 5        # degrees — snap lines within ±5° of 0/90/180/270
JUNCTION_CLUSTER_RADIUS = 10    # pixels — merge endpoints closer than this
MIN_LINE_LENGTH = 30            # pixels — ignore very short detected segments
MAX_LINE_GAP = 10               # pixels — connect nearby collinear segments
HOUGH_THRESHOLD = 80            # votes required for a line
WALL_THICKNESS_EST = 15         # pixels — estimated wall thickness for 3D


# ── Main Entry Point ─────────────────────────────────────────────────────────

def parse_floor_plan(image_input) -> dict:
    """
    Full parsing pipeline. Accepts:
      - file path (str)
      - numpy array (already loaded image)
      - base64 encoded string

    Returns structured dict with walls, rooms, junctions, metadata.
    """
    img = _load_image(image_input)
    if img is None:
        raise ValueError("Could not load image. Check path or base64 input.")

    h, w = img.shape[:2]
    logger.info(f"Parsing image: {w}x{h}px")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = _detect_edges(gray)
    raw_lines = _detect_lines(edges)

    if raw_lines is None or len(raw_lines) == 0:
        logger.warning("No lines detected — returning empty result")
        return _empty_result(w, h)

    # Mitigation 1: snap all angles to 0/90/180/270
    snapped_lines = _snap_to_orthogonal(raw_lines, tolerance=ANGLE_SNAP_TOLERANCE)

    # Mitigation 2: merge duplicate/overlapping lines
    merged_lines = _merge_collinear_lines(snapped_lines)

    # Mitigation 3: cluster endpoints into clean junctions
    junctions, wall_segments = _build_junctions(merged_lines)

    # Extract room polygons from enclosed regions
    rooms = _extract_rooms(edges, img.shape)

    # Detect openings (doors/windows) — gap detection in walls
    openings = _detect_openings(merged_lines, edges)

    # Scale factor: convert pixels to meters (assume A4/standard plan)
    # Most floor plans show a scale bar; we default to 1px = 0.05m if no bar found
    scale_px_to_m = _estimate_scale(img, gray)

    # Mitigation 4: round all coordinates to integers for clean 3D handoff
    wall_segments = _round_coordinates(wall_segments)
    junctions = _round_coordinates(junctions)

    result = {
        "image_size": {"width": w, "height": h},
        "scale_px_to_m": scale_px_to_m,
        "walls": wall_segments,
        "junctions": junctions,
        "rooms": rooms,
        "openings": openings,
        "stats": {
            "total_walls": len(wall_segments),
            "total_rooms": len(rooms),
            "total_junctions": len(junctions),
            "total_openings": len(openings),
        },
        "fallback_used": False,
    }

    logger.info(f"Parse complete: {len(wall_segments)} walls, "
                f"{len(rooms)} rooms, {len(junctions)} junctions")
    return result


# ── Image Loading ─────────────────────────────────────────────────────────────

def _load_image(image_input):
    if isinstance(image_input, np.ndarray):
        return image_input
    if isinstance(image_input, str):
        # Check if base64
        if image_input.startswith("data:image") or len(image_input) > 260:
            try:
                if "," in image_input:
                    image_input = image_input.split(",")[1]
                img_bytes = base64.b64decode(image_input)
                nparr = np.frombuffer(img_bytes, np.uint8)
                return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.error(f"Base64 decode failed: {e}")
                return None
        # File path
        return cv2.imread(image_input)
    return None


# ── Edge Detection ────────────────────────────────────────────────────────────

def _detect_edges(gray: np.ndarray) -> np.ndarray:
    """Multi-step edge detection for clean floor plan lines."""
    # Denoise first
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    # Adaptive thresholding handles varying contrast in scanned plans
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # Canny on original for sharp edges
    edges_canny = cv2.Canny(blurred, 50, 150, apertureSize=3)

    # Combine both
    combined = cv2.bitwise_or(thresh, edges_canny)

    # Morphological cleanup — close small gaps in walls
    kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    return cleaned


# ── Line Detection ────────────────────────────────────────────────────────────

def _detect_lines(edges: np.ndarray):
    """Probabilistic Hough Transform for line segments."""
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=HOUGH_THRESHOLD,
        minLineLength=MIN_LINE_LENGTH,
        maxLineGap=MAX_LINE_GAP
    )
    return lines


# ── Angle Snapping ────────────────────────────────────────────────────────────

def _snap_to_orthogonal(lines, tolerance: float = 5.0) -> list:
    """
    Mitigation: Non-90° layouts.
    Snap line endpoints so all walls are exactly horizontal or vertical.
    Lines within ±tolerance degrees of 0/90/180/270 get snapped.
    """
    snapped = []
    snap_angles = [0, 90, 180, 270]

    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180

        closest = min(snap_angles, key=lambda a: min(abs(angle - a), abs(angle - a + 180)))
        diff = min(abs(angle - closest), abs(angle - closest + 180))

        if diff <= tolerance:
            # Snap: make line perfectly horizontal or vertical
            if closest in [0, 180]:
                # Horizontal — fix y to midpoint
                mid_y = round((y1 + y2) / 2)
                snapped.append([x1, mid_y, x2, mid_y])
            else:
                # Vertical — fix x to midpoint
                mid_x = round((x1 + x2) / 2)
                snapped.append([mid_x, y1, mid_x, y2])
        else:
            # Keep as-is (diagonal — rare in clean floor plans)
            snapped.append([x1, y1, x2, y2])

    return snapped


# ── Line Merging ──────────────────────────────────────────────────────────────

def _merge_collinear_lines(lines: list, gap_threshold: int = 15) -> list:
    """
    Merge overlapping or close collinear line segments.
    Groups lines by orientation and position, merges within same row/column.
    """
    horizontals = defaultdict(list)
    verticals = defaultdict(list)

    for x1, y1, x2, y2 in lines:
        if y1 == y2:  # horizontal
            horizontals[y1].append((min(x1, x2), max(x1, x2)))
        elif x1 == x2:  # vertical
            verticals[x1].append((min(y1, y2), max(y1, y2)))

    merged = []

    for y, segments in horizontals.items():
        merged.extend(_merge_segments_1d(segments, gap_threshold,
                                         axis='h', fixed=y))

    for x, segments in verticals.items():
        merged.extend(_merge_segments_1d(segments, gap_threshold,
                                         axis='v', fixed=x))

    return merged


def _merge_segments_1d(segments: list, gap: int, axis: str, fixed: int) -> list:
    """Merge 1D intervals (x1,x2) that are close or overlapping."""
    if not segments:
        return []
    sorted_segs = sorted(segments)
    result = []
    cur_start, cur_end = sorted_segs[0]

    for start, end in sorted_segs[1:]:
        if start <= cur_end + gap:
            cur_end = max(cur_end, end)
        else:
            result.append(_seg_to_wall(cur_start, cur_end, axis, fixed))
            cur_start, cur_end = start, end

    result.append(_seg_to_wall(cur_start, cur_end, axis, fixed))
    return result


def _seg_to_wall(start, end, axis, fixed) -> dict:
    if axis == 'h':
        return {"x1": start, "y1": fixed, "x2": end, "y2": fixed,
                "orientation": "horizontal", "length_px": end - start}
    else:
        return {"x1": fixed, "y1": start, "x2": fixed, "y2": end,
                "orientation": "vertical", "length_px": end - start}


# ── Junction Detection ────────────────────────────────────────────────────────

def _build_junctions(walls: list) -> tuple:
    """
    Mitigation: Junction detection.
    Collect all endpoints, cluster nearby ones, classify junction type.
    T-junction = 3 incident walls, L-corner = 2, X-crossing = 4.
    """
    # Collect all endpoints
    endpoints = []
    for i, wall in enumerate(walls):
        endpoints.append((wall["x1"], wall["y1"], i, "start"))
        endpoints.append((wall["x2"], wall["y2"], i, "end"))

    # Cluster endpoints within JUNCTION_CLUSTER_RADIUS
    clusters = []
    used = set()

    for i, (x1, y1, wi1, pos1) in enumerate(endpoints):
        if i in used:
            continue
        cluster = [(x1, y1, wi1, pos1)]
        used.add(i)
        for j, (x2, y2, wi2, pos2) in enumerate(endpoints):
            if j in used:
                continue
            if abs(x2 - x1) <= JUNCTION_CLUSTER_RADIUS and \
               abs(y2 - y1) <= JUNCTION_CLUSTER_RADIUS:
                cluster.append((x2, y2, wi2, pos2))
                used.add(j)
        clusters.append(cluster)

    junctions = []
    for cluster in clusters:
        cx = round(np.mean([p[0] for p in cluster]))
        cy = round(np.mean([p[1] for p in cluster]))
        wall_ids = list(set(p[2] for p in cluster))
        degree = len(wall_ids)

        j_type = {1: "endpoint", 2: "L-corner", 3: "T-junction",
                  4: "X-crossing"}.get(degree, f"deg-{degree}")

        junctions.append({
            "x": cx, "y": cy,
            "type": j_type,
            "degree": degree,
            "connected_walls": wall_ids
        })

    # Snap wall endpoints to their cluster centroid
    junction_map = {}
    for junc in junctions:
        for wid in junc["connected_walls"]:
            if wid not in junction_map:
                junction_map[wid] = []
            junction_map[wid].append(junc)

    for i, wall in enumerate(walls):
        juncs = junction_map.get(i, [])
        if len(juncs) >= 1:
            # Find which junction is closer to start vs end
            for j in juncs:
                d_start = abs(j["x"] - wall["x1"]) + abs(j["y"] - wall["y1"])
                d_end = abs(j["x"] - wall["x2"]) + abs(j["y"] - wall["y2"])
                if d_start < d_end:
                    wall["x1"], wall["y1"] = j["x"], j["y"]
                else:
                    wall["x2"], wall["y2"] = j["x"], j["y"]

    return junctions, walls


# ── Room Extraction ───────────────────────────────────────────────────────────

def _extract_rooms(edges: np.ndarray, img_shape: tuple) -> list:
    """
    Find enclosed regions (rooms) using contour detection on the edge map.
    Returns list of room polygons with bounding boxes.
    """
    h, w = img_shape[:2]

    # Fill gaps for closed contour detection
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    # Invert for flood fill detection of enclosed areas
    inverted = cv2.bitwise_not(closed)

    contours, hierarchy = cv2.findContours(
        inverted, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    rooms = []
    min_area = (w * h) * 0.005   # at least 0.5% of image = valid room
    max_area = (w * h) * 0.80    # at most 80% of image (skip outer boundary)

    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue

        # Approximate polygon
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        pts = approx.reshape(-1, 2).tolist()

        x, y, rw, rh = cv2.boundingRect(contour)

        rooms.append({
            "id": f"room_{i}",
            "polygon": pts,
            "bounding_box": {"x": x, "y": y, "width": rw, "height": rh},
            "area_px": float(area),
            "centroid": {
                "x": round(x + rw / 2),
                "y": round(y + rh / 2)
            },
            "label": "unknown"   # labelling done in geometry.py
        })

    # Sort by area descending (largest rooms first)
    rooms.sort(key=lambda r: r["area_px"], reverse=True)
    return rooms


# ── Opening Detection ─────────────────────────────────────────────────────────

def _detect_openings(walls: list, edges: np.ndarray) -> list:
    """
    Detect gaps in walls (doors/windows).
    A gap = two collinear wall segments with a space between them.
    """
    openings = []
    MIN_OPENING = 20   # px — min gap to count as door/window
    MAX_OPENING = 120  # px — max gap (wider = probably missing wall, not door)

    # Group walls by orientation and position
    h_walls = defaultdict(list)
    v_walls = defaultdict(list)

    for w in walls:
        if w["orientation"] == "horizontal":
            h_walls[w["y1"]].append(w)
        else:
            v_walls[w["x1"]].append(w)

    for y, segs in h_walls.items():
        segs_sorted = sorted(segs, key=lambda s: s["x1"])
        for i in range(len(segs_sorted) - 1):
            gap = segs_sorted[i + 1]["x1"] - segs_sorted[i]["x2"]
            if MIN_OPENING <= gap <= MAX_OPENING:
                openings.append({
                    "type": "opening",
                    "orientation": "horizontal",
                    "x1": segs_sorted[i]["x2"],
                    "y1": y,
                    "x2": segs_sorted[i + 1]["x1"],
                    "y2": y,
                    "width_px": gap
                })

    for x, segs in v_walls.items():
        segs_sorted = sorted(segs, key=lambda s: s["y1"])
        for i in range(len(segs_sorted) - 1):
            gap = segs_sorted[i + 1]["y1"] - segs_sorted[i]["y2"]
            if MIN_OPENING <= gap <= MAX_OPENING:
                openings.append({
                    "type": "opening",
                    "orientation": "vertical",
                    "x1": x,
                    "y1": segs_sorted[i]["y2"],
                    "x2": x,
                    "y2": segs_sorted[i + 1]["y1"],
                    "width_px": gap
                })

    return openings


# ── Scale Estimation ──────────────────────────────────────────────────────────

def _estimate_scale(img: np.ndarray, gray: np.ndarray) -> float:
    """
    Try to detect a scale bar in the image.
    Falls back to default (1px = 0.05m → typical for 200dpi A4 plan).
    """
    # Simple heuristic: look for a thin horizontal line near bottom of image
    # that's isolated (scale bar). For now, return default.
    # TODO: OCR-based scale bar reading (optional extension)
    return 0.05   # meters per pixel (default)


# ── Utility ───────────────────────────────────────────────────────────────────

def _round_coordinates(items: list) -> list:
    """Round all coordinate values to integers for clean 3D handoff."""
    coord_keys = {"x", "y", "x1", "y1", "x2", "y2"}
    for item in items:
        for k in coord_keys:
            if k in item:
                item[k] = int(round(item[k]))
    return items


def _empty_result(w: int, h: int) -> dict:
    return {
        "image_size": {"width": w, "height": h},
        "scale_px_to_m": 0.05,
        "walls": [], "junctions": [], "rooms": [], "openings": [],
        "stats": {"total_walls": 0, "total_rooms": 0,
                  "total_junctions": 0, "total_openings": 0},
        "fallback_used": True,
    }


# ── Manual Fallback ───────────────────────────────────────────────────────────

def build_manual_result(walls: list, image_size: dict) -> dict:
    """
    Fallback clause: if CV fails, team manually defines wall coordinates.
    This will be disclosed during demo as per rules.
    walls format: [{"x1":0,"y1":0,"x2":100,"y2":0,"orientation":"horizontal"}, ...]
    """
    for i, w in enumerate(walls):
        w["length_px"] = int(abs(w.get("x2", 0) - w.get("x1", 0)) or
                             abs(w.get("y2", 0) - w.get("y1", 0)))
        w["id"] = f"wall_{i}"

    return {
        "image_size": image_size,
        "scale_px_to_m": 0.05,
        "walls": _round_coordinates(walls),
        "junctions": [],
        "rooms": [],
        "openings": [],
        "stats": {"total_walls": len(walls), "total_rooms": 0,
                  "total_junctions": 0, "total_openings": 0},
        "fallback_used": True,
    }
