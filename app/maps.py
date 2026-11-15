import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx

USER_AGENT = "spiessgesell-innen/0.1 (private doener review club)"
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
PLACE_RE = re.compile(r"/maps/place/([^/@?]+)")

BERLIN = (52.35, 52.68, 13.05, 13.80)


@dataclass(frozen=True)
class PlaceInfo:
    name: str
    address: str
    district: str
    lat: float
    lng: float
    maps_url: str


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


def resolve(url: str) -> tuple[str, tuple[float, float] | None]:
    """Follow Maps redirects inside the allowlist; return the final URL and coordinates."""
    if not _allowed(url):
        return url, parse_coordinates(url)
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
                return current, found
            response = client.get(current)
            location = response.headers.get("location")
            if not location:
                final = str(response.url)
                return final, parse_coordinates(final)
            if not _allowed(location):
                return current, parse_coordinates(current)
            current = location
    except httpx.HTTPError:
        return url, parse_coordinates(url)
    finally:
        client.close()
    return current, parse_coordinates(current)


def expand_and_parse(url: str) -> tuple[float, float] | None:
    return resolve(url)[1]


def name_from_url(url: str) -> str:
    value = unquote(url).replace("+", " ")
    match = PLACE_RE.search(value)
    if match:
        return match.group(1).strip()[:80]
    query = parse_qs(urlparse(url).query)
    for key in ("q", "query"):
        text = (query.get(key) or [""])[0].strip()
        if text and "," not in text and not text.replace(".", "").isdigit():
            return text[:80]
    return ""


def reverse_geocode(lat: float, lng: float) -> dict:
    try:
        response = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lng,
                "format": "jsonv2",
                "zoom": 18,
                "addressdetails": 1,
                "accept-language": "de",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=8.0,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return {}


def _address_parts(data: dict) -> tuple[str, str, str]:
    address = data.get("address") or {}
    road = address.get("road") or address.get("pedestrian") or address.get("footway") or ""
    number = address.get("house_number") or ""
    street = f"{road} {number}".strip() if number and number not in road else road
    postcode = address.get("postcode") or ""
    city = address.get("city") or address.get("town") or "Berlin"
    line = ", ".join(part for part in (street, f"{postcode} {city}".strip()) if part)
    district = (
        address.get("suburb")
        or address.get("city_district")
        or address.get("neighbourhood")
        or ""
    )
    if not line:
        line = (data.get("display_name") or "").split(",")[0]
    return line, district, address.get("name") or data.get("name") or ""


def place_info(url: str) -> PlaceInfo | None:
    final, coords = resolve(url)
    if not coords:
        return None
    lat, lng = coords
    data = reverse_geocode(lat, lng)
    address, district, osm_name = _address_parts(data)
    name = name_from_url(final) or name_from_url(url) or osm_name
    return PlaceInfo(
        name=name.strip()[:80],
        address=address.strip()[:160],
        district=district.strip()[:40],
        lat=lat,
        lng=lng,
        maps_url=url,
    )


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
