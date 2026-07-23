"""Generate KI app icons — dark geometric style with KI monogram."""
import math
import shutil
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "desktop" / "src-tauri" / "icons"
SIZES = [32, 128, 256, 512]


def draw_ki_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size * 0.12

    # Background: rounded square
    bg_color = (18, 22, 28, 255)  # #12161C
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=int(size * 0.22),
        fill=bg_color,
    )

    # Subtle hexagon accent
    cx, cy = size / 2, size / 2
    hex_r = size * 0.25
    hex_pts = []
    for i in range(6):
        angle = math.pi / 180 * (60 * i - 30)
        hex_pts.append((
            cx + hex_r * math.cos(angle),
            cy + hex_r * math.sin(angle),
        ))
    draw.polygon(hex_pts, fill=(99, 102, 241, 30))

    # "KI" text
    font_size = int(size * 0.35)
    font = None
    for name in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
    ]:
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    text = "KI"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1]
    draw.text((tx, ty), text, fill=(165, 180, 252, 255), font=font)

    # Bottom accent line
    line_w = tw * 0.5
    line_y = ty + th + size * 0.05
    lx = (size - line_w) / 2
    draw.line(
        [(lx, line_y), (lx + line_w, line_y)],
        fill=(56, 189, 248, 200),
        width=max(1, int(size * 0.015)),
    )

    return img


def save_icns(png_512: Path, output: Path):
    data = png_512.read_bytes()
    entry = b"ic07" + struct.pack(">I", 8 + len(data)) + data
    header = b"icns" + struct.pack(">I", 8 + len(entry))
    output.write_bytes(header + entry)


def save_ico(png_128: Path, output: Path):
    data = png_128.read_bytes()
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 128, 128, 0, 0, 1, 32, len(data), 22)
    output.write_bytes(header + entry + data)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pngs = {}

    for size in SIZES:
        img = draw_ki_icon(size)
        path = OUTPUT_DIR / f"ki-icon-{size}.png"
        img.save(path, "PNG")
        pngs[size] = path
        print(f"  ✓ {path.name} ({size}×{size})")

    # Tauri expected filenames
    shutil.copy(pngs[32], OUTPUT_DIR / "32x32.png")
    shutil.copy(pngs[128], OUTPUT_DIR / "128x128.png")
    shutil.copy(pngs[256], OUTPUT_DIR / "128x128@2x.png")
    shutil.copy(pngs[128], OUTPUT_DIR / "icon.png")
    print("  ✓ Copied to Tauri expected filenames")

    save_icns(pngs[512], OUTPUT_DIR / "icon.icns")
    print("  ✓ icon.icns")

    save_ico(pngs[128], OUTPUT_DIR / "icon.ico")
    print("  ✓ icon.ico")

    print("\n✅ All icons generated!")


if __name__ == "__main__":
    main()
