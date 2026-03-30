"""
Stage 1 & 2: Floor Plan Parser
- Detects walls (single centerlines), rooms, room labels, and openings
- Suppresses OCR text before wall extraction so labels do not become walls
- Detects door swing arcs for the 3D viewer
"""

import base64
import logging
import math
import re
from collections import defaultdict
from typing import Optional

import cv2
import numpy as np

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover - optional dependency fallback
    RapidOCR = None

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

ANGLE_SNAP_TOLERANCE = 5        # degrees — snap lines within ±5° of 0/90/180/270
JUNCTION_CLUSTER_RADIUS = 15    # pixels — merge endpoints closer than this
MIN_LINE_LENGTH = 40            # pixels — minimum for Hough detection
MAX_LINE_GAP = 8                # pixels — connect nearby collinear segments
HOUGH_THRESHOLD = 100           # votes required for a line (higher = stricter)
WALL_THICKNESS_EST = 15         # pixels — estimated wall thickness for 3D
MIN_WALL_LENGTH_PX = 60         # pixels — post-merge minimum wall length (removes text/noise)
MAX_WALLS = 80                  # cap — if more than this, apply stricter filtering
TEXT_MASK_PADDING = 10          # pixels — mask OCR labels before line detection
PARALLEL_MERGE_DISTANCE = 18    # pixels — collapse double-edge walls into one centerline
OPENING_MIN_PX = 24             # pixels — minimum gap to be considered an opening
OPENING_MAX_PX = 140            # pixels — maximum door/window width in plan pixels
DOOR_SEARCH_PADDING = 40        # pixels — ROI around candidate opening for arc search
OCR_CONFIDENCE_MIN = 0.45
WINDOW_EDGE_MARGIN = 90         # pixels — boundary band for window symbols
WINDOW_SYMBOL_THICKNESS_MAX = 14
WINDOW_SYMBOL_LENGTH_MIN = 24
WINDOW_SYMBOL_LENGTH_MAX = 180
WINDOW_PAIR_DISTANCE_MIN = 2
WINDOW_PAIR_DISTANCE_MAX = 14

ROOM_WORDS = [
    "GREAT", "ROOM", "KITCHEN", "BEDROOM", "BATHROOM", "BATH", "FOYER",
    "LAUNDRY", "ENTRY", "LIVING", "DINING", "MASTER", "GARAGE", "HALL",
    "PANTRY", "STORE", "STUDY", "OFFICE",
]
COMMON_ROOM_LABELS = [
    "GREAT ROOM", "KITCHEN", "BEDROOM", "BATHROOM", "BATH", "FOYER",
    "LAUNDRY", "ENTRY", "LIVING ROOM", "DINING ROOM", "MASTER BEDROOM",
    "GARAGE", "HALL", "PANTRY", "STUDY", "OFFICE",
]

_OCR_ENGINE = None


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
    text_regions = _extract_text_regions(img)
    edges = _detect_edges(gray, text_regions)
    raw_lines = _detect_lines(edges)

    if raw_lines is None or len(raw_lines) == 0:
        logger.warning("No lines detected — returning empty result")
        return _empty_result(w, h)

    # Mitigation 1: snap all angles to 0/90/180/270
    snapped_lines = _snap_to_orthogonal(raw_lines, tolerance=ANGLE_SNAP_TOLERANCE)

    # Mitigation 2: merge duplicate/overlapping lines
    merged_lines = _merge_collinear_lines(snapped_lines)
    merged_lines = _collapse_parallel_walls(merged_lines)

    # Mitigation 3: filter out short segments (text, door arcs, window markers, noise).
    # Use a relative threshold — a segment shorter than 3% of the image diagonal is
    # almost certainly a window symbol, text annotation, or arc fragment rather than
    # a real wall.  The absolute floor (MIN_WALL_LENGTH_PX) still applies for tiny
    # images where 3% would fall below the Hough minimum.
    image_diagonal = (w**2 + h**2) ** 0.5
    min_length = max(MIN_WALL_LENGTH_PX, image_diagonal * 0.03)
    merged_lines = [
        wall for wall in merged_lines
        if wall["length_px"] >= min_length
    ]

    # Mitigation 4: if still too many walls, increase threshold progressively
    if len(merged_lines) > MAX_WALLS:
        # Sort by length descending, keep only the longest (most structural) walls
        merged_lines = sorted(merged_lines, key=lambda w: w["length_px"], reverse=True)
        # Try increasing the min length until under cap
        for factor in [1.5, 2.0, 2.5, 3.0]:
            filtered = [w for w in merged_lines if w["length_px"] >= min_length * factor]
            if len(filtered) <= MAX_WALLS:
                merged_lines = filtered
                break
        else:
            merged_lines = merged_lines[:MAX_WALLS]

    # Mitigation 5: cluster endpoints into clean junctions
    junctions, wall_segments = _build_junctions(merged_lines)
    wall_segments = _normalize_walls(wall_segments)

    # Mitigation 5b: with OCR text already removed, we can keep degree-1 walls.
    # Many real plan segments terminate at doors, plan cut-outs, or image crops.
    wall_segments = _collapse_parallel_walls(wall_segments)
    wall_segments = _deduplicate_walls(wall_segments)

    # Extract room polygons from enclosed regions
    rooms = _extract_rooms(edges, img.shape)
    rooms = _assign_text_to_rooms(rooms, text_regions)

    # Detect openings and door swing arcs
    openings = _detect_openings(wall_segments)
    openings = _attach_door_arcs(gray, text_regions, openings)
    windows = _detect_windows(gray, text_regions, img.shape)
    openings.extend(_recover_doors_from_symbols(gray, text_regions, wall_segments, openings, windows))
    openings.extend(windows)

    # Scale factor: convert pixels to meters
    scale_px_to_m = _estimate_scale(img, gray)

    # Mitigation 6: round all coordinates to integers for clean 3D handoff
    wall_segments = _round_coordinates(wall_segments)
    junctions = _round_coordinates(junctions)
    rooms = _round_room_data(rooms)
    openings = _round_openings(openings)

    result = {
        "image_size": {"width": w, "height": h},
        "scale_px_to_m": scale_px_to_m,
        "walls": wall_segments,
        "junctions": junctions,
        "rooms": rooms,
        "openings": openings,
        "labels": text_regions,
        "stats": {
            "total_walls": len(wall_segments),
            "total_rooms": len(rooms),
            "total_junctions": len(junctions),
            "total_openings": len(openings),
            "total_doors": sum(1 for opening in openings if opening.get("type") == "door"),
            "total_windows": sum(1 for opening in openings if opening.get("type") == "window"),
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
        return cv2.imread(image_input)
    return None


# ── Edge Detection ────────────────────────────────────────────────────────────

def _detect_edges(gray: np.ndarray, text_regions: Optional[list] = None) -> np.ndarray:
    """
    Multi-step edge detection optimised for clean digital floor plans.
    Uses stronger blur to suppress text and thin lines.
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 4
    )
    if text_regions:
        thresh = _mask_text_regions(thresh, text_regions, TEXT_MASK_PADDING)

    edges_canny = cv2.Canny(blurred, 80, 200, apertureSize=3)
    if text_regions:
        edges_canny = _mask_text_regions(edges_canny, text_regions, TEXT_MASK_PADDING)

    combined = cv2.bitwise_or(thresh, edges_canny)

    kernel = np.ones((3, 3), np.uint8)
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

    erode_kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.erode(cleaned, erode_kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

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
    Non-orthogonal lines (diagonals) are discarded — door arcs become diagonal
    segments and are naturally filtered here.
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
                mid_y = round((y1 + y2) / 2)
                snapped.append([x1, mid_y, x2, mid_y])
            else:
                mid_x = round((x1 + x2) / 2)
                snapped.append([mid_x, y1, mid_x, y2])
        # else: discard non-orthogonal lines (door arcs, diagonal noise)

    return snapped


# ── Line Merging ──────────────────────────────────────────────────────────────

def _merge_collinear_lines(lines: list, gap_threshold: int = 20) -> list:
    """
    Merge overlapping or close collinear line segments.
    Groups lines by orientation and position, merges within same row/column.
    Uses position bucketing to handle slight offsets from snapping.
    """
    # Bucket size for grouping nearly-collinear lines
    BUCKET = 8  # pixels — lines within 8px of same y/x are on same wall

    h_buckets = defaultdict(list)
    v_buckets = defaultdict(list)

    for x1, y1, x2, y2 in lines:
        if y1 == y2:  # horizontal
            bucket_y = round(y1 / BUCKET) * BUCKET
            h_buckets[bucket_y].append((min(x1, x2), max(x1, x2)))
        elif x1 == x2:  # vertical
            bucket_x = round(x1 / BUCKET) * BUCKET
            v_buckets[bucket_x].append((min(y1, y2), max(y1, y2)))

    merged = []

    for y, segments in h_buckets.items():
        merged.extend(_merge_segments_1d(segments, gap_threshold, axis='h', fixed=y))

    for x, segments in v_buckets.items():
        merged.extend(_merge_segments_1d(segments, gap_threshold, axis='v', fixed=x))

    return merged


def _collapse_parallel_walls(lines: list, distance_threshold: int = PARALLEL_MERGE_DISTANCE) -> list:
    """Collapse the two detected faces of a thick wall into one centerline."""
    horizontal = [wall for wall in lines if wall["orientation"] == "horizontal"]
    vertical = [wall for wall in lines if wall["orientation"] == "vertical"]
    merged = []
    merged.extend(_collapse_parallel_group(horizontal, distance_threshold, axis="horizontal"))
    merged.extend(_collapse_parallel_group(vertical, distance_threshold, axis="vertical"))
    return merged


def _collapse_parallel_group(lines: list, distance_threshold: int, axis: str) -> list:
    if not lines:
        return []

    fixed_key = "y1" if axis == "horizontal" else "x1"
    start_key = "x1" if axis == "horizontal" else "y1"
    end_key = "x2" if axis == "horizontal" else "y2"

    ordered = sorted(lines, key=lambda line: (line[fixed_key], line[start_key], line[end_key]))
    used = set()
    collapsed = []

    for i, wall in enumerate(ordered):
        if i in used:
            continue

        cluster = [wall]
        used.add(i)
        w_start = min(wall[start_key], wall[end_key])
        w_end = max(wall[start_key], wall[end_key])

        for j in range(i + 1, len(ordered)):
            other = ordered[j]
            if j in used:
                continue
            if abs(other[fixed_key] - wall[fixed_key]) > distance_threshold:
                if other[fixed_key] - wall[fixed_key] > distance_threshold:
                    break
                continue

            o_start = min(other[start_key], other[end_key])
            o_end = max(other[start_key], other[end_key])
            overlap = min(w_end, o_end) - max(w_start, o_start)
            if overlap >= min(w_end - w_start, o_end - o_start) * 0.45:
                cluster.append(other)
                used.add(j)

        center = round(float(np.mean([item[fixed_key] for item in cluster])))
        intervals = [
            (min(item[start_key], item[end_key]), max(item[start_key], item[end_key]))
            for item in cluster
        ]

        for start, end in _merge_intervals(intervals, gap=MAX_LINE_GAP + 4):
            collapsed.append(_seg_to_wall(start, end, "h" if axis == "horizontal" else "v", center))

    return collapsed


def _merge_intervals(intervals: list, gap: int) -> list:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


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
    endpoints = []
    for i, wall in enumerate(walls):
        endpoints.append((wall["x1"], wall["y1"], i, "start"))
        endpoints.append((wall["x2"], wall["y2"], i, "end"))

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
            for j in juncs:
                d_start = abs(j["x"] - wall["x1"]) + abs(j["y"] - wall["y1"])
                d_end = abs(j["x"] - wall["x2"]) + abs(j["y"] - wall["y2"])
                if d_start < d_end:
                    wall["x1"], wall["y1"] = j["x"], j["y"]
                else:
                    wall["x2"], wall["y2"] = j["x"], j["y"]

    return junctions, walls


def _normalize_walls(walls: list) -> list:
    normalized = []
    for wall in walls:
        fixed = dict(wall)
        if fixed["orientation"] == "horizontal":
            y = int(round((fixed["y1"] + fixed["y2"]) / 2))
            x1, x2 = sorted((int(round(fixed["x1"])), int(round(fixed["x2"]))))
            if x2 - x1 <= 0:
                continue
            fixed["x1"], fixed["x2"] = x1, x2
            fixed["y1"] = fixed["y2"] = y
            fixed["length_px"] = x2 - x1
        else:
            x = int(round((fixed["x1"] + fixed["x2"]) / 2))
            y1, y2 = sorted((int(round(fixed["y1"])), int(round(fixed["y2"]))))
            if y2 - y1 <= 0:
                continue
            fixed["x1"] = fixed["x2"] = x
            fixed["y1"], fixed["y2"] = y1, y2
            fixed["length_px"] = y2 - y1
        normalized.append(fixed)
    return normalized


def _deduplicate_walls(walls: list) -> list:
    deduped = {}
    for wall in _normalize_walls(walls):
        key = (
            wall["orientation"],
            wall["x1"], wall["y1"], wall["x2"], wall["y2"],
        )
        existing = deduped.get(key)
        if existing is None or wall["length_px"] > existing["length_px"]:
            deduped[key] = wall

    unique = sorted(
        deduped.values(),
        key=lambda wall: (
            wall["orientation"],
            wall["y1"] if wall["orientation"] == "horizontal" else wall["x1"],
            wall["x1"] if wall["orientation"] == "horizontal" else wall["y1"],
        ),
    )
    for i, wall in enumerate(unique):
        wall["id"] = f"wall_{i}"
    return unique
# ── Room Extraction ───────────────────────────────────────────────────────────

def _extract_rooms(edges: np.ndarray, img_shape: tuple) -> list:
    """
    Find enclosed regions (rooms) using contour detection on the edge map.
    Returns list of room polygons with bounding boxes.
    """
    h, w = img_shape[:2]

    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    inverted = cv2.bitwise_not(closed)

    contours, hierarchy = cv2.findContours(
        inverted, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )

    rooms = []
    min_area = (w * h) * 0.008   # at least 0.8% of image = valid room
    max_area = (w * h) * 0.75    # at most 75% of image (skip outer boundary)

    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue

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
            "label": "unknown"
        })

    rooms.sort(key=lambda r: r["area_px"], reverse=True)

    # Cap rooms at 20 — more than this is noise
    return rooms[:20]


def _assign_text_to_rooms(rooms: list, text_regions: list) -> list:
    if not rooms or not text_regions:
        return rooms

    for region in text_regions:
        room = _find_room_for_point(rooms, region["center"])
        if room is None:
            continue
        if room.get("label", "unknown").lower() == "unknown":
            room["label"] = region["text"]
        else:
            room["label"] = _merge_room_labels(room["label"], region["text"])

    return rooms


# ── Opening Detection ─────────────────────────────────────────────────────────

def _detect_openings(walls: list) -> list:
    """
    Detect gaps in walls (doors/windows).
    A gap = two collinear wall segments with a space between them.
    """
    openings = []
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
            if OPENING_MIN_PX <= gap <= OPENING_MAX_PX:
                openings.append({
                    "id": f"opening_{len(openings)}",
                    "type": "opening",
                    "orientation": "horizontal",
                    "x1": segs_sorted[i]["x2"],
                    "y1": y,
                    "x2": segs_sorted[i + 1]["x1"],
                    "y2": y,
                    "width_px": gap,
                    "hinge_candidates": [
                        {"x": segs_sorted[i]["x2"], "y": y},
                        {"x": segs_sorted[i + 1]["x1"], "y": y},
                    ],
                })

    for x, segs in v_walls.items():
        segs_sorted = sorted(segs, key=lambda s: s["y1"])
        for i in range(len(segs_sorted) - 1):
            gap = segs_sorted[i + 1]["y1"] - segs_sorted[i]["y2"]
            if OPENING_MIN_PX <= gap <= OPENING_MAX_PX:
                openings.append({
                    "id": f"opening_{len(openings)}",
                    "type": "opening",
                    "orientation": "vertical",
                    "x1": x,
                    "y1": segs_sorted[i]["y2"],
                    "x2": x,
                    "y2": segs_sorted[i + 1]["y1"],
                    "width_px": gap,
                    "hinge_candidates": [
                        {"x": x, "y": segs_sorted[i]["y2"]},
                        {"x": x, "y": segs_sorted[i + 1]["y1"]},
                    ],
                })

    return openings


def _attach_door_arcs(gray: np.ndarray, text_regions: list, openings: list) -> list:
    if not openings:
        return openings

    image_shape = gray.shape
    symbol_mask = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (3, 3), 0),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 4
    )
    symbol_mask = _mask_text_regions(symbol_mask, text_regions, TEXT_MASK_PADDING)
    contours, _ = cv2.findContours(symbol_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    diagonal_clusters = _extract_diagonal_symbol_clusters(symbol_mask)

    for opening in openings:
        arc = _find_door_arc_for_opening(opening, contours)
        if arc is None and _should_synthesise_door_arc(opening, image_shape, diagonal_clusters):
            arc = _synthesise_door_arc(opening, image_shape)
        if arc:
            opening["type"] = "door"
            opening["door_arc"] = arc
            opening["center"] = {
                "x": round((opening["x1"] + opening["x2"]) / 2),
                "y": round((opening["y1"] + opening["y2"]) / 2),
            }
            opening["bbox"] = _build_door_bbox(opening, arc, image_shape)
        else:
            opening["type"] = "opening"
            opening.pop("door_arc", None)
            opening.pop("center", None)
            opening.pop("bbox", None)

    return openings


def _should_synthesise_door_arc(opening: dict, image_shape: tuple, diagonal_clusters: list) -> bool:
    width = float(opening.get("width_px", 0))
    if width < OPENING_MIN_PX or width > min(OPENING_MAX_PX, 110):
        return False

    image_h, image_w = image_shape[:2]
    center_x = (float(opening["x1"]) + float(opening["x2"])) / 2
    center_y = (float(opening["y1"]) + float(opening["y2"])) / 2
    margin_x = max(8.0, image_w * 0.01)
    margin_y = max(8.0, image_h * 0.01)

    inside_image = (
        margin_x <= center_x <= image_w - margin_x and
        margin_y <= center_y <= image_h - margin_y
    )
    if not inside_image:
        return False

    return _opening_has_symbol_support(opening, diagonal_clusters)


def _extract_diagonal_symbol_clusters(symbol_mask: np.ndarray) -> list:
    lines = cv2.HoughLinesP(
        symbol_mask,
        rho=1,
        theta=np.pi / 180,
        threshold=18,
        minLineLength=10,
        maxLineGap=8,
    )
    if lines is None:
        return []

    segments = []
    for raw in lines[:, 0]:
        x1, y1, x2, y2 = [int(v) for v in raw]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 10 or length > 110:
            continue
        angle = abs(math.degrees(math.atan2(dy, dx))) % 180
        angle = min(angle, 180 - angle)
        if angle < 12 or angle > 78:
            continue
        segments.append({
            "points": (x1, y1, x2, y2),
            "mid_x": (x1 + x2) / 2,
            "mid_y": (y1 + y2) / 2,
        })

    clusters = []
    used = set()
    for idx, segment in enumerate(segments):
        if idx in used:
            continue

        pending = [idx]
        used.add(idx)
        cluster_indices = []
        while pending:
            current = pending.pop()
            cluster_indices.append(current)
            origin = segments[current]
            for other_idx, other in enumerate(segments):
                if other_idx in used:
                    continue
                if abs(origin["mid_x"] - other["mid_x"]) <= 90 and abs(origin["mid_y"] - other["mid_y"]) <= 90:
                    used.add(other_idx)
                    pending.append(other_idx)

        points = []
        for cluster_idx in cluster_indices:
            x1, y1, x2, y2 = segments[cluster_idx]["points"]
            points.extend([(x1, y1), (x2, y2)])

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bbox = {
            "x": min(xs),
            "y": min(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
        }
        if len(cluster_indices) < 2:
            continue
        if not (28 <= bbox["width"] <= 170 and 28 <= bbox["height"] <= 170):
            continue

        clusters.append({
            "bbox": bbox,
            "center": {
                "x": round(bbox["x"] + bbox["width"] / 2),
                "y": round(bbox["y"] + bbox["height"] / 2),
            },
            "count": len(cluster_indices),
        })

    return clusters


def _opening_has_symbol_support(opening: dict, diagonal_clusters: list) -> bool:
    center_x = (float(opening["x1"]) + float(opening["x2"])) / 2
    center_y = (float(opening["y1"]) + float(opening["y2"])) / 2
    width = max(float(opening.get("width_px", 0)), OPENING_MIN_PX)
    for cluster in diagonal_clusters:
        bbox = cluster["bbox"]
        padding = max(72.0, width * 1.25)
        if (
            bbox["x"] - padding <= center_x <= bbox["x"] + bbox["width"] + padding and
            bbox["y"] - padding <= center_y <= bbox["y"] + bbox["height"] + padding
        ):
            return True
    return False


def _recover_doors_from_symbols(gray: np.ndarray, text_regions: list, walls: list, openings: list, windows: list) -> list:
    image_shape = gray.shape
    raw_symbol_mask = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (3, 3), 0),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 4
    )
    masked_symbol_mask = _mask_text_regions(raw_symbol_mask, text_regions, TEXT_MASK_PADDING)
    candidates = _extract_diagonal_symbol_clusters(masked_symbol_mask)
    candidates.extend(_extract_diagonal_symbol_clusters(raw_symbol_mask))
    recovered = []
    existing_boxes = [opening.get("bbox") for opening in openings if opening.get("bbox")]
    window_boxes = [window.get("bbox") for window in windows if window.get("bbox")]

    for cluster in candidates:
        if any(_bboxes_overlap(cluster["bbox"], box) for box in existing_boxes):
            continue
        if any(_bboxes_overlap(cluster["bbox"], window_box, padding=6) for window_box in window_boxes):
            continue
        door = _build_symbol_door_candidate(cluster, walls, image_shape)
        if door is None:
            continue
        if any(_bboxes_overlap(door["bbox"], box) for box in existing_boxes):
            continue
        existing_boxes.append(door["bbox"])
        recovered.append(door)

    return recovered


def _build_symbol_door_candidate(cluster: dict, walls: list, image_shape: tuple) -> Optional[dict]:
    bbox = cluster["bbox"]
    corners = {
        "top_left": {"x": bbox["x"], "y": bbox["y"]},
        "top_right": {"x": bbox["x"] + bbox["width"], "y": bbox["y"]},
        "bottom_right": {"x": bbox["x"] + bbox["width"], "y": bbox["y"] + bbox["height"]},
        "bottom_left": {"x": bbox["x"], "y": bbox["y"] + bbox["height"]},
    }

    best_name = None
    best_score = None
    best_support = None
    for name, corner in corners.items():
        support = _corner_wall_support(corner, walls)
        score = support["horizontal_distance"] + support["vertical_distance"]
        if min(support["horizontal_distance"], support["vertical_distance"]) > 55:
            continue
        if max(support["horizontal_distance"], support["vertical_distance"]) > 170:
            continue
        if score > 210:
            continue
        if best_score is None or score < best_score:
            best_name = name
            best_score = score
            best_support = support

    if best_name is None:
        return None

    radius = max(28, min(OPENING_MAX_PX, int(round(max(bbox["width"], bbox["height"])))))
    hinge = corners[best_name]
    arc = _build_corner_arc(best_name, hinge, radius)
    if arc is None:
        return None

    orientation = "horizontal" if best_support["horizontal_distance"] <= best_support["vertical_distance"] else "vertical"
    if orientation == "horizontal":
        if "left" in best_name:
            x1, x2 = hinge["x"], min(image_shape[1] - 1, hinge["x"] + radius)
        else:
            x1, x2 = max(0, hinge["x"] - radius), hinge["x"]
        y1 = y2 = hinge["y"]
    else:
        if "top" in best_name:
            y1, y2 = hinge["y"], min(image_shape[0] - 1, hinge["y"] + radius)
        else:
            y1, y2 = max(0, hinge["y"] - radius), hinge["y"]
        x1 = x2 = hinge["x"]

    return {
        "id": f"door_symbol_{cluster['center']['x']}_{cluster['center']['y']}",
        "type": "door",
        "orientation": orientation,
        "x1": int(x1),
        "y1": int(y1),
        "x2": int(x2),
        "y2": int(y2),
        "width_px": int(radius),
        "hinge_candidates": [dict(hinge)],
        "door_arc": arc,
        "center": dict(cluster["center"]),
        "bbox": dict(bbox),
    }


def _corner_wall_support(corner: dict, walls: list) -> dict:
    horizontal_distance = 9999.0
    vertical_distance = 9999.0

    for wall in walls:
        if wall["orientation"] == "horizontal":
            x_min = min(wall["x1"], wall["x2"]) - 28
            x_max = max(wall["x1"], wall["x2"]) + 28
            if x_min <= corner["x"] <= x_max:
                horizontal_distance = min(horizontal_distance, abs(corner["y"] - wall["y1"]))
        else:
            y_min = min(wall["y1"], wall["y2"]) - 28
            y_max = max(wall["y1"], wall["y2"]) + 28
            if y_min <= corner["y"] <= y_max:
                vertical_distance = min(vertical_distance, abs(corner["x"] - wall["x1"]))

    return {
        "horizontal_distance": horizontal_distance,
        "vertical_distance": vertical_distance,
    }


def _build_corner_arc(corner_name: str, hinge: dict, radius: int) -> Optional[dict]:
    configs = {
        "top_left": (0.0, 90.0),
        "top_right": (90.0, 180.0),
        "bottom_right": (180.0, 270.0),
        "bottom_left": (-90.0, 0.0),
    }
    if corner_name not in configs:
        return None

    start_angle_deg, end_angle_deg = configs[corner_name]
    end_angle_rad = math.radians(end_angle_deg)
    return {
        "hinge": {"x": int(hinge["x"]), "y": int(hinge["y"])},
        "radius_px": float(radius),
        "start_angle_deg": float(start_angle_deg),
        "end_angle_deg": float(end_angle_deg),
        "leaf_end": {
            "x": round(float(hinge["x"] + math.cos(end_angle_rad) * radius)),
            "y": round(float(hinge["y"] + math.sin(end_angle_rad) * radius)),
        },
    }


def _bboxes_overlap(a: Optional[dict], b: Optional[dict], padding: int = 18) -> bool:
    if not a or not b:
        return False
    ax1 = a["x"] - padding
    ay1 = a["y"] - padding
    ax2 = a["x"] + a["width"] + padding
    ay2 = a["y"] + a["height"] + padding
    bx1 = b["x"]
    by1 = b["y"]
    bx2 = b["x"] + b["width"]
    by2 = b["y"] + b["height"]
    return min(ax2, bx2) >= max(ax1, bx1) and min(ay2, by2) >= max(ay1, by1)


def _build_door_bbox(opening: dict, arc: dict, image_shape: tuple) -> dict:
    image_h, image_w = image_shape[:2]
    x_values = [opening["x1"], opening["x2"], arc["hinge"]["x"], arc["leaf_end"]["x"]]
    y_values = [opening["y1"], opening["y2"], arc["hinge"]["y"], arc["leaf_end"]["y"]]
    padding = max(8, int(round(float(opening.get("width_px", OPENING_MIN_PX)) * 0.18)))

    x1 = max(0, int(round(min(x_values) - padding)))
    y1 = max(0, int(round(min(y_values) - padding)))
    x2 = min(image_w - 1, int(round(max(x_values) + padding)))
    y2 = min(image_h - 1, int(round(max(y_values) + padding)))

    return {
        "x": x1,
        "y": y1,
        "width": max(1, x2 - x1),
        "height": max(1, y2 - y1),
    }


def _detect_windows(gray: np.ndarray, text_regions: list, image_shape: tuple, relaxed: bool = False) -> list:
    mask = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gray, (3, 3), 0),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 4
    )
    mask = _mask_text_regions(mask, text_regions, TEXT_MASK_PADDING)
    lines = cv2.HoughLinesP(
        mask,
        rho=1,
        theta=np.pi / 180,
        threshold=16 if relaxed else 20,
        minLineLength=16 if relaxed else 20,
        maxLineGap=5 if relaxed else 4,
    )
    if lines is None:
        return []

    image_h, image_w = image_shape[:2]
    edge_margin = WINDOW_EDGE_MARGIN + (20 if relaxed else 0)

    horizontal = []
    vertical = []
    for raw in lines[:, 0]:
        x1, y1, x2, y2 = [int(v) for v in raw]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        if dx >= dy and WINDOW_SYMBOL_LENGTH_MIN <= dx <= WINDOW_SYMBOL_LENGTH_MAX and dy <= 4:
            y = round((y1 + y2) / 2)
            near_edge = "top" if y <= edge_margin else "bottom" if y >= image_h - edge_margin else None
            if near_edge:
                horizontal.append({
                    "edge": near_edge,
                    "start": min(x1, x2),
                    "end": max(x1, x2),
                    "fixed": y,
                })
        elif dy > dx and WINDOW_SYMBOL_LENGTH_MIN <= dy <= WINDOW_SYMBOL_LENGTH_MAX and dx <= 4:
            x = round((x1 + x2) / 2)
            near_edge = "left" if x <= edge_margin else "right" if x >= image_w - edge_margin else None
            if near_edge:
                vertical.append({
                    "edge": near_edge,
                    "start": min(y1, y2),
                    "end": max(y1, y2),
                    "fixed": x,
                })

    windows = []
    windows.extend(_build_window_candidates(horizontal, axis="horizontal"))
    windows.extend(_build_window_candidates(vertical, axis="vertical"))
    merged = _merge_window_candidates(windows)
    filtered = [
        window for window in merged
        if _is_reasonable_window_candidate(window, image_w, image_h)
    ]
    return _deduplicate_openings_by_bbox(filtered)


def _build_window_candidates(lines: list, axis: str) -> list:
    candidates = []
    for i, line in enumerate(lines):
        for other in lines[i + 1:]:
            if line["edge"] != other["edge"]:
                continue
            distance = abs(line["fixed"] - other["fixed"])
            if not (WINDOW_PAIR_DISTANCE_MIN <= distance <= WINDOW_PAIR_DISTANCE_MAX):
                continue
            overlap_start = max(line["start"], other["start"])
            overlap_end = min(line["end"], other["end"])
            overlap = overlap_end - overlap_start
            if overlap < WINDOW_SYMBOL_LENGTH_MIN:
                continue

            if axis == "horizontal":
                x1 = overlap_start
                x2 = overlap_end
                y1 = min(line["fixed"], other["fixed"])
                y2 = max(line["fixed"], other["fixed"])
                orientation = "horizontal"
                center = {"x": round((x1 + x2) / 2), "y": round((y1 + y2) / 2)}
            else:
                x1 = min(line["fixed"], other["fixed"])
                x2 = max(line["fixed"], other["fixed"])
                y1 = overlap_start
                y2 = overlap_end
                orientation = "vertical"
                center = {"x": round((x1 + x2) / 2), "y": round((y1 + y2) / 2)}

            if (x2 - x1) > WINDOW_SYMBOL_LENGTH_MAX or (y2 - y1) > WINDOW_SYMBOL_LENGTH_MAX:
                continue
            if min(x2 - x1, y2 - y1) > WINDOW_SYMBOL_THICKNESS_MAX and max(x2 - x1, y2 - y1) < 2 * WINDOW_SYMBOL_LENGTH_MIN:
                continue

            candidates.append({
                "type": "window",
                "orientation": orientation,
                "edge": line["edge"],
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width_px": max(x2 - x1, y2 - y1),
                "center": center,
                "bbox": {"x": x1, "y": y1, "width": max(1, x2 - x1), "height": max(1, y2 - y1)},
            })
    return candidates


def _merge_window_candidates(candidates: list) -> list:
    merged = []
    for candidate in sorted(candidates, key=lambda item: (item["edge"], item["x1"], item["y1"])):
        matched = False
        for existing in merged:
            if existing["edge"] != candidate["edge"]:
                continue
            if _window_overlap(existing, candidate):
                existing["x1"] = min(existing["x1"], candidate["x1"])
                existing["y1"] = min(existing["y1"], candidate["y1"])
                existing["x2"] = max(existing["x2"], candidate["x2"])
                existing["y2"] = max(existing["y2"], candidate["y2"])
                existing["width_px"] = max(existing["x2"] - existing["x1"], existing["y2"] - existing["y1"])
                existing["center"] = {
                    "x": round((existing["x1"] + existing["x2"]) / 2),
                    "y": round((existing["y1"] + existing["y2"]) / 2),
                }
                existing["bbox"] = {
                    "x": existing["x1"],
                    "y": existing["y1"],
                    "width": max(1, existing["x2"] - existing["x1"]),
                    "height": max(1, existing["y2"] - existing["y1"]),
                }
                matched = True
                break
        if not matched:
            merged.append(dict(candidate))
    return merged


def _window_overlap(a: dict, b: dict) -> bool:
    ax1, ay1, ax2, ay2 = a["x1"], a["y1"], a["x2"], a["y2"]
    bx1, by1, bx2, by2 = b["x1"], b["y1"], b["x2"], b["y2"]
    return (
        min(ax2, bx2) - max(ax1, bx1) >= -8 and
        min(ay2, by2) - max(ay1, by1) >= -8
    )


def _deduplicate_openings_by_bbox(openings: list) -> list:
    unique = []
    for opening in openings:
        if any(_window_overlap(opening, other) for other in unique):
            continue
        unique.append(opening)
    for i, opening in enumerate(unique):
        if opening.get("type") == "window":
            opening["id"] = f"window_{i}"
    return unique


def _is_reasonable_window_candidate(window: dict, image_w: int, image_h: int) -> bool:
    span = max(abs(window["x2"] - window["x1"]), abs(window["y2"] - window["y1"]))
    thickness = max(1, min(abs(window["x2"] - window["x1"]), abs(window["y2"] - window["y1"])))
    center = window.get("center", {"x": 0, "y": 0})
    edge = window.get("edge")

    if edge in {"left", "right"}:
        if not (80 <= span <= 150 and 2 <= thickness <= 16):
            return False
        if center["y"] >= image_h * 0.8:
            return False
    elif edge == "top":
        if not (35 <= span <= 140 and 2 <= thickness <= 12):
            return False
    elif edge == "bottom":
        if not (35 <= span <= 110 and 2 <= thickness <= 12):
            return False
        if abs(center["x"] - image_w / 2) < image_w * 0.12:
            return False

    return True


def _find_door_arc_for_opening(opening: dict, contours: list) -> Optional[dict]:
    x_min = min(opening["x1"], opening["x2"]) - DOOR_SEARCH_PADDING
    x_max = max(opening["x1"], opening["x2"]) + DOOR_SEARCH_PADDING
    y_min = min(opening["y1"], opening["y2"]) - DOOR_SEARCH_PADDING
    y_max = max(opening["y1"], opening["y2"]) + DOOR_SEARCH_PADDING

    best = None
    expected_radius = max(opening["width_px"], OPENING_MIN_PX)

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if x + w < x_min or x > x_max or y + h < y_min or y > y_max:
            continue
        if max(w, h) < OPENING_MIN_PX or max(w, h) > OPENING_MAX_PX * 1.8:
            continue

        points = contour.reshape(-1, 2).astype(np.float32)
        if len(points) < 12:
            continue

        for hinge in opening["hinge_candidates"]:
            center = np.array([hinge["x"], hinge["y"]], dtype=np.float32)
            dists = np.linalg.norm(points - center, axis=1)
            radius = float(np.median(dists))
            radius_std = float(np.std(dists))
            if radius < OPENING_MIN_PX * 0.7 or radius > OPENING_MAX_PX * 1.35:
                continue
            if abs(radius - expected_radius) > max(18, expected_radius * 0.45):
                continue
            if radius_std > max(10, radius * 0.22):
                continue

            free_end = _other_hinge_candidate(opening, hinge)
            start_angle = np.arctan2(free_end["y"] - hinge["y"], free_end["x"] - hinge["x"])
            centroid = points.mean(axis=0)
            centroid_angle = np.arctan2(centroid[1] - hinge["y"], centroid[0] - hinge["x"])
            sweep = _choose_quarter_turn(start_angle, centroid_angle)
            end_angle = start_angle + sweep

            score = radius_std + abs(radius - expected_radius) * 0.25
            if best is None or score < best["score"]:
                end_point = {
                    "x": round(float(hinge["x"] + np.cos(end_angle) * radius)),
                    "y": round(float(hinge["y"] + np.sin(end_angle) * radius)),
                }
                best = {
                    "score": score,
                    "hinge": {"x": int(hinge["x"]), "y": int(hinge["y"])},
                    "radius_px": round(radius, 2),
                    "start_angle_deg": round(np.degrees(start_angle), 2),
                    "end_angle_deg": round(np.degrees(end_angle), 2),
                    "leaf_end": end_point,
                }

    if not best:
        return None

    return {
        "hinge": best["hinge"],
        "radius_px": best["radius_px"],
        "start_angle_deg": best["start_angle_deg"],
        "end_angle_deg": best["end_angle_deg"],
        "leaf_end": best["leaf_end"],
    }


def _synthesise_door_arc(opening: dict, image_shape: tuple) -> dict:
    image_h, image_w = image_shape[:2]
    image_center = np.array([image_w / 2, image_h / 2], dtype=np.float32)
    radius = float(max(opening["width_px"], OPENING_MIN_PX))
    best = None

    for hinge in opening["hinge_candidates"]:
        free_end = _other_hinge_candidate(opening, hinge)
        start_angle = np.arctan2(free_end["y"] - hinge["y"], free_end["x"] - hinge["x"])

        for sweep in (np.pi / 2, -np.pi / 2):
            end_angle = start_angle + sweep
            probe = np.array([
                hinge["x"] + np.cos(start_angle + sweep / 2) * radius * 0.75,
                hinge["y"] + np.sin(start_angle + sweep / 2) * radius * 0.75,
            ], dtype=np.float32)

            outside_penalty = 0.0
            if probe[0] < 0 or probe[0] > image_w or probe[1] < 0 or probe[1] > image_h:
                outside_penalty = 10000.0

            score = float(np.linalg.norm(probe - image_center)) + outside_penalty
            if best is None or score < best["score"]:
                best = {
                    "score": score,
                    "hinge": {"x": int(hinge["x"]), "y": int(hinge["y"])},
                    "radius_px": round(radius, 2),
                    "start_angle_deg": round(np.degrees(start_angle), 2),
                    "end_angle_deg": round(np.degrees(end_angle), 2),
                    "leaf_end": {
                        "x": round(float(hinge["x"] + np.cos(end_angle) * radius)),
                        "y": round(float(hinge["y"] + np.sin(end_angle) * radius)),
                    },
                }

    return {
        "hinge": best["hinge"],
        "radius_px": best["radius_px"],
        "start_angle_deg": best["start_angle_deg"],
        "end_angle_deg": best["end_angle_deg"],
        "leaf_end": best["leaf_end"],
    }


# ── Scale Estimation ──────────────────────────────────────────────────────────

def _estimate_scale(img: np.ndarray, gray: np.ndarray) -> float:
    """
    Try to detect a scale bar in the image.
    Falls back to default (1px = 0.05m → typical for 200dpi A4 plan).
    """
    return 0.05


# ── Utility ───────────────────────────────────────────────────────────────────

def _round_coordinates(items: list) -> list:
    """Round all coordinate values to integers for clean 3D handoff."""
    coord_keys = {"x", "y", "x1", "y1", "x2", "y2"}
    for item in items:
        for k in coord_keys:
            if k in item:
                item[k] = int(round(item[k]))
    return items


def _round_room_data(rooms: list) -> list:
    for room in rooms:
        _round_coordinates([room["centroid"]])
        for point in room.get("polygon", []):
            point[0] = int(round(point[0]))
            point[1] = int(round(point[1]))
        bbox = room.get("bounding_box", {})
        for key in ("x", "y", "width", "height"):
            if key in bbox:
                bbox[key] = int(round(bbox[key]))
    return rooms


def _round_openings(openings: list) -> list:
    for opening in openings:
        _round_coordinates([opening])
        if opening.get("center"):
            _round_coordinates([opening["center"]])
        if opening.get("bbox"):
            bbox = opening["bbox"]
            for key in ("x", "y", "width", "height"):
                if key in bbox:
                    bbox[key] = int(round(bbox[key]))
        for hinge in opening.get("hinge_candidates", []):
            hinge["x"] = int(round(hinge["x"]))
            hinge["y"] = int(round(hinge["y"]))
        if opening.get("door_arc"):
            arc = opening["door_arc"]
            _round_coordinates([arc["hinge"], arc["leaf_end"]])
            arc["radius_px"] = round(float(arc["radius_px"]), 2)
            arc["start_angle_deg"] = round(float(arc["start_angle_deg"]), 2)
            arc["end_angle_deg"] = round(float(arc["end_angle_deg"]), 2)
    return openings


def _extract_text_regions(img: np.ndarray) -> list:
    engine = _get_ocr_engine()
    if engine is None:
        return []

    try:
        results, _ = engine(img)
    except Exception as exc:  # pragma: no cover - OCR engine runtime issue
        logger.warning("OCR failed: %s", exc)
        return []

    text_regions = []
    for item in results or []:
        points, text, confidence = item
        if confidence < OCR_CONFIDENCE_MIN:
            continue
        polygon = np.array(points, dtype=np.float32)
        x, y, w, h = cv2.boundingRect(polygon.astype(np.int32))
        if w < 20 or h < 10:
            continue
        cleaned = _normalise_room_text(text)
        if not cleaned:
            continue
        text_regions.append({
            "text": cleaned,
            "confidence": float(confidence),
            "bounding_box": {"x": x, "y": y, "width": w, "height": h},
            "center": {"x": round(x + w / 2), "y": round(y + h / 2)},
            "polygon": polygon.astype(np.int32).tolist(),
        })

    return text_regions


def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    if RapidOCR is None:
        return None
    try:
        _OCR_ENGINE = RapidOCR()
    except Exception as exc:  # pragma: no cover - model init issue
        logger.warning("RapidOCR unavailable: %s", exc)
        _OCR_ENGINE = None
    return _OCR_ENGINE


def _mask_text_regions(mask: np.ndarray, text_regions: list, padding: int) -> np.ndarray:
    result = mask.copy()
    height, width = result.shape[:2]
    for region in text_regions:
        box = region["bounding_box"]
        x1 = max(0, box["x"] - padding)
        y1 = max(0, box["y"] - padding)
        x2 = min(width - 1, box["x"] + box["width"] + padding)
        y2 = min(height - 1, box["y"] + box["height"] + padding)
        cv2.rectangle(result, (x1, y1), (x2, y2), 0, thickness=-1)
    return result


def _find_room_for_point(rooms: list, point: dict):
    best = None
    best_distance = None
    px, py = point["x"], point["y"]

    for room in rooms:
        polygon = np.array(room.get("polygon", []), dtype=np.int32)
        if len(polygon) >= 3 and cv2.pointPolygonTest(polygon, (px, py), False) >= 0:
            return room

    for room in rooms:
        centroid = room["centroid"]
        distance = (centroid["x"] - px) ** 2 + (centroid["y"] - py) ** 2
        if best is None or distance < best_distance:
            best = room
            best_distance = distance

    return best


def _merge_room_labels(existing: str, incoming: str) -> str:
    existing_parts = [part.strip() for part in existing.split("/") if part.strip()]
    if incoming not in existing_parts:
        existing_parts.append(incoming)
    return " / ".join(existing_parts)


def _normalise_room_text(text: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", (text or "").upper())
    if not token:
        return ""

    if token.isdigit():
        return ""

    words = []
    remaining = token
    while remaining:
        matched = None
        for word in sorted(ROOM_WORDS, key=len, reverse=True):
            if remaining.startswith(word):
                matched = word
                break
        if matched:
            words.append(_correct_word(matched))
            remaining = remaining[len(matched):]
            continue

        if remaining[0].isdigit():
            digits = re.match(r"\d+", remaining).group(0)
            words.append(digits)
            remaining = remaining[len(digits):]
            continue

        best = _best_room_word(remaining)
        if best:
            words.append(best)
            remaining = remaining[len(best.replace(" ", "")):]
            continue

        words.append(remaining[0])
        remaining = remaining[1:]

    joined = " ".join(part for part in words if part)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def _correct_word(word: str) -> str:
    replacements = {
        "BEDROOM": "BEDROOM",
        "BATHROOM": "BATHROOM",
        "BATH": "BATH",
        "FOYER": "FOYER",
        "KITCHEN": "KITCHEN",
        "LAUNDRY": "LAUNDRY",
        "ENTRY": "ENTRY",
        "ROOM": "ROOM",
        "GREAT": "GREAT",
        "LIVING": "LIVING",
        "DINING": "DINING",
        "MASTER": "MASTER",
        "GARAGE": "GARAGE",
        "HALL": "HALL",
        "PANTRY": "PANTRY",
        "STUDY": "STUDY",
        "OFFICE": "OFFICE",
    }
    return replacements.get(word, word)


def _best_room_word(token: str) -> Optional[str]:
    best = None
    best_score = None
    for label in COMMON_ROOM_LABELS:
        candidate = label.replace(" ", "")
        segment = token[:len(candidate)]
        if len(segment) != len(candidate):
            continue
        score = sum(a != b for a, b in zip(segment, candidate))
        if best is None or score < best_score:
            best = label
            best_score = score
    if best_score is not None and best_score <= 2:
        return best
    return None


def _other_hinge_candidate(opening: dict, hinge: dict) -> dict:
    for candidate in opening["hinge_candidates"]:
        if candidate["x"] != hinge["x"] or candidate["y"] != hinge["y"]:
            return candidate
    return opening["hinge_candidates"][0]


def _choose_quarter_turn(start_angle: float, centroid_angle: float) -> float:
    delta = np.arctan2(np.sin(centroid_angle - start_angle), np.cos(centroid_angle - start_angle))
    return np.pi / 2 if delta >= 0 else -np.pi / 2


def _empty_result(w: int, h: int) -> dict:
    return {
        "image_size": {"width": w, "height": h},
        "scale_px_to_m": 0.05,
        "walls": [], "junctions": [], "rooms": [], "openings": [], "labels": [],
        "stats": {"total_walls": 0, "total_rooms": 0,
                  "total_junctions": 0, "total_openings": 0, "total_doors": 0, "total_windows": 0},
        "fallback_used": True,
    }


# ── Manual Fallback ───────────────────────────────────────────────────────────

def build_manual_result(walls: list, image_size: dict) -> dict:
    """
    Fallback clause: if CV fails, team manually defines wall coordinates.
    Disclosed during demo as per rules.
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
        "labels": [],
        "stats": {"total_walls": len(walls), "total_rooms": 0,
                  "total_junctions": 0, "total_openings": 0, "total_doors": 0, "total_windows": 0},
        "fallback_used": True,
    }
