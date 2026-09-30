"""Catalogue du composeur : formulaire et wireframe de chaque modèle.

Tout est **dérivé** du registre `app/modeles.py` — rien n'est déclaré deux
fois. Les champs viennent de la disposition du modèle (nombre d'emplacements
image, style du texte) ; le wireframe est dessiné en mm avec la même
`Geometrie` que le rendu, donc à l'échelle exacte de la section produite, pour
chacun des poids compatibles.

L'ordre des champs est l'ordre des `blocs` écrits dans `content.yaml` :
images, puis texte (paragraphes ou éléments de liste), puis encarts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.modeles import FAMILLES, MODELES, Geometrie, Modele, lignes_effectives


@dataclass(frozen=True)
class Champ:
    """Un groupe de champs répétable du formulaire de section.

    `type` = type de bloc produit dans content.yaml ; `mini`/`maxi` bornent la
    répétition (« 3 images » = mini 3, maxi 3) ; `legende` ajoute un champ de
    légende sous chaque image, `padding` le réglage de marge intérieure.
    """

    type: str  # "image" | "paragraphe" | "item" | "encadre"
    libelle: str
    mini: int = 1
    maxi: int = 1
    legende: bool = False
    padding: bool = False


def champs_de(m: Modele) -> list[Champ]:
    champs: list[Champ] = []
    if m.a_images:
        n = m.emplacements
        champs.append(
            Champ("image", "Capture", mini=n, maxi=m.images_max or n,
                  legende=m.legendes, padding=True)
        )
    if m.texte != "aucun":
        if m.style_texte == "items":
            champs.append(Champ("paragraphe", "Introduction", mini=0, maxi=1))
            champs.append(Champ("item", "Élément de liste", mini=2, maxi=6))
        elif m.paragraphes_max:
            libelle = "Texte encadré" if m.style_texte == "cadre" else "Paragraphe"
            champs.append(Champ("paragraphe", libelle, mini=1, maxi=m.paragraphes_max))
    champs.append(Champ("encadre", "Encart", mini=m.encarts_min, maxi=m.encarts_max))
    return champs


# ---------------------------------------------------------------------------
# Wireframes (SVG en mm, niveaux de gris)
# ---------------------------------------------------------------------------

_LIGNE_H = 2.4
_LIGNE_PAS = 5.2


def _r(x: float, y: float, w: float, h: float, cls: str, rx: float = 1.2) -> str:
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0.5):.1f}" '
            f'height="{max(h, 0.5):.1f}" rx="{rx}" class="{cls}"/>')


def _lignes(x: float, y: float, w: float, n: int) -> str:
    return "".join(
        _r(x, y + i * _LIGNE_PAS, w * (0.6 if i == n - 1 else 1), _LIGNE_H, "wf-texte")
        for i in range(n)
    )


def _image(x: float, y: float, w: float, h: float) -> str:
    icone = min(w, h) * 0.28
    return _r(x, y, w, h, "wf-image") + _r(
        x + (w - icone) / 2, y + (h - icone * 0.8) / 2, icone, icone * 0.8, "wf-image-icone"
    )


def _bloc_texte(m: Modele, x: float, y: float, w: float, h: float, centre: bool = True,
                max_lignes: int = 6) -> str:
    """Zone de texte dessinée selon le style du modèle."""
    if m.paragraphes_max == 0 and m.style_texte != "items":
        # Encart seul : un cadre et son pictogramme.
        bh = min(h, 18.0)
        by = y + (h - bh) / 2 if centre else y
        return (_r(x, by, w, bh, "wf-encadre", rx=2.5)
                + f'<circle cx="{x + 7:.1f}" cy="{by + bh / 2:.1f}" r="2.8" class="wf-image-icone"/>'
                + _lignes(x + 13, by + bh / 2 - 1.2, w * 0.55, 1))
    n = max(1, min(max_lignes, int(h // _LIGNE_PAS) - 1))
    if m.style_texte == "items":
        n = max(2, min(4, int(h // 12)))
        bloc_h = n * 11
        y0 = y + (h - bloc_h) / 2 if centre else y
        out = ""
        for i in range(n):
            yy = y0 + i * 11
            out += _r(x, yy, 6, 6, "wf-image-icone", rx=1) + _r(x + 8.5, yy - 0.5, 1.2, 7, "wf-lisere", rx=0.6)
            out += _lignes(x + 12, yy + 1.8, w - 12, 1)
        return out
    if m.style_texte == "cadre":
        k = 2 if h > 30 else 1
        bh = min(22.0, (h - 4 * (k - 1)) / k)
        y0 = y + (h - (k * bh + (k - 1) * 4)) / 2 if centre else y
        out = ""
        for i in range(k):
            yy = y0 + i * (bh + 4)
            out += _r(x, yy, w, bh, "wf-encadre", rx=2)
            out += _lignes(x + 4, yy + 4, w - 8, max(1, min(3, int((bh - 6) // _LIGNE_PAS))))
        return out
    if m.style_texte == "colonnes":
        demi = (w - 8) / 2
        return _lignes(x, y, demi, n) + _lignes(x + demi + 8, y, demi, max(1, n - 1))
    bloc_h = n * _LIGNE_PAS
    y0 = y + (h - bloc_h) / 2 if centre else y
    if m.style_texte == "lisere":
        return (_r(x, y0 - 1, 1.3, bloc_h, "wf-lisere", rx=0.6)
                + _lignes(x + 5, y0, w - 5, n))
    return _lignes(x, y0, w, n)


def _grille(m: Modele, x: float, y: float, w: float, h: float, geom: Geometrie,
            colonnes: int | None = None) -> str:
    colonnes = colonnes or m.colonnes
    lignes = lignes_effectives(m, 0) if colonnes == m.colonnes else 1
    esp = geom.espace_images_mm
    cw = (w - (colonnes - 1) * esp) / colonnes
    media = geom.media_mm(m, h, lignes)
    rang_h = media + (geom.legende_mm if m.legendes else 0)
    total = lignes * rang_h + (lignes - 1) * esp
    y0 = y + max(0.0, (h - total) / 2)
    out = ""
    for r in range(lignes):
        for c in range(colonnes):
            cx = x + c * (cw + esp)
            cy = y0 + r * (rang_h + esp)
            out += _image(cx, cy, cw, media)
            if m.legendes:
                out += _r(cx + cw * 0.2, cy + media + 2.4, cw * 0.6, 1.8, "wf-texte")
    return out


def wireframe(m: Modele, hauteur: int, geom: Geometrie) -> str:
    """Architecture de la section en gris, à l'échelle de la page."""
    largeur = geom.largeur_mm
    haut = geom.section_mm(hauteur)
    corps_y = geom.pad_haut_mm + geom.titre_mm
    corps = geom.corps_mm(hauteur, avec_titre=True)
    out = _r(0, geom.pad_haut_mm + 0.5, largeur * 0.45, 4.5, "wf-titre")

    if m.texte == "seul":
        # Plus la section est haute, plus elle porte de texte.
        out += _bloc_texte(m, 0, corps_y, largeur, min(corps, 16 + 16 * hauteur),
                           centre=m.paragraphes_max == 0, max_lignes=3 * hauteur + 1)
    elif m.texte == "aucun":
        out += _grille(m, 0, corps_y, largeur, geom.zone_images_mm(m, hauteur, True, 0), geom)
    elif m.texte in ("dessous", "dessus"):
        zone = geom.zone_images_mm(m, hauteur, True, 0)
        reste = corps - zone - 3
        if m.texte == "dessous":
            out += _grille(m, 0, corps_y, largeur, zone, geom)
            out += _bloc_texte(m, 0, corps_y + zone + 3, largeur, min(reste, 30), centre=False)
        else:
            out += _bloc_texte(m, 0, corps_y, largeur, min(reste, 16), centre=False)
            out += _grille(m, 0, corps_y + reste + 3, largeur, zone, geom)
    else:
        zi = largeur * m.ratio
        g = geom.gouttiere_mm
        if m.texte == "milieu":
            zt = largeur - 2 * zi - 2 * g
            out += _grille(m, 0, corps_y, zi, corps, geom, colonnes=1)
            out += _bloc_texte(m, zi + g, corps_y, zt, corps)
            out += _grille(m, zi + zt + 2 * g, corps_y, zi, corps, geom, colonnes=1)
        else:
            zt = largeur - zi - g
            xi, xt = (0, zi + g) if m.texte == "droite" else (zt + g, 0)
            out += _grille(m, xi, corps_y, zi, corps, geom)
            out += _bloc_texte(m, xt, corps_y, zt, corps)

    return (
        f'<svg class="wireframe" viewBox="0 0 {largeur:.1f} {haut:.1f}" '
        f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">{out}</svg>'
    )


# ---------------------------------------------------------------------------
# Export pour le composeur
# ---------------------------------------------------------------------------

def catalogue_json(geom: Geometrie) -> dict:
    """Modèles, familles et poids, prêts pour le panneau « Ajouter une section »."""
    return {
        "familles": [{"id": i, "libelle": l} for i, l in FAMILLES],
        "modeles": [
            {
                "id": m.id,
                "libelle": m.libelle,
                "description": m.description,
                "famille": m.famille,
                "hauteurs": list(m.hauteurs),
                "defaut": m.defaut,
                "champs": [asdict(c) for c in champs_de(m)],
                "wireframes": {str(h): wireframe(m, h, geom) for h in m.hauteurs},
            }
            for m in MODELES
        ],
    }
