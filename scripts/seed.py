#!/usr/bin/env python3
"""Seed the three demo shops. Idempotent by slug."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db
from app.config import load

SHOPS = [
    {
        "name": "Hasir",
        "address": "Adalbertstraße 28, 10999 Berlin",
        "district": "Kreuzberg",
        "lat": 52.5007,
        "lng": 13.4183,
        "google_maps_url": "https://www.google.com/maps/place/Hasir/@52.5007,13.4183,17z",
    },
    {
        "name": "Imren",
        "address": "Karl-Marx-Straße 94, 12043 Berlin",
        "district": "Neukölln",
        "lat": 52.4780,
        "lng": 13.4375,
        "google_maps_url": "https://www.google.com/maps/place/Imren/@52.4780,13.4375,17z",
    },
    {
        "name": "Rüyam Gemüse Kebab",
        "address": "Hauptstraße 133, 10827 Berlin",
        "district": "Schöneberg",
        "lat": 52.4841,
        "lng": 13.3533,
        "google_maps_url": "https://www.google.com/maps/place/R%C3%BCyam/@52.4841,13.3533,17z",
    },
]


def main() -> None:
    settings = load()
    db.init_db(settings)
    conn = db.connect(settings.db_path)
    try:
        for shop in SHOPS:
            if conn.execute("SELECT 1 FROM shops WHERE slug = ?", (db.slugify(shop["name"]),)).fetchone():
                continue
            db.create_shop(
                conn,
                name=shop["name"],
                address=shop["address"],
                district=shop["district"],
                lat=shop["lat"],
                lng=shop["lng"],
                google_maps_url=shop["google_maps_url"],
                note="",
            )
            print("added", shop["name"])
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
