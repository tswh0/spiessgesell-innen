import pytest

from app.maps import expand_and_parse, in_berlin, parse_coordinates


@pytest.mark.parametrize(
    "text",
    [
        "https://www.google.com/maps/place/X/@52.5007,13.4183,17z/data=!4m6",
        "https://www.google.com/maps/place/X/data=!4m2!3d52.5007!4d13.4183",
        "https://maps.google.com/?q=52.5007,13.4183",
        "https://www.google.de/maps?ll=52.5007,13.4183&z=17",
        "52.5007,13.4183",
    ],
)
def test_parses_common_formats(text):
    assert parse_coordinates(text) == pytest.approx((52.5007, 13.4183))


def test_non_google_url_is_never_fetched(monkeypatch):
    import app.maps as maps

    def boom(*args, **kwargs):
        raise AssertionError("must not fetch a non-Google URL")

    monkeypatch.setattr(maps.httpx.Client, "get", boom)
    assert maps.expand_and_parse("https://example.com/@52.5,13.4") == pytest.approx((52.5, 13.4))


def test_short_link_expansion(monkeypatch):
    import app.maps as maps

    class Response:
        def __init__(self, location):
            self.headers = {"location": location} if location else {}
            self.url = "https://maps.app.goo.gl/abc"

    calls = []

    def fake_get(self, url):
        calls.append(url)
        if url.endswith("abc"):
            return Response("https://www.google.com/maps/place/X/@52.49,13.39,17z")
        return Response(None)

    monkeypatch.setattr(maps.httpx.Client, "get", fake_get)
    assert maps.expand_and_parse("https://maps.app.goo.gl/abc") == pytest.approx((52.49, 13.39))
    assert calls


def test_berlin_bounds():
    assert in_berlin(52.5, 13.4)
    assert not in_berlin(48.1, 11.5)


def test_name_from_place_url():
    import app.maps as maps

    assert maps.name_from_url(
        "https://www.google.com/maps/place/Hasir/@52.5,13.4,17z"
    ) == "Hasir"
    assert maps.name_from_url(
        "https://www.google.com/maps/place/R%C3%BCyam%20Gem%C3%BCse%20Kebab/@52.48,13.35"
    ) == "Rüyam Gemüse Kebab"
    assert maps.name_from_url("https://maps.google.com/?q=Hasir+Berlin") == "Hasir Berlin"


def test_place_info(monkeypatch):
    import app.maps as maps

    monkeypatch.setattr(maps, "resolve", lambda url: (url, (52.5, 13.42)))
    monkeypatch.setattr(
        maps,
        "reverse_geocode",
        lambda lat, lng: {
            "address": {
                "road": "Adalbertstraße",
                "house_number": "28",
                "postcode": "10999",
                "city": "Berlin",
                "suburb": "Kreuzberg",
            }
        },
    )
    info = maps.place_info("https://www.google.com/maps/place/Hasir/@52.5,13.42,17z")
    assert info == maps.PlaceInfo(
        name="Hasir",
        address="Adalbertstraße 28, 10999 Berlin",
        district="Kreuzberg",
        lat=52.5,
        lng=13.42,
        maps_url="https://www.google.com/maps/place/Hasir/@52.5,13.42,17z",
    )


def test_place_info_without_coordinates(monkeypatch):
    import app.maps as maps

    monkeypatch.setattr(maps, "resolve", lambda url: (url, None))
    assert maps.place_info("https://maps.app.goo.gl/nope") is None
