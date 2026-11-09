"""Génère l'icône CancerScan (mallette médicale blanche sur dégradé bleu) et le logo de démarrage Android.

Usage (depuis mobile/) : python tool/make_icons.py
Nécessite Pillow. Les fichiers produits sont versionnés : ce script n'est à relancer que pour changer l'icône.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RES = Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "res"
TOP, BOTTOM = (21, 101, 192), (66, 165, 245)  # #1565C0 → #42A5F5
WHITE = (255, 255, 255, 255)
S = 1024  # dessin en haute définition puis réduction (anticrénelage)


def gradient(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))  # diagonale haut-gauche → bas-droite
            px[x, y] = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
    return img


def bag(size: int, scale: float, color=WHITE, shadow: bool = False) -> Image.Image:
    """Mallette médicale centrée, occupant `scale` de la largeur."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = size * scale
    x0, x1 = (size - w) / 2, (size + w) / 2
    body_top, body_bottom = size / 2 - w * 0.30, size / 2 + w * 0.38
    r = w * 0.12
    # Poignée
    hw, ht = w * 0.36, w * 0.17
    d.rounded_rectangle([size / 2 - hw / 2, body_top - ht, size / 2 + hw / 2, body_top + r], radius=w * 0.07,
                        outline=color, width=int(w * 0.075))
    # Corps
    d.rounded_rectangle([x0, body_top, x1, body_bottom], radius=r, fill=color)
    # Croix (découpée dans le corps)
    cx, cy = size / 2, (body_top + body_bottom) / 2
    arm, thick = w * 0.19, w * 0.085
    cut = (0, 0, 0, 0)
    d.rectangle([cx - thick, cy - arm, cx + thick, cy + arm], fill=cut)
    d.rectangle([cx - arm, cy - thick, cx + arm, cy + thick], fill=cut)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sh.paste((10, 40, 90, 90), mask=img.split()[3])
        sh = sh.filter(ImageFilter.GaussianBlur(size * 0.02))
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(sh, (0, int(size * 0.015)))
        out.alpha_composite(img)
        return out
    return img


def rounded_mask(size: int, radius: float) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def save(img: Image.Image, rel: str, px: int) -> None:
    path = RES / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((px, px), Image.LANCZOS).save(path, optimize=True)


def main() -> None:
    bg = gradient(S)
    glyph = bag(S, 0.56, shadow=True)

    # Icône classique (Android < 8) : carré arrondi plein
    legacy = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    legacy.paste(bg, mask=rounded_mask(S, S * 0.22))
    legacy.alpha_composite(glyph)
    # Icône adaptative (Android ≥ 8) : premier plan transparent, zone sûre = 66 % centraux
    foreground = bag(S, 0.40, shadow=True)
    background = gradient(S)

    for density, base in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
        save(legacy, f"mipmap-{density}/ic_launcher.png", base)
        adaptive = round(base * 108 / 48)
        save(foreground, f"mipmap-{density}/ic_launcher_foreground.png", adaptive)
        save(background, f"mipmap-{density}/ic_launcher_background.png", adaptive)
        # Logo de l'écran de démarrage (Android < 12) : mallette blanche, 160 dp
        save(bag(S, 0.9), f"drawable-{density}/splash_logo.png", round(base * 160 / 48))

    # Image 512 px pour une future fiche Play Store
    legacy.resize((512, 512), Image.LANCZOS).save(Path(__file__).resolve().parent / "icon_512.png", optimize=True)
    print("Icônes générées dans", RES)


if __name__ == "__main__":
    main()
