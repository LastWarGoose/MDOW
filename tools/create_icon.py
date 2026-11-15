"""Generate the MD monogram as SVG and a multi-resolution Windows icon."""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "src" / "app" / "assets"
SHAPES = [
    ("#111112", [(0, 0), (224, 0), (256, 32), (256, 256), (32, 256), (0, 224)]),
    (
        "#ff7800",
        [
            (28, 188),
            (28, 68),
            (52, 68),
            (80, 114),
            (108, 68),
            (132, 68),
            (132, 188),
            (106, 188),
            (106, 120),
            (80, 160),
            (54, 120),
            (54, 188),
        ],
    ),
    ("#ff7800", [(148, 68), (196, 68), (228, 100), (228, 156), (196, 188), (148, 188)]),
    ("#111112", [(174, 94), (184, 94), (202, 112), (202, 144), (184, 162), (174, 162)]),
]


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    picture = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(picture)
    polygons = []
    for color, points in SHAPES:
        draw.polygon([(x * 4, y * 4) for x, y in points], fill=color)
        coordinates = " ".join(f"{x},{y}" for x, y in points)
        polygons.append(f'<polygon fill="{color}" points="{coordinates}"/>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
    (ASSETS / "md.svg").write_text(svg + "".join(polygons) + "</svg>\n", encoding="utf-8")
    picture.resize((256, 256), Image.Resampling.LANCZOS).save(
        ASSETS / "md.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]
    )


if __name__ == "__main__":
    main()
