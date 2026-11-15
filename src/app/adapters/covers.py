import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.models.task import AppError

MAX_COVER_SOURCE = 10 * 1024 * 1024
MAX_COVER_OUTPUT = 2 * 1024 * 1024
MAX_PIXELS = 25_000_000


@dataclass
class CoverSource:
    image: Image.Image
    preview: bytes


def decode_cover(data: bytes) -> Image.Image:
    if len(data) > MAX_COVER_SOURCE:
        raise AppError("Исходная обложка должна быть не больше 10 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise AppError("Обложка должна содержать не больше 25 мегапикселей.")
                source.load()
                return ImageOps.exif_transpose(source).convert("RGBA")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise AppError("Не удалось прочитать изображение обложки.") from exc


def encode_cover(image: Image.Image, maximum=1500) -> bytes:
    picture = image.copy()
    picture.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
    background = Image.new("RGB", picture.size, "white")
    background.paste(picture, mask=picture.getchannel("A"))
    for quality in (90, 80, 65):
        output = BytesIO()
        background.save(output, "JPEG", quality=quality, optimize=True)
        if output.tell() <= MAX_COVER_OUTPUT:
            return output.getvalue()
    raise AppError("Не удалось уменьшить обложку до 2 МБ.")


def prepare_cover(data: bytes) -> bytes:
    return encode_cover(decode_cover(data))


def load_cover_source(value: Path | bytes, cancel) -> CoverSource:
    cancel.check()
    if isinstance(value, Path):
        with value.open("rb") as stream:
            value = stream.read(MAX_COVER_SOURCE + 1)
    image = decode_cover(value)
    cancel.check()
    preview = encode_cover(image, maximum=1000)
    cancel.check()
    return CoverSource(image, preview)


def crop_cover(source: CoverSource, selection: tuple[int, int, int], cancel) -> bytes:
    cancel.check()
    x, y, side = selection
    width, height = source.image.size
    if not all(isinstance(v, int) for v in selection) or side < 1 or min(x, y) < 0:
        raise AppError("Некорректная область обложки.")
    if x + side > width or y + side > height:
        raise AppError("Область обложки выходит за границы изображения.")
    result = encode_cover(source.image.crop((x, y, x + side, y + side)))
    cancel.check()
    return result


def load_cover(path: Path, cancel=None) -> bytes:
    if cancel:
        cancel.check()
    with path.open("rb") as stream:
        result = prepare_cover(stream.read(MAX_COVER_SOURCE + 1))
    if cancel:
        cancel.check()
    return result
