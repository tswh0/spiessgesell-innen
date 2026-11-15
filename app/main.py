import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from . import db, images, maps
from .config import Settings, load
from .security import Auth, LoginLimiter, clean_name, csrf_ok, new_csrf

BASE = Path(__file__).resolve().parent
AUTH_MAX_AGE = 60 * 60 * 24 * 90
NAME_MAX_AGE = 60 * 60 * 24 * 365
MAX_PHOTOS = 6

templates = Jinja2Templates(directory=BASE / "templates")


class NeedLogin(Exception):
    pass


class NeedName(Exception):
    pass


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    thumbs = settings.uploads_dir / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)
    db.init_db(settings)

    app = FastAPI(title="spießgesell:innen", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.auth = Auth(settings.shared_password, settings.secret_key)
    app.state.limiter = LoginLimiter()
    app.state.thumbs = thumbs

    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

    templates.env.filters["score"] = fmt_score
    templates.env.filters["date_de"] = fmt_date
    templates.env.filters["euro"] = fmt_euro

    register_routes(app)
    return app


def _conn(request: Request):
    return db.connect(request.app.state.settings.db_path)


def _auth(request: Request) -> Auth:
    return request.app.state.auth


def current_name(request: Request) -> str | None:
    token = request.cookies.get("sg_auth")
    if not token or not _auth(request).unsign(token, AUTH_MAX_AGE):
        return None
    name_token = request.cookies.get("sg_name")
    if not name_token:
        return ""
    data = _auth(request).unsign(name_token, NAME_MAX_AGE)
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"]
    return ""


def require(request: Request) -> str:
    name = current_name(request)
    if name is None:
        raise NeedLogin()
    if name == "":
        raise NeedName()
    return name


def safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def csrf_token(request: Request) -> str:
    token = request.cookies.get("sg_csrf")
    if token:
        return token
    token = getattr(request.state, "csrf", None) or new_csrf()
    request.state.csrf = token
    return token


def render(request: Request, template: str, status: int = 200, **context):
    context.setdefault("csrf", csrf_token(request))
    context.setdefault("current_name", current_name(request))
    return templates.TemplateResponse(
        request, template, context, status_code=status
    )


def fmt_score(value) -> str:
    if value is None:
        return "–"
    return f"{float(value):.1f}".replace(".", ",")


def fmt_date(value) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except ValueError:
        return str(value or "")


def fmt_euro(value) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}".replace(".", ",") + " €"


def _export_rows(conn, photo_prefix: str):
    cats = db.categories(conn)
    shops = db.list_shops(conn, order="name")
    rows = []
    for shop in shops:
        base = [
            shop["id"], shop["name"], shop["slug"], shop["address"],
            shop["district"], f"{shop['lat']:.6f}", f"{shop['lng']:.6f}",
            shop["google_maps_url"], shop["note"],
        ]
        reviews = db.reviews_for_shop(conn, shop["id"])
        if not reviews:
            rows.append(base + [""] * (7 + len(cats)))
            continue
        for review in reviews:
            scores = db.review_scores(conn, review["id"])
            price = (
                f"{review['price_eur']:.2f}".replace(".", ",")
                if review["price_eur"] is not None else ""
            )
            rows.append(base + [
                review["id"], review["author"], fmt_date(review["visited_on"]), price,
                *[scores.get(c["key"], "") for c in cats],
                fmt_score(review["score"]) if review["score"] is not None else "",
                review["body"],
                " | ".join(f"{photo_prefix}{Path(image['file']).name}" for image in review["images"]),
            ])
    return cats, rows


def _export_csv(cats, rows) -> str:
    out = io.StringIO()
    out.write("\ufeff")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([
        "Laden-ID", "Laden", "Slug", "Adresse", "Bezirk", "Breitengrad",
        "Längengrad", "Google-Maps-Link", "Notiz", "Bewertungs-ID", "Autor",
        "Besucht am", "Preis (EUR)", *[c["label"] for c in cats], "Gesamt",
        "Text", "Fotos",
    ])
    def safe(value):
        if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
            return "'" + value
        return value
    writer.writerows([[safe(value) for value in row] for row in rows])
    return out.getvalue()


def redirect(url: str, status: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status)


def client_key(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or (request.client.host if request.client else "unknown")
    )


def parse_scores(form, allowed: set[str]) -> dict[str, int]:
    out = {}
    for key, value in form.items():
        if not key.startswith("score_"):
            continue
        category = key.removeprefix("score_")
        if category not in allowed:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= 10:
            out[category] = number
    return out


def parse_price(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        return None
    if not 0 <= value <= 100:
        return None
    return round(value, 2)


def valid_date(raw: str | None) -> str:
    try:
        parsed = date.fromisoformat(raw or "")
    except ValueError:
        return date.today().isoformat()
    if parsed > date.today() or parsed.year < 2000:
        return date.today().isoformat()
    return parsed.isoformat()


def remove_files(settings: Settings, rows) -> None:
    for row in rows:
        for name in (row["file"], row["thumb"]):
            path = settings.uploads_dir / name
            if path.exists():
                path.unlink()
        thumb = settings.uploads_dir / "thumbs" / row["thumb"]
        if thumb.exists():
            thumb.unlink()


def register_routes(app: FastAPI) -> None:
    @app.exception_handler(NeedLogin)
    async def _login(request: Request, exc: NeedLogin):
        return redirect(f"/login?next={quote(request.url.path)}")

    @app.exception_handler(NeedName)
    async def _name(request: Request, exc: NeedName):
        return redirect(f"/wer?next={quote(request.url.path)}")

    @app.middleware("http")
    async def cookies_and_headers(request: Request, call_next):
        response = await call_next(request)
        fresh = getattr(request.state, "csrf", None)
        if fresh and "sg_csrf" not in request.cookies:
            response.set_cookie(
                "sg_csrf",
                fresh,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="lax",
                secure=request.app.state.settings.secure_cookies,
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: blob: https://tile.openstreetmap.org; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "form-action 'self'; base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"ok": True})

    @app.get("/manifest.webmanifest")
    async def manifest():
        return FileResponse(BASE / "static" / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(BASE / "static" / "sw.js",
                            media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/offline", response_class=HTMLResponse)
    async def offline(request: Request):
        return render(request, "offline.html")

    @app.get("/uploads/{path:path}", response_class=FileResponse)
    async def upload_file(request: Request, path: str):
        if current_name(request) is None:
            raise NeedLogin()
        base = request.app.state.settings.uploads_dir.resolve()
        target = (base / path).resolve()
        if base != target and base not in target.parents:
            return render(request, "404.html", status=404)
        if not target.is_file():
            return render(request, "404.html", status=404)
        return FileResponse(
            target,
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request, next: str = "/"):
        if current_name(request) is not None:
            return redirect(safe_next(next))
        return render(request, "login.html", next=safe_next(next))

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
            return render(request, "login.html", status=400, next="/", error="Sitzung abgelaufen. Nochmal.")
        key = client_key(request)
        if request.app.state.limiter.blocked(key):
            return render(
                request, "login.html", status=429, next="/",
                error="Zu viele Versuche. In zehn Minuten nochmal.",
            )
        if not _auth(request).check_password(str(form.get("password", ""))):
            request.app.state.limiter.fail(key)
            return render(
                request, "login.html", status=401,
                next=safe_next(str(form.get("next", "/"))),
                error="Falsches Passwort.",
            )
        request.app.state.limiter.reset(key)
        target = safe_next(str(form.get("next", "/")))
        response = redirect(
            f"/wer?next={quote(target)}" if _needs_name(request) else target
        )
        response.set_cookie(
            "sg_auth",
            _auth(request).sign({"v": 1}),
            max_age=AUTH_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.app.state.settings.secure_cookies,
        )
        return response

    def _needs_name(request: Request) -> bool:
        name = current_name(request)
        return name is None or name == ""

    @app.get("/wer", response_class=HTMLResponse)
    async def name_form(request: Request, next: str = "/"):
        if current_name(request) is None:
            return redirect("/login")
        conn = _conn(request)
        try:
            authors = db.known_authors(conn)
        finally:
            conn.close()
        return render(
            request,
            "name.html",
            next=safe_next(next),
            authors=authors,
            name=current_name(request) or "",
        )

    @app.post("/wer")
    async def set_name(request: Request):
        if current_name(request) is None:
            return redirect("/login")
        form = await request.form()
        if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
            return render(
                request, "name.html", status=400, next="/", authors=[],
                name="", error="Sitzung abgelaufen. Nochmal.",
            )
        name = clean_name(str(form.get("name", "")))
        if not name:
            conn = _conn(request)
            try:
                authors = db.known_authors(conn)
            finally:
                conn.close()
            return render(
                request, "name.html", status=400,
                next=safe_next(str(form.get("next", "/"))),
                authors=authors, name=str(form.get("name", "")),
                error="Bitte einen Namen mit 1–40 Zeichen.",
            )
        response = redirect(safe_next(str(form.get("next", "/"))))
        response.set_cookie(
            "sg_name",
            _auth(request).sign({"name": name}),
            max_age=NAME_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.app.state.settings.secure_cookies,
        )
        return response

    @app.post("/logout")
    async def logout(request: Request):
        form = await request.form()
        if csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
            response = redirect("/login")
            response.delete_cookie("sg_auth")
            response.delete_cookie("sg_name")
            return response
        return redirect("/")

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request, order: str = "score", bezirk: str = ""):
        require(request)
        conn = _conn(request)
        try:
            shops = db.list_shops(conn, order=order, district=bezirk)
            districts = db.districts(conn)
            totals = db.stats(conn)
        finally:
            conn.close()
        shop_data = [
            {
                "slug": row["slug"],
                "name": row["name"],
                "lat": row["lat"],
                "lng": row["lng"],
                "score": row["score"],
                "count": row["review_count"],
                "district": row["district"],
                "best": index == 0 and row["score"] is not None,
                "photo": f"/uploads/thumbs/{row['photo'].replace('.webp', '_t.webp')}"
                if row["photo"]
                else None,
            }
            for index, row in enumerate(shops)
        ]
        return render(
            request,
            "index.html",
            shops=shops,
            districts=districts,
            totals=totals,
            order=order,
            bezirk=bezirk,
            shop_json=json.dumps(shop_data, ensure_ascii=False),
            page="home",
        )

    @app.get("/laden/{slug}", response_class=HTMLResponse)
    async def shop_page(request: Request, slug: str):
        require(request)
        conn = _conn(request)
        try:
            shop = db.shop_by_slug(conn, slug)
            if not shop:
                return render(request, "404.html", status=404)
            categories = db.shop_categories(conn, shop["id"])
            reviews = db.reviews_for_shop(conn, shop["id"])
        finally:
            conn.close()
        hero = None
        for review in reviews:
            if review["images"]:
                hero = review["images"][0]
                break
        return render(
            request,
            "shop.html",
            shop=shop,
            categories=categories,
            reviews=reviews,
            hero=hero,
            directions=maps.maps_link(shop["lat"], shop["lng"]),
            page="shop",
        )

    @app.get("/laeden/neu", response_class=HTMLResponse)
    async def new_shop_form(request: Request):
        require(request)
        return render(request, "new_shop.html", page="new")

    @app.post("/laeden/neu")
    async def new_shop_lookup(request: Request):
        require(request)
        form = await request.form()
        link = str(form.get("link", "")).strip()
        if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
            return render(request, "new_shop.html", status=400,
                          error="Sitzung abgelaufen. Nochmal.", link=link)
        if not link:
            return render(request, "new_shop.html", status=400,
                          error="Bitte den Google-Maps-Link einfügen.", link=link)
        info = await run_in_threadpool(maps.place_info, link)
        if not info:
            return render(
                request, "new_shop.html", status=400,
                error="Im Link stecken keine Koordinaten. Nimm den Teilen-Link aus Google Maps.",
                link=link,
            )
        return render(
            request, "new_shop_confirm.html",
            info=info, link=link, page="new", error=None,
        )

    @app.post("/laeden/neu/anlegen")
    async def new_shop_create(request: Request):
        require(request)
        form = await request.form()
        link = str(form.get("link", "")).strip()
        name = " ".join(str(form.get("name", "")).split())[:80]
        address = str(form.get("address", "")).strip()[:160]
        district = str(form.get("district", "")).strip()[:40]
        note = str(form.get("note", "")).strip()[:500]
        try:
            lat = float(str(form.get("lat", "")))
            lng = float(str(form.get("lng", "")))
        except ValueError:
            lat = lng = 0.0
        info = maps.PlaceInfo(
            name=name, address=address, district=district,
            lat=lat, lng=lng, maps_url=link,
        )
        if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
            return render(request, "new_shop_confirm.html", status=400,
                          info=info, link=link, page="new",
                          error="Sitzung abgelaufen. Nochmal.")
        if len(name) < 2:
            return render(request, "new_shop_confirm.html", status=400,
                          info=info, link=link, page="new",
                          error="Wie heißt der Laden?")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return render(request, "new_shop_confirm.html", status=400,
                          info=info, link=link, page="new",
                          error="Koordinaten fehlen. Nochmal über den Link.")
        if not maps.in_berlin(lat, lng):
            return render(request, "new_shop_confirm.html", status=400,
                          info=info, link=link, page="new",
                          error="Der Laden liegt nicht in Berlin.")
        conn = _conn(request)
        try:
            shop_id = db.create_shop(
                conn, name=name, address=address, district=district,
                lat=lat, lng=lng, google_maps_url=link, note=note,
            )
            conn.commit()
            shop = conn.execute("SELECT slug FROM shops WHERE id = ?", (shop_id,)).fetchone()
        finally:
            conn.close()
        return redirect(f"/laden/{shop['slug']}")

    @app.get("/laden/{slug}/bewerten", response_class=HTMLResponse)
    async def review_form(request: Request, slug: str):
        require(request)
        conn = _conn(request)
        try:
            shop = db.shop_by_slug(conn, slug)
            categories = db.categories(conn)
        finally:
            conn.close()
        if not shop:
            return render(request, "404.html", status=404)
        return render(
            request, "review_form.html", shop=shop, categories=categories,
            today=date.today().isoformat(), review=None, scores={}, photos=[],
            error=None, page="review",
        )

    @app.post("/laden/{slug}/bewerten")
    async def review_create(request: Request, slug: str):
        name = require(request)
        form = await request.form()
        conn = _conn(request)
        try:
            shop = db.shop_by_slug(conn, slug)
            categories = db.categories(conn)
            if not shop:
                return render(request, "404.html", status=404)
            if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=date.today().isoformat(), review=None, scores={},
                              photos=[], error="Sitzung abgelaufen. Nochmal.", page="review")
            scores = parse_scores(form, {c["key"] for c in categories})
            missing = [c["label"] for c in categories if c["key"] not in scores]
            if missing:
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=valid_date(str(form.get("visited_on"))),
                              review=None, scores=scores, photos=[],
                              error="Noch Punkte vergeben für: " + ", ".join(missing) + ".",
                              page="review")
            review_id = db.create_review(
                conn,
                shop_id=shop["id"],
                author=name,
                body=str(form.get("body", "")).strip()[:4000],
                visited_on=valid_date(str(form.get("visited_on"))),
                price_eur=parse_price(str(form.get("price", ""))),
                scores=scores,
            )
            conn.commit()
            saved = await _save_photos(request, form, review_id, conn, start=0)
            if saved["error"]:
                db.delete_review(conn, review_id)
                conn.commit()
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=date.today().isoformat(), review=None, scores=scores,
                              photos=[], error=saved["error"], page="review")
            conn.commit()
        finally:
            conn.close()
        return redirect(f"/laden/{slug}")

    async def _save_photos(request: Request, form, review_id: int, conn, start: int) -> dict:
        settings = request.app.state.settings
        uploads = form.getlist("photos")
        uploads = [u for u in uploads if getattr(u, "filename", "")]
        if start + len(uploads) > MAX_PHOTOS:
            return {"error": f"Höchstens {MAX_PHOTOS} Fotos pro Bewertung.", "count": 0}
        for offset, upload in enumerate(uploads):
            try:
                data = await run_in_threadpool(images.read_limited, upload)
                processed = await run_in_threadpool(
                    images.process, data, settings.uploads_dir, request.app.state.thumbs
                )
            except images.ImageError as exc:
                return {"error": str(exc), "count": offset}
            db.add_image(
                conn, review_id,
                file=processed["file"], thumb=processed["thumb"],
                width=processed["width"], height=processed["height"],
                position=start + offset,
            )
        return {"error": None, "count": len(uploads)}

    @app.get("/bewertungen/{review_id}/bearbeiten", response_class=HTMLResponse)
    async def review_edit_form(request: Request, review_id: int):
        name = require(request)
        conn = _conn(request)
        try:
            review = db.review_by_id(conn, review_id)
            if not review or review["author"] != name:
                return render(request, "404.html", status=404)
            shop = conn.execute(
                "SELECT * FROM shops WHERE id = ?", (review["shop_id"],)
            ).fetchone()
            categories = db.categories(conn)
            scores = db.review_scores(conn, review_id)
            photos = db.review_images(conn, review_id)
        finally:
            conn.close()
        return render(
            request, "review_form.html", shop=shop, categories=categories,
            today=review["visited_on"], review=review, scores=scores,
            photos=photos, error=None, page="review",
        )

    @app.post("/bewertungen/{review_id}")
    async def review_update(request: Request, review_id: int):
        name = require(request)
        form = await request.form()
        conn = _conn(request)
        try:
            review = db.review_by_id(conn, review_id)
            if not review or review["author"] != name:
                return render(request, "404.html", status=404)
            shop = conn.execute("SELECT * FROM shops WHERE id = ?", (review["shop_id"],)).fetchone()
            categories = db.categories(conn)
            if not csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=review["visited_on"], review=review,
                              scores=db.review_scores(conn, review_id),
                              photos=db.review_images(conn, review_id),
                              error="Sitzung abgelaufen. Nochmal.", page="review")
            scores = parse_scores(form, {c["key"] for c in categories})
            missing = [c["label"] for c in categories if c["key"] not in scores]
            if missing:
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=valid_date(str(form.get("visited_on"))),
                              review=review, scores=scores,
                              photos=db.review_images(conn, review_id),
                              error="Noch Punkte vergeben für: " + ", ".join(missing) + ".",
                              page="review")
            db.update_review(
                conn, review_id, author=name,
                body=str(form.get("body", "")).strip()[:4000],
                visited_on=valid_date(str(form.get("visited_on"))),
                price_eur=parse_price(str(form.get("price", ""))),
                scores=scores,
            )
            current = db.review_images(conn, review_id)
            remove_ids = {int(x) for x in form.getlist("remove_image") if str(x).isdigit()}
            for image in current:
                if image["id"] in remove_ids:
                    row = db.delete_image(conn, image["id"], review_id)
                    if row:
                        remove_files(request.app.state.settings, [row])
            saved = await _save_photos(request, form, review_id, conn, len(current) - len(remove_ids))
            if saved["error"]:
                conn.rollback()
                return render(request, "review_form.html", status=400,
                              shop=shop, categories=categories,
                              today=valid_date(str(form.get("visited_on"))),
                              review=review, scores=scores,
                              photos=db.review_images(conn, review_id),
                              error=saved["error"], page="review")
            conn.commit()
        finally:
            conn.close()
        return redirect(f"/laden/{shop['slug']}")

    @app.post("/bewertungen/{review_id}/loeschen")
    async def review_delete(request: Request, review_id: int):
        name = require(request)
        form = await request.form()
        conn = _conn(request)
        try:
            review = db.review_by_id(conn, review_id)
            if not review or review["author"] != name:
                return render(request, "404.html", status=404)
            shop = conn.execute("SELECT slug FROM shops WHERE id = ?", (review["shop_id"],)).fetchone()
            if csrf_ok(request.cookies.get("sg_csrf"), form.get("csrf")):
                files = db.delete_review(conn, review_id)
                conn.commit()
                remove_files(request.app.state.settings, files)
        finally:
            conn.close()
        return redirect(f"/laden/{shop['slug']}")

    @app.get("/rangliste", response_class=HTMLResponse)
    async def ranking_page(request: Request):
        require(request)
        conn = _conn(request)
        try:
            rows = db.ranking(conn)
            leaders = db.category_leaders(conn)
            categories = db.categories(conn)
        finally:
            conn.close()
        parsed = []
        for row in rows:
            scores = {}
            for pair in (row["category_scores"] or "").split(","):
                if ":" in pair:
                    key, value = pair.split(":", 1)
                    scores[key] = float(value)
            item = dict(row)
            item["scores"] = scores
            parsed.append(item)
        return render(
            request, "ranking.html", rows=parsed, leaders=leaders,
            categories=categories, page="ranking",
        )

    @app.get("/export.csv")
    async def export_csv(request: Request):
        require(request)
        conn = _conn(request)
        try:
            cats, rows = _export_rows(conn, "/uploads/")
        finally:
            conn.close()
        filename = f"spiessgesell-innen-{date.today().isoformat()}.csv"
        return Response(
            _export_csv(cats, rows),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/export.zip")
    async def export_zip(request: Request):
        require(request)
        conn = _conn(request)
        try:
            cats, rows = _export_rows(conn, "fotos/")
        finally:
            conn.close()

        stamp = date.today().isoformat()
        csv_name = f"spiessgesell-innen-{stamp}.csv"
        uploads = request.app.state.settings.uploads_dir
        photos = [
            path for path in sorted(uploads.iterdir())
            if path.is_file() and not path.name.startswith(".")
        ]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(csv_name, _export_csv(cats, rows))
            for photo in photos:
                archive.write(photo, f"fotos/{photo.name}")
        filename = f"spiessgesell-innen-{stamp}.zip"
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/ich", response_class=HTMLResponse)
    async def my_page(request: Request):
        name = require(request)
        conn = _conn(request)
        try:
            reviews = db.reviews_by_author(conn, name)
        finally:
            conn.close()
        return render(request, "me.html", reviews=reviews, page="me")

    @app.get("/logout", response_class=HTMLResponse)
    async def logout_get(request: Request):
        return redirect("/")

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return render(request, "404.html", status=404)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc):
        return render(request, "500.html", status=500)


app = create_app()
