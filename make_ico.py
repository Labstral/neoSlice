"""Génère neoSlice.ico avec fond solide et sharpen agressif."""
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw

SRC = Path("assets/neoSlice.png")
DST = Path("assets/neoSlice.ico")

BG_COLOR = (7, 13, 20)          # #070D14 — fond sombre exact du thème
MARGIN_RATIO = 0.04             # 4% de marge autour du logo

SIZES = [256, 128, 64, 48, 32, 24, 16]


def crop_to_content(src_rgba: Image.Image) -> Image.Image:
    """Recadre au contenu réel + petite marge, retourne une image RGBA carrée."""
    bbox = src_rgba.getbbox()
    if not bbox:
        return src_rgba
    left, top, right, bottom = bbox
    content_size = max(right - left, bottom - top)
    margin = int(content_size * MARGIN_RATIO)

    # Centrer le contenu dans un carré avec marge
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    half = content_size // 2 + margin
    nl = max(0, cx - half)
    nt = max(0, cy - half)
    nr = min(src_rgba.width,  cx + half)
    nb = min(src_rgba.height, cy + half)

    cropped = src_rgba.crop((nl, nt, nr, nb))
    # Rendre carré si légèrement asymétrique
    side = max(cropped.width, cropped.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cropped.width)  // 2
    oy = (side - cropped.height) // 2
    square.paste(cropped, (ox, oy))
    return square


def make_size(src_rgba: Image.Image, size: int) -> Image.Image:
    # Composite sur fond solide
    bg = Image.new("RGB", src_rgba.size, BG_COLOR)
    bg.paste(src_rgba, mask=src_rgba.split()[3])

    # Redimensionner
    resized = bg.resize((size, size), Image.LANCZOS)

    # Sharpen adaptatif selon la taille
    if size <= 16:
        # Très petite : sharpen maximum
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
    print(f"Source: {src.size} {src.mode}")

    src = crop_to_content(src)
    print(f"Après recadrage: {src.size}")

    frames = [make_size(src, s) for s in SIZES]

    # Sauvegarder — le premier frame est la taille principale (256)
    frames[0].save(
        DST,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=frames[1:],
    )

    size_kb = DST.stat().st_size / 1024
    print(f"ICO généré : {DST} ({size_kb:.1f} KB, {len(SIZES)} tailles)")

    # Vérifier le contenu ICO
    ico = Image.open(DST)
    print(f"ICO sizes disponibles : {ico.info.get('sizes', 'N/A')}")


if __name__ == "__main__":
    main()
