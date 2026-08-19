"""Catalogue des layouts pour le composeur (voir CLAUDE.md §3, §7).

`app/layouts.py` sait *rendre* une section ; ce module décrit ce qu'il faut
*saisir* pour la remplir : le poids de la section (1 à 4 unités), un wireframe
en gris (l'architecture du bloc, pas son contenu) et la liste ordonnée des
champs attendus — c'est cette liste qui pilote le formulaire du composeur.

Règle : la description ci-dessous doit rester en phase avec le rendu de
`app/layouts.py` (un layout qui ne consomme qu'une image ne doit pas en
proposer trois). L'ordre des champs est aussi l'ordre des `blocs` écrits dans
`content.yaml`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.schemas import LAYOUT_HAUTEURS

# ---------------------------------------------------------------------------
# Wireframes — SVG en niveaux de gris, une unité de hauteur = 30 unités SVG
# ---------------------------------------------------------------------------

_W = 120  # largeur de référence du wireframe


def _rect(x: float, y: float, w: float, h: float, cls: str, rx: float = 1.5) -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" class="{cls}"/>'


def _titre(x: float, y: float, w: float) -> str:
    return _rect(x, y, w * 0.6, 4, "wf-titre")


def _lignes(x: float, y: float, w: float, n: int, pas: float = 6) -> str:
    """n lignes de texte, la dernière volontairement plus courte."""
    return "".join(
        _rect(x, y + i * pas, w * (0.55 if i == n - 1 else 1), 2.5, "wf-texte")
        for i in range(n)
    )


def _image(x: float, y: float, w: float, h: float) -> str:
    return _rect(x, y, w, h, "wf-image") + _rect(
        x + w / 2 - 5, y + h / 2 - 4, 10, 8, "wf-image-icone", rx=1
    )


def _svg(hauteur: int, corps: str) -> str:
    return (
        f'<svg class="wireframe" viewBox="0 0 {_W} {30 * hauteur}" '
        f'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">{corps}</svg>'
    )


def _wf_texte_seul() -> str:
    return _svg(1, _titre(6, 5, 108) + _lignes(6, 14, 108, 3))


def _wf_etape_compacte() -> str:
    return _svg(
        1,
        _titre(6, 4, 108)
        + _image(6, 11, 50, 15)
        + _rect(62, 12, 1.5, 13, "wf-lisere", rx=1)
        + _lignes(68, 14, 46, 2, pas=5),
    )


def _wf_image_gauche_texte() -> str:
    return _svg(2, _image(6, 12, 48, 36) + _titre(60, 16, 54) + _lignes(60, 26, 54, 3))


def _wf_texte_image_droite() -> str:
    return _svg(2, _titre(6, 16, 54) + _lignes(6, 26, 54, 3) + _image(66, 12, 48, 36))


def _wf_image_dessus_texte() -> str:
    return _svg(2, _titre(6, 5, 108) + _image(6, 13, 108, 27) + _lignes(6, 45, 108, 2))


def _wf_triple_image() -> str:
    corps = _titre(6, 5, 108)
    for i in range(3):
        x = 6 + i * 37
        corps += _image(x, 14, 34, 22) + _lignes(x, 40, 34, 2, pas=5)
    return _svg(2, corps)


def _wf_etape_detaillee() -> str:
    return _svg(3, _titre(6, 6, 108) + _image(6, 15, 108, 45) + _lignes(6, 66, 108, 4))


def _wf_pleine_page() -> str:
    return _svg(
        4,
        _titre(6, 8, 108)
        + _lignes(6, 20, 108, 5)
        + _rect(6, 56, 108, 16, "wf-encadre")
        + _lignes(6, 80, 108, 5),
    )


# ---------------------------------------------------------------------------
# Champs attendus par layout
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Champ:
    """Un groupe de champs répétable du formulaire de section.

    `type` colle au type de bloc produit dans `content.yaml` ; `mini`/`maxi`
    bornent la répétition (« 3 images » = mini 3, maxi 3) ; `legende` ajoute un
    champ de légende sous chaque image.
    """

    type: str  # "image" | "paragraphe" | "encadre"
    libelle: str
    mini: int = 1
    maxi: int = 1
    legende: bool = False
    aide: str = ""


@dataclass(frozen=True)
class LayoutCatalogue:
    id: str
    libelle: str
    description: str
    hauteur: int
    wireframe: str
    titre_section: bool
    champs: list[Champ] = field(default_factory=list)


def _entree(
    layout_id: str,
    libelle: str,
    description: str,
    wireframe: str,
    champs: list[Champ],
    titre_section: bool = True,
) -> LayoutCatalogue:
    return LayoutCatalogue(
        id=layout_id,
        libelle=libelle,
        description=description,
        hauteur=LAYOUT_HAUTEURS[layout_id],
        wireframe=wireframe,
        titre_section=titre_section,
        champs=champs,
    )


CATALOGUE: list[LayoutCatalogue] = [
    _entree(
        "texte-seul",
        "Texte seul",
        "Titre puis paragraphes empilés. Aucun visuel.",
        _wf_texte_seul(),
        [
            Champ("paragraphe", "Paragraphe", mini=1, maxi=4),
            Champ("encadre", "Encadré", mini=0, maxi=2),
        ],
    ),
    _entree(
        "etape-compacte",
        "Étape compacte",
        "Capture à gauche, liseré, texte centré à droite.",
        _wf_etape_compacte(),
        [
            Champ("image", "Capture", mini=1, maxi=1),
            Champ("paragraphe", "Texte de l'étape", mini=1, maxi=2),
        ],
    ),
    _entree(
        "image-gauche-texte",
        "Image à gauche + texte",
        "Capture à gauche sur toute la hauteur, texte à droite.",
        _wf_image_gauche_texte(),
        [
            Champ("image", "Capture", mini=1, maxi=1, legende=True),
            Champ("paragraphe", "Paragraphe", mini=1, maxi=3),
            Champ("encadre", "Encadré", mini=0, maxi=1),
        ],
    ),
    _entree(
        "texte-image-droite",
        "Texte + image à droite",
        "Texte à gauche, capture à droite.",
        _wf_texte_image_droite(),
        [
            Champ("image", "Capture", mini=1, maxi=1, legende=True),
            Champ("paragraphe", "Paragraphe", mini=1, maxi=3),
            Champ("encadre", "Encadré", mini=0, maxi=1),
        ],
    ),
    _entree(
        "image-dessus-texte",
        "Image au-dessus du texte",
        "Capture pleine largeur, texte en dessous.",
        _wf_image_dessus_texte(),
        [
            Champ("image", "Capture", mini=1, maxi=2, legende=True),
            Champ("paragraphe", "Paragraphe", mini=1, maxi=3),
            Champ("encadre", "Encadré", mini=0, maxi=1),
        ],
    ),
    _entree(
        "triple-image",
        "Trois images légendées",
        "Trois captures côte à côte, chacune avec sa légende.",
        _wf_triple_image(),
        [Champ("image", "Capture", mini=3, maxi=3, legende=True)],
    ),
    _entree(
        "etape-detaillee",
        "Étape détaillée",
        "Titre, capture pleine largeur, puis texte et encadrés.",
        _wf_etape_detaillee(),
        [
            Champ("image", "Capture", mini=1, maxi=2, legende=True),
            Champ("paragraphe", "Paragraphe", mini=1, maxi=4),
            Champ("encadre", "Encadré", mini=0, maxi=2),
        ],
    ),
    _entree(
        "pleine-page",
        "Pleine page",
        "Une page entière de texte et d'encadrés.",
        _wf_pleine_page(),
        [
            Champ("paragraphe", "Paragraphe", mini=1, maxi=8),
            Champ("encadre", "Encadré", mini=0, maxi=4),
        ],
    ),
]

CATALOGUE_PAR_ID: dict[str, LayoutCatalogue] = {e.id: e for e in CATALOGUE}


def catalogue_json() -> list[dict]:
    """Catalogue sérialisé pour le composeur (front)."""
    return [asdict(e) for e in CATALOGUE]
