"""Génère neoSlice.icns pour macOS.

Le logo source est 3:2 (paysage). Pour une icône macOS carrée :
- Fond sombre #070D14 remplit tout le canvas 1024×1024
- Logo centré, occupe 85 % de la largeur (ou hauteur, selon le côté limitant)
- Sharpen adaptatif selon la taille cible
"""
from pathlib import Path
from PIL import Image, ImageFilter

SRC = Path("assets/neoSlice_transparent.png")  # 256x256, fond transparent
DST = Path("assets/neoSlice.icns")

FILL_RATIO = 0.90   # le logo occupe 90 % du canvas

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def make_size(logo_rgba: Image.Image, canvas_size: int) -> Image.Image:
    """Redimensionne le logo sur canvas transparent — pas de fond ajouté."""
    max_dim = int(canvas_size * FILL_RATIO)
    logo_w, logo_h = logo_rgba.size
    scale = min(max_dim / logo_w, max_dim / logo_h)
    new_w = int(logo_w * scale)
    new_h = int(logo_h * scale)

    logo_resized = logo_rgba.resize((new_w, new_h), Image.LANCZOS)

    # Sharpen adaptatif
    if canvas_size <= 16:
        logo_resized = logo_resized.filter(
            ImageFilter.UnsharpMask(radius=1, percent=300, threshold=1))
        logo_resized = logo_resized.filter(ImageFilter.SHARPEN)
    elif canvas_size <= 32:
        logo_resized = logo_resized.filter(
            ImageFilter.UnsharpMask(radius=1.5, percent=250, threshold=2))
        logo_resized = logo_resized.filter(ImageFilter.SHARPEN)
    elif canvas_size <= 64:
        logo_resized = logo_resized.filter(
            ImageFilter.UnsharpMask(radius=2, percent=200, threshold=2))
    else:
        logo_resized = logo_resized.filter(
            ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

    # Canvas 100% transparent + logo centré
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    ox = (canvas_size - new_w) // 2
    oy = (canvas_size - new_h) // 2
    canvas.paste(logo_resized, (ox, oy), mask=logo_resized.split()[3])
    return canvas


def main():
    src = Image.open(SRC).convert("RGBA")
    print(f"Source : {src.size} ({src.size[0]/src.size[1]:.2f} ratio)")

    frames = {s: make_size(src, s) for s in SIZES}

    frames[SIZES[-1]].save(
        DST,
        format="ICNS",
        append_images=[frames[s] for s in SIZES[:-1]],
    )

    size_kb = DST.stat().st_size / 1024
    print(f"ICNS généré : {DST} ({size_kb:.1f} KB, tailles : {SIZES})")
    print(f"Logo occupe {FILL_RATIO*100:.0f}% du canvas — fond transparent")


if __name__ == "__main__":
    main()
