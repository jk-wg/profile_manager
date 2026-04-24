#!/usr/bin/env python3
"""Post the vertices of a hardcoded GeoJSON polygon to the wg-shorts locations API."""

import json
import urllib.request

# ---------------------------------------------------------------------------
# Replace the coordinates below with your actual polygon data.
# The exterior ring must be a list of [lon, lat] pairs (GeoJSON order).
# The closing vertex (same as the first) will be skipped automatically.
# ---------------------------------------------------------------------------
POLYGON_COORDINATES = [
    [9.712047308809474, 53.20814244754138],
    [9.713047308809474, 53.20814244754138],
    [9.713047308809474, 53.20914244754138],
    [9.712047308809474, 53.20914244754138],
    [9.712047308809474, 53.20814244754138],  # closing vertex – duplicate of first
]

NICKNAME_BASE = "point"
URL = "https://wg-shorts.wheregroup.com/backend/locations/"
CSRF_TOKEN = "foo"

# ---------------------------------------------------------------------------

# Drop the closing vertex (same as the first in a valid polygon ring).
ring = POLYGON_COORDINATES[:-1] if len(POLYGON_COORDINATES) > 1 else POLYGON_COORDINATES

for idx, coord in enumerate(ring):
    payload = {"nickname": f"{NICKNAME_BASE}_{idx}", "coordinates": coord}
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cookie": f"csrfToken={CSRF_TOKEN}",
    }
    req = urllib.request.Request(URL, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as response:
        print(f"[{idx}] status={response.status}  body={response.read().decode()}")
