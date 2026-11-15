# spießgesell:innen

Private Döner review club for Berlin. One map, one score per category, photos, a
ranking. FastAPI + SQLite in one container; the UI is server-rendered and mobile-first,
installable as a web app.

## How it works

- **Access**: one shared password (`SHARED_PASSWORD`), no accounts. After login every
  visitor picks a name; reviews carry that name. Everything is behind the password.
- **Shops**: paste the Google Maps share link — the name comes from the place in the
  link, street and Bezirk from reverse-geocoding its coordinates (Nominatim, no API
  key). A confirmation step lets you override any of them before saving.
- **Reviews**: visit date, 1–10 in five categories, optional text and price, up to six
  photos. Images are re-encoded to WebP (1600 px + 480 px thumb), EXIF stripped.
- **Map**: Leaflet + OpenStreetMap tiles; pins coloured by score, best in the accent.
- **Ranking**: overall leaderboard and per-category leaders.
- **Categories**: `seed/categories.yaml`, upserted on boot. Add a category without a
  migration; missing scores are simply left out of the averages.
- **Web app**: manifest, maskable icons and a service worker (static assets cached,
  offline page). Install from the browser's "Add to Home Screen".

## Local development

```sh
uv venv .venv && . .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # set SECRET_KEY and SHARED_PASSWORD
export $(grep -v '^#' .env | xargs)
python scripts/seed.py          # optional: three real Berlin shops
uvicorn app.main:app --reload --port 8090
```

Tests: `pytest`. The map and fonts come from the network; everything else runs offline.

## Docker

```sh
cp .env.example .env            # fill SECRET_KEY, SHARED_PASSWORD, BASE_URL
docker compose up -d --build
curl http://127.0.0.1:8095/healthz
```

`compose.yml` binds `127.0.0.1:8095` only. Put Caddy (or the tunnel) in front —
`Caddyfile.snippet` has the two lines for `doner.twh0.de`.

Data lives in `./data` (SQLite + uploads), mounted at `/data`. Back it up with:

```sh
sqlite3 data/spiessgesell-innen.sqlite3 ".backup 'backup-$(date +%F).sqlite3'"
rsync -a data/uploads/ backup-uploads/
```

Demo data: `python scripts/seed.py` adds three real shops; `python scripts/reset.py
--reviews` clears the reviews and their image files, `--all` clears shops too.

## Security notes

- No open signup; one password for the group. Anyone with it can post under any name —
  that is the trade-off you chose.
- CSRF double-submit token on every POST, signed HttpOnly cookies, login rate limit,
  CSP, `noindex`.
- Uploads are decoded by Pillow (magic bytes, 40 MP cap, 15 MB per file), re-encoded,
  stored under generated names, and served only to signed-in visitors.
- Reviews can be edited or deleted by whoever uses the same name; no stronger
  ownership check without accounts.

## Layout

```
app/main.py      routes, auth gate, uploads, aggregation calls
app/db.py        schema, queries, seeding
app/maps.py      Maps link parsing, place lookup, Nominatim, allowlisted redirects
app/images.py    Pillow pipeline (HEIC, EXIF strip, WebP)
app/security.py  password check, signed cookies, CSRF, rate limit
app/templates/   Jinja pages
app/static/      app.css, map.js, form.js, pwa.js, sw.js, manifest
app/static/brand SVG mark, favicon, PWA and apple icons
seed/            categories.yaml
scripts/         seed.py, reset.py
deploy/          user units for the LXC test instance
```
