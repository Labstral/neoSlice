"""Génère neoSlice.icns pour macOS — même logique que make_ico.py."""
from pathlib import Path
from PIL import Image, ImageFilter

SRC = Path("assets/neoSlice.png")
DST = Path("assets/neoSlice.icns")

BG_COLOR   = (7, 13, 20)   # #070D14 — fond sombre exact du thème
MARGIN_RATIO = 0.04         # 4% de marge autour du logo

# Tailles requises par macOS pour un .icns complet
SIZES = [16, 32, 64, 128, 256, 512, 1024]


def crop_to_content(src_rgba: Image.Image) -> Image.Image:
    """Recadre au contenu réel + marge, retourne une image RGBA carrée."""
    bbox = src_rgba.getbbox()
    if not bbox:
        return src_rgba
    left, top, right, bottom = bbox
    content_size = max(right - left, bottom - top)
    margin = int(content_size * MARGIN_RATIO)

    cx = (left + right) // 2
    cy = (top + bottom) // 2
    half = content_size // 2 + margin
    nl = max(0, cx - half)
    nt = max(0, cy - half)
    nr = min(src_rgba.width,  cx + half)
    nb = min(src_rgba.height, cy + half)

    cropped = src_rgba.crop((nl, nt, nr, nb))
    side = max(cropped.width, cropped.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cropped.width)  // 2
    oy = (side - cropped.height) // 2
    square.paste(cropped, (ox, oy))
    return square


def make_size(src_rgba: Image.Image, size: int) -> Image.Image:
    """Composite sur fond sombre + resize LANCZOS + sharpen adaptatif."""
    bg = Image.new("RGBA", src_rgba.size, (*BG_COLOR, 255))
    bg.paste(src_rgba, mask=src_rgba.split()[3])

    resized = bg.resize((size, size), Image.LANCZOS)

    if size <= 16:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1, percent=300, threshold=1))
        resized = resized.filter(ImageFilter.SHARPEN)
    elif size <= 32:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=1.5, percent=250, threshold=2))
        resized = resized.filter(ImageFilter.SHARPEN)
    elif size <= 64:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=2, percent=200, threshold=2))
    else:
        resized = resized.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    return resized.convert("RGBA")


def main():
    src = Image.open(SRC).convert("RGBA")
    print(f"Source : {src.size} {src.mode}")

    src = crop_to_content(src)
    print(f"Après recadrage carré : {src.size}")

    frames = {s: make_size(src, s) for s in SIZES}

    # Pillow génère le .icns directement avec toutes les tailles
    frames[SIZES[-1]].save(
        DST,
        format="ICNS",
        append_images=[frames[s] for s in SIZES[:-1]],
    )

    size_kb = DST.stat().st_size / 1024
    print(f"ICNS généré : {DST} ({size_kb:.1f} KB, tailles : {SIZES})")


if __name__ == "__main__":
    main()
