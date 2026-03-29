"""
Stage 2: Geometry Reconstruction
- Converts parsed wall segments into a structural graph
- Classifies walls as load-bearing vs partition
- Detects spans, room extents, and structural concerns
"""

import math
from collections import defaultdict
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

LOAD_BEARING_SPAN_RATIO = 0.60   # wall must span >60% of floor width/height
LONG_SPAN_THRESHOLD_M = 5.0      # spans > 5m flagged as needing steel/RCC
COLUMN_NEEDED_SPAN_M = 4.0       # spans > 4m suggest a column is needed


# ── Main Entry Point ──────────────────────────────────────────────────────────

def reconstruct_geometry(parse_result: dict) -> dict:
    """
    Takes parse_result from parser.py and returns full structural model:
    - Wall graph (nodes = junctions, edges = walls)
    - Load-bearing classification per wall
    - Room labels and extents
    - Structural concerns (unsupported spans, missing columns)
    - Element list ready for material analysis
    """
    walls = parse_result["walls"]
    rooms = parse_result["rooms"]
    junctions = parse_result["junctions"]
    img_w = parse_result["image_size"]["width"]
    img_h = parse_result["image_size"]["height"]
    scale = parse_result["scale_px_to_m"]
    fallback_used = parse_result.get("fallback_used", False)

    if not walls:
        logger.warning("No walls to reconstruct — returning empty geometry")
        return _empty_geometry(fallback_used)

    # Step 1: Build wall graph
    graph = _build_wall_graph(walls, junctions)

    # Step 2: Detect outer boundary
    boundary = _detect_boundary(walls, img_w, img_h)

    # Step 3: Classify load-bearing vs partition
    walls = _classify_walls(walls, boundary, img_w, img_h)

    # Step 4: Compute spans in meters
    walls = _compute_spans(walls, scale)

    # Step 5: Label rooms
    rooms = _label_rooms(rooms, walls, img_w, img_h)

    # Step 6: Detect structural concerns
    concerns = _detect_concerns(walls, scale)

    # Step 7: Build element list for material analysis
    elements = _build_element_list(walls, rooms, scale)

    result = {
        "graph": graph,
        "walls": walls,
        "rooms": rooms,
        "boundary": boundary,
        "elements": elements,
        "structural_concerns": concerns,
        "image_size": parse_result["image_size"],
        "scale_px_to_m": scale,
        "fallback_used": fallback_used,
        "stats": {
            "load_bearing_count": sum(1 for w in walls if w.get("load_bearing")),
            "partition_count": sum(1 for w in walls if not w.get("load_bearing")),
            "room_count": len(rooms),
            "concern_count": len(concerns),
        }
    }

    logger.info(f"Geometry done: {result['stats']}")
    return result


# ── Wall Graph ────────────────────────────────────────────────────────────────

def _build_wall_graph(walls: list, junctions: list) -> dict:
    """
    Graph representation:
    - nodes: junction points (corners, T-junctions, crossings)
    - edges: wall segments connecting nodes
    """
    nodes = {f"j_{i}": {"id": f"j_{i}", "x": j["x"], "y": j["y"],
                          "type": j["type"], "degree": j["degree"]}
             for i, j in enumerate(junctions)}

    edges = []
    for i, wall in enumerate(walls):
        edges.append({
            "id": f"wall_{i}",
            "from": f"({wall['x1']},{wall['y1']})",
            "to": f"({wall['x2']},{wall['y2']})",
            "orientation": wall["orientation"],
            "length_px": wall["length_px"]
        })

    return {"nodes": nodes, "edges": edges}


# ── Boundary Detection ────────────────────────────────────────────────────────

def _detect_boundary(walls: list, img_w: int, img_h: int) -> dict:
    """
    Identify the outer boundary of the building.
    Boundary walls are those closest to the image edges with significant length.
    """
    EDGE_MARGIN = max(img_w, img_h) * 0.05   # 5% from edge = "outer"

    boundary_walls = []
    for wall in walls:
        x_min = min(wall["x1"], wall["x2"])
        x_max = max(wall["x1"], wall["x2"])
        y_min = min(wall["y1"], wall["y2"])
        y_max = max(wall["y1"], wall["y2"])

        near_left   = x_min <= EDGE_MARGIN
        near_right  = x_max >= img_w - EDGE_MARGIN
        near_top    = y_min <= EDGE_MARGIN
        near_bottom = y_max >= img_h - EDGE_MARGIN

        if near_left or near_right or near_top or near_bottom:
            boundary_walls.append(wall)

    # Compute bounding box of all walls (building footprint)
    all_x = [w["x1"] for w in walls] + [w["x2"] for w in walls]
    all_y = [w["y1"] for w in walls] + [w["y2"] for w in walls]

    return {
        "min_x": min(all_x), "max_x": max(all_x),
        "min_y": min(all_y), "max_y": max(all_y),
        "width_px": max(all_x) - min(all_x),
        "height_px": max(all_y) - min(all_y),
        "boundary_wall_ids": [walls.index(w) for w in boundary_walls
                              if w in walls]
    }


# ── Load-Bearing Classification ───────────────────────────────────────────────

def _classify_walls(walls: list, boundary: dict, img_w: int, img_h: int) -> list:
    """
    Mitigation: Load-bearing classification.

    Rules (in priority order):
    1. Outer boundary walls → always load-bearing
    2. Walls spanning > LOAD_BEARING_SPAN_RATIO of floor width/height → load-bearing
    3. Walls forming continuous spine across floor → load-bearing
    4. Everything else → partition
    """
    floor_w = boundary["width_px"]
    floor_h = boundary["height_px"]
    EDGE_MARGIN = max(img_w, img_h) * 0.05

    # Group walls by their fixed coordinate (for spine detection)
    h_by_y = defaultdict(list)
    v_by_x = defaultdict(list)

    for i, wall in enumerate(walls):
        wall["id"] = f"wall_{i}"
        wall["load_bearing"] = False  # default

        if wall["orientation"] == "horizontal":
            h_by_y[wall["y1"]].append(i)
        else:
            v_by_x[wall["x1"]].append(i)

    for i, wall in enumerate(walls):
        x_min = min(wall["x1"], wall["x2"])
        x_max = max(wall["x1"], wall["x2"])
        y_min = min(wall["y1"], wall["y2"])
        y_max = max(wall["y1"], wall["y2"])

        # Rule 1: outer boundary
        near_edge = (x_min <= boundary["min_x"] + EDGE_MARGIN or
                     x_max >= boundary["max_x"] - EDGE_MARGIN or
                     y_min <= boundary["min_y"] + EDGE_MARGIN or
                     y_max >= boundary["max_y"] - EDGE_MARGIN)

        if near_edge:
            wall["load_bearing"] = True
            wall["lb_reason"] = "outer boundary wall"
            continue

        # Rule 2: long span
        length = wall["length_px"]
        if wall["orientation"] == "horizontal":
            if floor_w > 0 and length / floor_w >= LOAD_BEARING_SPAN_RATIO:
                wall["load_bearing"] = True
                wall["lb_reason"] = f"spans {length/floor_w*100:.0f}% of floor width"
                continue
        else:
            if floor_h > 0 and length / floor_h >= LOAD_BEARING_SPAN_RATIO:
                wall["load_bearing"] = True
                wall["lb_reason"] = f"spans {length/floor_h*100:.0f}% of floor height"
                continue

        # Rule 3: spine — wall is at center ± 15% of floor
        if wall["orientation"] == "vertical":
            center_x = boundary["min_x"] + floor_w / 2
            if abs(wall["x1"] - center_x) < floor_w * 0.15:
                wall["load_bearing"] = True
                wall["lb_reason"] = "structural spine (central vertical wall)"
                continue

        if wall["orientation"] == "horizontal":
            center_y = boundary["min_y"] + floor_h / 2
            if abs(wall["y1"] - center_y) < floor_h * 0.15:
                wall["load_bearing"] = True
                wall["lb_reason"] = "structural spine (central horizontal wall)"
                continue

        # Default: partition
        wall["load_bearing"] = False
        wall["lb_reason"] = "interior partition"

    return walls


# ── Span Computation ──────────────────────────────────────────────────────────

def _compute_spans(walls: list, scale: float) -> list:
    """Convert pixel lengths to meters, add span classification."""
    for wall in walls:
        length_m = wall["length_px"] * scale
        wall["length_m"] = round(length_m, 2)
        wall["span_class"] = (
            "short" if length_m < 3 else
            "medium" if length_m < LONG_SPAN_THRESHOLD_M else
            "long"
        )
    return walls


# ── Room Labelling ────────────────────────────────────────────────────────────

def _label_rooms(rooms: list, walls: list, img_w: int, img_h: int) -> list:
    """
    Heuristic room labelling by area and position.
    Without OCR, we estimate based on size and location.
    """
    if not rooms:
        return rooms

    total_area = sum(r["area_px"] for r in rooms)
    sorted_rooms = sorted(rooms, key=lambda r: r["area_px"], reverse=True)

    labels_assigned = []
    for i, room in enumerate(sorted_rooms):
        area_ratio = room["area_px"] / total_area if total_area > 0 else 0
        cx = room["centroid"]["x"]
        cy = room["centroid"]["y"]

        # Position quadrant
        left_half = cx < img_w / 2
        top_half = cy < img_h / 2

        if i == 0:
            label = "Living Room / Great Room"
        elif area_ratio > 0.15:
            label = "Bedroom" if not (left_half and top_half) else "Master Bedroom"
        elif area_ratio > 0.08:
            label = "Bedroom"
        elif area_ratio > 0.04:
            label = "Kitchen" if (left_half and not top_half) else "Bedroom"
        elif area_ratio > 0.02:
            label = "Bathroom"
        elif area_ratio > 0.01:
            label = "Laundry / Storage"
        else:
            label = "Foyer / Hallway"

        # Avoid duplicate labels with index
        base_label = label
        count = labels_assigned.count(base_label)
        if count > 0:
            label = f"{base_label} {count + 1}"
        labels_assigned.append(base_label)

        room["label"] = label
        room["area_m2"] = round(room["area_px"] * (0.05 ** 2), 2)

    return sorted_rooms


# ── Structural Concerns ───────────────────────────────────────────────────────

def _detect_concerns(walls: list, scale: float) -> list:
    """
    Detect structural issues:
    - Large unsupported spans (> LONG_SPAN_THRESHOLD_M)
    - Load-bearing walls with no column support
    - Missing intermediate supports
    """
    concerns = []

    for wall in walls:
        length_m = wall.get("length_m", 0)

        if wall.get("load_bearing") and length_m >= LONG_SPAN_THRESHOLD_M:
            concerns.append({
                "type": "long_span",
                "severity": "high",
                "wall_id": wall.get("id"),
                "span_m": length_m,
                "message": (
                    f"Load-bearing wall ({wall.get('lb_reason', '')}) spans "
                    f"{length_m:.1f}m — exceeds 5m threshold. "
                    f"Steel frame or RCC beam recommended."
                )
            })

        elif wall.get("load_bearing") and length_m >= COLUMN_NEEDED_SPAN_M:
            concerns.append({
                "type": "column_needed",
                "severity": "medium",
                "wall_id": wall.get("id"),
                "span_m": length_m,
                "message": (
                    f"Load-bearing wall spans {length_m:.1f}m. "
                    f"Consider intermediate RCC column for support."
                )
            })

    return concerns


# ── Element List Builder ──────────────────────────────────────────────────────

def _build_element_list(walls: list, rooms: list, scale: float) -> list:
    """
    Build a flat list of structural elements ready for material analysis.
    Each element has a type, dimensions, and context.
    """
    elements = []

    for wall in walls:
        el_type = "load_bearing_wall" if wall.get("load_bearing") else "partition_wall"
        elements.append({
            "id": wall.get("id", "unknown"),
            "type": el_type,
            "orientation": wall.get("orientation"),
            "length_m": wall.get("length_m", 0),
            "height_m": 3.0,   # standard floor height
            "span_class": wall.get("span_class", "short"),
            "lb_reason": wall.get("lb_reason", ""),
            "load_bearing": wall.get("load_bearing", False),
        })

    # Add floor slab element
    if rooms:
        total_area_m2 = sum(r.get("area_m2", 0) for r in rooms)
        elements.append({
            "id": "floor_slab",
            "type": "slab",
            "length_m": None,
            "area_m2": round(total_area_m2, 2),
            "height_m": 0.15,   # 150mm standard slab thickness
            "span_class": "medium",
            "load_bearing": True,
            "lb_reason": "floor slab"
        })

    # Add column elements for long-span load-bearing walls
    for wall in walls:
        if wall.get("load_bearing") and wall.get("length_m", 0) >= COLUMN_NEEDED_SPAN_M:
            elements.append({
                "id": f"col_{wall.get('id', 'unknown')}",
                "type": "column",
                "length_m": wall.get("length_m"),
                "height_m": 3.0,
                "span_class": wall.get("span_class"),
                "load_bearing": True,
                "lb_reason": f"supporting {wall.get('length_m', 0):.1f}m span"
            })

    return elements


# ── Utilities ─────────────────────────────────────────────────────────────────

def _empty_geometry(fallback_used: bool) -> dict:
    return {
        "graph": {"nodes": {}, "edges": []},
        "walls": [], "rooms": [], "boundary": {},
        "elements": [], "structural_concerns": [],
        "fallback_used": fallback_used,
        "stats": {"load_bearing_count": 0, "partition_count": 0,
                  "room_count": 0, "concern_count": 0}
    }


def euclidean(x1, y1, x2, y2) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
