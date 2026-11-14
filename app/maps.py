import re
from urllib.parse import unquote, urlparse

import httpx

USER_AGENT = "spiessgesellen/0.1 (private doener review club)"
SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl"}
MAP_HOSTS = {
    "www.google.com",
    "google.com",
    "maps.google.com",
    "www.google.de",
    "google.de",
}
ALLOWED_HOSTS = SHORT_HOSTS | MAP_HOSTS

COORD_PATTERNS = [
    re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"[?&](?:q|ll|query|destination|center)=(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)"),
    re.compile(r"^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$"),
]

BERLIN = (52.35, 52.68, 13.05, 13.80)


def parse_coordinates(text: str) -> tuple[float, float] | None:
    if not text:
        return None
    value = unquote(text)
    for pattern in COORD_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        lat, lng = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


def in_berlin(lat: float, lng: float) -> bool:
    south, north, west, east = BERLIN
    return south <= lat <= north and west <= lng <= east


def _allowed(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOWED_HOSTS


def expand_and_parse(url: str) -> tuple[float, float] | None:
    """Follow Google Maps redirects manually, never leaving the allowlist."""
    if not _allowed(url):
        return parse_coordinates(url)
    client = httpx.Client(
        timeout=6.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    )
    current = url
    try:
        for _ in range(6):
            found = parse_coordinates(current)
            if found:
                return found
            response = client.get(current)
            location = response.headers.get("location")
            if not location:
                return parse_coordinates(str(response.url))
            if not _allowed(location):
                return None
            current = location
    except httpx.HTTPError:
        return parse_coordinates(url)
    finally:
        client.close()
    return parse_coordinates(current)


def geocode(address: str) -> tuple[float, float] | None:
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "de"},
            headers={"User-Agent": USER_AGENT},
            timeout=8.0,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def maps_link(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lng:.6f}"


def static_map(lat: float, lng: float, zoom: int = 16) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lng:.6f}#map={zoom}/{lat:.6f}/{lng:.6f}"
