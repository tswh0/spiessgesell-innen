# spießgesell:innen

A few friends and I meet up for döner around Berlin and argue about which place is best. This is the site we use to keep score.

<p align="center">
  <img src="docs/home-mobile.jpg" width="260" alt="Map and list of döner shops on a phone">
  <img src="docs/shop-desktop.jpg" width="560" alt="Shop page with photos, score and reviews">
</p>

## What it does

- Add a shop by pasting a Google Maps link, or share one straight into the installed app. The name, street and district come from the link, and you can correct them before saving.
- Each review has a visit date, five 1–10 scores, optional text and price, and up to six photos. Photos are converted to WebP and stripped of EXIF data; tap one for the full-screen gallery.
- The map and ranking update from the reviews. The ranking shows the best overall and per category.
- Everyone uses the same password and picks a name. The browser also keeps a small identity cookie, so two people with the same name don't edit each other's reviews.

## Run it

```sh
cp .env.example .env
# set SECRET_KEY and SHARED_PASSWORD
docker compose pull
docker compose up -d
```

The published image is `ghcr.io/tswh0/spiessgesell-innen`. It is private, so run `docker login ghcr.io` with a token that has `read:packages` before pulling. Set `IMAGE_TAG` in `.env` to pin a release instead of `latest`.

The app listens on `127.0.0.1:8095`. Put Caddy or a tunnel in front; `Caddyfile.snippet` has the two lines for `doner.twh0.de`. The app trusts the proxy's `X-Forwarded-Proto` header (`FORWARDED_ALLOW_IPS=*`) because it is bound to localhost; without that, static links are generated as `http://` and browsers block the CSS as mixed content. For local development with the code bind-mounted and reload enabled:

```sh
docker compose -f compose.dev.yaml up -d --build
```

That uses `http://127.0.0.1:8090` and a separate `data-dev` volume.

Data lives in the `data` volume. Back it up with:

```sh
docker run --rm -v spiessgesell-innen_data:/data -v "$PWD":/backup alpine tar czf /backup/data.tgz -C /data .
```

The app writes a backup ZIP at 03:15 into the `backups` volume and keeps the last 14. `BACKUP_AT` and `BACKUP_KEEP` change that. The tar command above is there if you want a full volume copy instead.

## Local development

```sh
uv venv .venv && . .venv/bin/activate
uv pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python scripts/seed.py
uvicorn app.main:app --reload --port 8090
```

Run `pytest` for the tests. The seed script adds three Berlin shops; `scripts/reset.py` clears reviews or shops.

## Notes

- SQLite and uploads sit in one volume. Map tiles and reverse geocoding come from public services; the fonts are bundled, and there are no API keys.
- The PWA installs from the browser and keeps working offline.
- `/healthz` checks SQLite and the uploads directory; Docker uses it as its healthcheck.
- GitHub Actions builds a multi-arch image on every published release. Tags follow semantic versions such as `v1.1.0`, `1.1.0` and `1.1`, plus `latest`.
