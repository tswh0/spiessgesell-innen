import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    key        TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    hint       TEXT NOT NULL DEFAULT '',
    weight     REAL NOT NULL DEFAULT 1,
    position   INTEGER NOT NULL DEFAULT 0,
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS shops (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    slug             TEXT NOT NULL UNIQUE,
    address          TEXT NOT NULL DEFAULT '',
    district         TEXT NOT NULL DEFAULT '',
    lat              REAL NOT NULL,
    lng              REAL NOT NULL,
    google_maps_url  TEXT NOT NULL DEFAULT '',
    note             TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id     INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    author      TEXT NOT NULL,
    author_id   TEXT,
    body        TEXT NOT NULL DEFAULT '',
    visited_on  TEXT NOT NULL,
    price_eur   REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS review_scores (
    review_id     INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    category_key  TEXT NOT NULL,
    score         INTEGER NOT NULL CHECK (score BETWEEN 1 AND 10),
    PRIMARY KEY (review_id, category_key)
);

CREATE TABLE IF NOT EXISTS review_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id  INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    file       TEXT NOT NULL,
    thumb      TEXT NOT NULL,
    width      INTEGER NOT NULL,
    height     INTEGER NOT NULL,
    sha256     TEXT,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_attempts (
    key       TEXT PRIMARY KEY,
    failures  INTEGER NOT NULL,
    reset_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_shop ON reviews(shop_id, visited_on DESC);
CREATE INDEX IF NOT EXISTS idx_images_review ON review_images(review_id, position);

CREATE VIEW IF NOT EXISTS review_overall AS
SELECT review_id, AVG(score * 1.0) AS score
FROM review_scores
GROUP BY review_id;

CREATE VIEW IF NOT EXISTS shop_stats AS
SELECT s.id AS shop_id,
       COUNT(ro.review_id) AS review_count,
       AVG(ro.score) AS score
FROM shops s
LEFT JOIN reviews r ON r.shop_id = s.id
LEFT JOIN review_overall ro ON ro.review_id = r.id
GROUP BY s.id;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    legacy = settings.data_dir / "spiessgesellen.sqlite3"
    if legacy.exists() and not settings.db_path.exists():
        legacy.rename(settings.db_path)
    conn = connect(settings.db_path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        seed_categories(conn, settings.categories_file)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(reviews)")}
    if "author_id" not in columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN author_id TEXT")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(review_images)")}
    if "sha256" not in columns:
        conn.execute("ALTER TABLE review_images ADD COLUMN sha256 TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_author_id ON reviews(author_id)")


def seed_categories(conn: sqlite3.Connection, path: Path) -> None:
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    for position, row in enumerate(data):
        conn.execute(
            """
            INSERT INTO categories (key, label, hint, weight, position, active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET
                label = excluded.label,
                hint = excluded.hint,
                weight = excluded.weight,
                position = excluded.position,
                active = 1
            """,
            (
                row["key"],
                row["label"],
                row.get("hint", ""),
                float(row.get("weight", 1)),
                position,
            ),
        )


def categories(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT * FROM categories WHERE active = 1 ORDER BY position"
    ).fetchall()


def slugify(name: str) -> str:
    umlauts = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    text = name.lower()
    for src, dst in umlauts.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text[:60].rstrip("-")) or "laden"


def unique_slug(conn: sqlite3.Connection, name: str) -> str:
    base = slugify(name)
    slug, n = base, 1
    while conn.execute("SELECT 1 FROM shops WHERE slug = ?", (slug,)).fetchone():
        n += 1
        slug = f"{base}-{n}"
    return slug


def list_shops(conn, order: str = "score", district: str = ""):
    where, params = "", []
    if district:
        where, params = "WHERE s.district = ?", [district]
    order_sql = {
        "score": "st.score DESC NULLS LAST, st.review_count DESC, s.name",
        "new": "s.created_at DESC",
        "name": "s.name COLLATE NOCASE",
    }.get(order, "st.score DESC NULLS LAST, s.name")
    rows = conn.execute(
        f"""
        SELECT s.*, st.review_count, st.score,
               (SELECT file FROM review_images i
                  JOIN reviews r ON r.id = i.review_id
                 WHERE r.shop_id = s.id ORDER BY r.visited_on DESC, i.id LIMIT 1) AS photo
        FROM shops s JOIN shop_stats st ON st.shop_id = s.id
        {where}
        ORDER BY {order_sql}
        """,
        params,
    ).fetchall()
    return rows


def shop_by_slug(conn, slug: str):
    return conn.execute(
        """
        SELECT s.*, st.review_count, st.score
        FROM shops s JOIN shop_stats st ON st.shop_id = s.id
        WHERE s.slug = ?
        """,
        (slug,),
    ).fetchone()


def shop_categories(conn, shop_id: int):
    return conn.execute(
        """
        SELECT c.key, c.label, c.hint,
               (SELECT AVG(rs.score * 1.0) FROM review_scores rs
                 JOIN reviews r ON r.id = rs.review_id
                WHERE r.shop_id = ? AND rs.category_key = c.key) AS score,
               (SELECT COUNT(*) FROM review_scores rs
                 JOIN reviews r ON r.id = rs.review_id
                WHERE r.shop_id = ? AND rs.category_key = c.key) AS n
        FROM categories c
        WHERE c.active = 1
        ORDER BY c.position
        """,
        (shop_id, shop_id),
    ).fetchall()


def reviews_for_shop(conn, shop_id: int):
    rows = conn.execute(
        """
        SELECT r.*, ro.score
        FROM reviews r LEFT JOIN review_overall ro ON ro.review_id = r.id
        WHERE r.shop_id = ? ORDER BY r.visited_on DESC, r.id DESC
        """,
        (shop_id,),
    ).fetchall()
    out = []
    for row in rows:
        scores = conn.execute(
            """
            SELECT c.label, rs.score FROM review_scores rs
            JOIN categories c ON c.key = rs.category_key
            WHERE rs.review_id = ? ORDER BY c.position
            """,
            (row["id"],),
        ).fetchall()
        images = conn.execute(
            "SELECT * FROM review_images WHERE review_id = ? ORDER BY position, id",
            (row["id"],),
        ).fetchall()
        item = dict(row)
        item["scores"] = scores
        item["images"] = images
        out.append(item)
    return out


def review_by_id(conn, review_id: int):
    return conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()


def review_scores(conn, review_id: int) -> dict:
    rows = conn.execute(
        "SELECT category_key, score FROM review_scores WHERE review_id = ?", (review_id,)
    ).fetchall()
    return {row["category_key"]: row["score"] for row in rows}


def review_images(conn, review_id: int):
    return conn.execute(
        "SELECT * FROM review_images WHERE review_id = ? ORDER BY position, id",
        (review_id,),
    ).fetchall()


def create_shop(conn, *, name, address, district, lat, lng, google_maps_url, note) -> int:
    slug = unique_slug(conn, name)
    cur = conn.execute(
        """
        INSERT INTO shops (name, slug, address, district, lat, lng, google_maps_url, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (name, slug, address, district, lat, lng, google_maps_url, note),
    )
    return cur.lastrowid


def create_review(conn, *, shop_id, author, author_id, body, visited_on, price_eur, scores) -> int:
    cur = conn.execute(
        """
        INSERT INTO reviews (shop_id, author, author_id, body, visited_on, price_eur)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (shop_id, author, author_id, body, visited_on, price_eur),
    )
    review_id = cur.lastrowid
    for key, score in scores.items():
        conn.execute(
            "INSERT INTO review_scores (review_id, category_key, score) VALUES (?, ?, ?)",
            (review_id, key, score),
        )
    return review_id


def update_review(conn, review_id: int, *, author, author_id, body, visited_on, price_eur, scores) -> None:
    conn.execute(
        """
        UPDATE reviews SET author = ?, author_id = COALESCE(author_id, ?),
                           body = ?, visited_on = ?, price_eur = ?,
                           updated_at = datetime('now')
        WHERE id = ?
        """,
        (author, author_id, body, visited_on, price_eur, review_id),
    )
    conn.execute("DELETE FROM review_scores WHERE review_id = ?", (review_id,))
    for key, score in scores.items():
        conn.execute(
            "INSERT INTO review_scores (review_id, category_key, score) VALUES (?, ?, ?)",
            (review_id, key, score),
        )


def add_image(conn, review_id: int, *, file, thumb, width, height, sha256, position) -> None:
    conn.execute(
        """
        INSERT INTO review_images (review_id, file, thumb, width, height, sha256, position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (review_id, file, thumb, width, height, sha256, position),
    )


def delete_image(conn, image_id: int, review_id: int):
    row = conn.execute(
        "SELECT * FROM review_images WHERE id = ? AND review_id = ?", (image_id, review_id)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM review_images WHERE id = ?", (image_id,))
    return row


def delete_review(conn, review_id: int):
    rows = conn.execute(
        "SELECT file, thumb FROM review_images WHERE review_id = ?", (review_id,)
    ).fetchall()
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    return rows


def districts(conn):
    return [
        row["district"]
        for row in conn.execute(
            "SELECT DISTINCT district FROM shops WHERE district != '' ORDER BY district COLLATE NOCASE"
        )
    ]


def known_authors(conn):
    return [
        row["author"]
        for row in conn.execute(
            "SELECT DISTINCT author FROM reviews ORDER BY author COLLATE NOCASE"
        )
    ]


def reviews_by_author(conn, author: str, author_id: str | None = None):
    if author_id:
        where = (
            "(r.author_id = ? AND r.author = ? COLLATE NOCASE) "
            "OR (r.author_id IS NULL AND r.author = ? COLLATE NOCASE)"
        )
        params = (author_id, author, author)
    else:
        where = "r.author_id IS NULL AND r.author = ? COLLATE NOCASE"
        params = (author,)
    return conn.execute(
        f"""
        SELECT r.*, ro.score, s.name AS shop_name, s.slug AS shop_slug
        FROM reviews r
        JOIN shops s ON s.id = r.shop_id
        LEFT JOIN review_overall ro ON ro.review_id = r.id
        WHERE {where} ORDER BY r.visited_on DESC, r.id DESC
        """,
        params,
    ).fetchall()


def ranking(conn, limit: int = 100):
    return conn.execute(
        """
        SELECT s.*, st.review_count, st.score,
               GROUP_CONCAT(c.key || ':' || ROUND(cs.avg_score, 1)) AS category_scores
        FROM shops s
        JOIN shop_stats st ON st.shop_id = s.id
        LEFT JOIN (
            SELECT r.shop_id, rs.category_key, AVG(rs.score * 1.0) AS avg_score
            FROM reviews r JOIN review_scores rs ON rs.review_id = r.id
            GROUP BY r.shop_id, rs.category_key
        ) cs ON cs.shop_id = s.id
        LEFT JOIN categories c ON c.key = cs.category_key
        WHERE st.review_count > 0
        GROUP BY s.id
        ORDER BY st.score DESC, st.review_count DESC, s.name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def category_leaders(conn, min_reviews: int = 1):
    rows = conn.execute(
        """
        SELECT c.key, c.label, s.name AS shop_name, s.slug AS shop_slug,
               AVG(rs.score * 1.0) AS score, COUNT(*) AS n
        FROM review_scores rs
        JOIN categories c ON c.key = rs.category_key
        JOIN reviews r ON r.id = rs.review_id
        JOIN shops s ON s.id = r.shop_id
        WHERE c.active = 1
        GROUP BY c.key, s.id
        HAVING n >= ?
        ORDER BY c.position, score DESC
        """,
        (min_reviews,),
    ).fetchall()
    leaders, seen = [], set()
    for row in rows:
        if row["key"] in seen:
            continue
        seen.add(row["key"])
        leaders.append(row)
    return leaders


def stats(conn):
    row = conn.execute(
        "SELECT (SELECT COUNT(*) FROM shops) AS shops, (SELECT COUNT(*) FROM reviews) AS reviews"
    ).fetchone()
    return row


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
