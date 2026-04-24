#!/usr/bin/env python3
"""Post the vertices of the first polygon in a GeoJSON file to the wg-shorts API.

Usage
-----
    python scripts/geojson_to_api.py <geojson_file> [options]

The script reads a GeoJSON file, extracts the first polygon geometry it finds
(inside a Feature or FeatureCollection), converts its exterior-ring vertices to
individual GeoJSON Point Features and HTTP-POSTs each one to the configured API
endpoint.

Examples
--------
    # Default endpoint
    python scripts/geojson_to_api.py my_area.geojson

    # Custom base URL
    python scripts/geojson_to_api.py my_area.geojson --base-url https://wg-shorts.wheregroup.com

    # With Bearer-token authentication
    python scripts/geojson_to_api.py my_area.geojson --token MY_SECRET_TOKEN
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# GeoJSON helpers
# ---------------------------------------------------------------------------


def _extract_polygon_coords(geometry: Dict[str, Any]) -> Optional[List[List[float]]]:
    """Return the exterior-ring coordinate list of the first Polygon found.

    Handles both ``Polygon`` and ``MultiPolygon`` geometry types.
    Returns ``None`` when the geometry is not polygonal.
    """
    geo_type = geometry.get("type")
    if geo_type == "Polygon":
        coords = geometry.get("coordinates")
        if not coords or not coords[0]:
            return None
        return coords[0]  # exterior ring
    if geo_type == "MultiPolygon":
        coords = geometry.get("coordinates")
        if not coords or not coords[0] or not coords[0][0]:
            return None
        return coords[0][0]  # first polygon, exterior ring
    return None


def _find_first_polygon_coords(
    geojson: Dict[str, Any],
) -> Tuple[List[List[float]], Optional[Dict[str, Any]]]:
    """Walk a GeoJSON object and return (exterior_ring_coords, properties).

    Raises ``ValueError`` when no polygon geometry is found.
    """
    geo_type = geojson.get("type")

    if geo_type == "FeatureCollection":
        for feature in geojson.get("features", []):
            coords = _extract_polygon_coords(feature.get("geometry") or {})
            if coords is not None:
                return coords, feature.get("properties")

    elif geo_type == "Feature":
        coords = _extract_polygon_coords(geojson.get("geometry") or {})
        if coords is not None:
            return coords, geojson.get("properties")

    elif geo_type in ("Polygon", "MultiPolygon"):
        coords = _extract_polygon_coords(geojson)
        if coords is not None:
            return coords, None

    raise ValueError("No Polygon or MultiPolygon geometry found in the GeoJSON file.")


def coords_to_point_features(
    exterior_ring: List[List[float]],
    base_properties: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Convert exterior-ring coordinates to a list of GeoJSON Point Features.

    The closing vertex (identical to the first vertex in a valid polygon ring)
    is omitted so that each physical corner is posted exactly once.
    """
    props = dict(base_properties or {})
    features = []

    # A valid polygon ring has the first == last coordinate; drop the duplicate.
    ring = exterior_ring[:-1] if len(exterior_ring) > 1 else exterior_ring

    for idx, coord in enumerate(ring):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": coord,
                },
                "properties": {**props, "vertex_index": idx},
            }
        )
    return features


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def post_feature(
    url: str,
    feature: Dict[str, Any],
    token: Optional[str] = None,
) -> Tuple[int, str]:
    """POST a GeoJSON Feature to *url* and return ``(status_code, body)``."""
    data = json.dumps(feature).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract the first polygon from a GeoJSON file and POST each vertex "
            "as a Point Feature to the wg-shorts API."
        ),
    )
    parser.add_argument(
        "geojson_file",
        type=Path,
        help="Path to the input GeoJSON file.",
    )
    parser.add_argument(
        "--base-url",
        default="https://wg-shorts.wheregroup.com",
        help="Base URL of the API server (default: https://wg-shorts.wheregroup.com).",
    )
    parser.add_argument(
        "--endpoint",
        default="/api/shorts/",
        help="API path to POST each point to (default: /api/shorts/).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token for Authorization header (optional).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the features that would be posted without actually sending them.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # -- Read file -----------------------------------------------------------
    geojson_path: Path = args.geojson_file
    if not geojson_path.is_file():
        print(f"Error: file not found: {geojson_path}", file=sys.stderr)
        return 1

    try:
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {geojson_path}: {exc}", file=sys.stderr)
        return 1

    # -- Extract polygon -----------------------------------------------------
    try:
        exterior_ring, properties = _find_first_polygon_coords(geojson)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    point_features = coords_to_point_features(exterior_ring, properties)
    print(f"Found {len(point_features)} vertex point(s) in the first polygon.")

    # -- Build target URL ----------------------------------------------------
    base = args.base_url.rstrip("/")
    endpoint = args.endpoint if args.endpoint.startswith("/") else f"/{args.endpoint}"
    url = f"{base}{endpoint}"

    if args.dry_run:
        print(f"Dry-run – would POST {len(point_features)} feature(s) to {url}:")
        for feature in point_features:
            print(json.dumps(feature, indent=2))
        return 0

    # -- POST each point -----------------------------------------------------
    print(f"Posting {len(point_features)} point(s) to {url} …")
    errors = 0
    for i, feature in enumerate(point_features, start=1):
        status, body = post_feature(url, feature, token=args.token)
        if 200 <= status < 300:
            print(f"  [{i}/{len(point_features)}] ✓  status={status}")
        else:
            print(
                f"  [{i}/{len(point_features)}] ✗  status={status}  body={body!r}",
                file=sys.stderr,
            )
            errors += 1

    if errors:
        print(f"\n{errors} error(s) occurred.", file=sys.stderr)
        return 1

    print("\nAll points posted successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
