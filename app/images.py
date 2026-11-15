import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 40_000_000

MAX_BYTES = 15 * 1024 * 1024
WEB_MAX = 1600
THUMB_MAX = 480


class ImageError(ValueError):
    pass


def process(data: bytes, uploads_dir: Path, thumb_dir: Path) -> dict:
    if len(data) > MAX_BYTES:
        raise ImageError("Bild ist größer als 15 MB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")

            stem = uuid.uuid4().hex
            web = image.copy()
            web.thumbnail((WEB_MAX, WEB_MAX), Image.LANCZOS)
            web_path = uploads_dir / f"{stem}.webp"
            web.save(web_path, "WEBP", quality=82, method=4)
            digest = hashlib.sha256(web_path.read_bytes()).hexdigest()

            thumb = image.copy()
            thumb.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
            thumb_path = thumb_dir / f"{stem}_t.webp"
            thumb.save(thumb_path, "WEBP", quality=75, method=4)

            return {
                "file": web_path.name,
                "thumb": thumb_path.name,
                "width": web.width,
                "height": web.height,
                "sha256": digest,
            }
    except (OSError, Image.DecompressionBombError) as exc:
        raise ImageError("Datei ist kein lesbares Bild.") from exc


def read_limited(upload, limit: int = MAX_BYTES) -> bytes:
    data = bytearray()
    while True:
        chunk = upload.file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > limit:
            raise ImageError("Bild ist größer als 15 MB.")
    return bytes(data)
