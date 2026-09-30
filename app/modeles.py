"""Registre des modèles de section — source unique (voir CLAUDE.md §3).

Un *modèle* décrit l'architecture d'une section : disposition des images,
position et style du texte, poids compatibles. Trois consommateurs en dérivent,
ce qui les garde synchrones par construction :

- `app/layouts.py` rend la section en HTML ;
- `app/catalogue.py` en tire les champs du formulaire et le wireframe ;
- `app/schemas.py` valide `layout` et `hauteur` dans `content.yaml`.

La **géométrie** (hauteurs en mm) est aussi calculée ici, depuis la charte :
une section a une hauteur fixe (son poids × l'unité de page), et chaque boîte
image reçoit une hauteur explicite pour que l'image la remplisse en
`object-fit: contain`. Calculer en mm plutôt qu'en `calc()` CSS garantit un
rendu identique dans le navigateur et dans WeasyPrint. Le CSS du template,
lui, ne porte que le style (couleurs, bordures, typographie).

Ce module ne dépend d'aucun autre module du projet (pas même `schemas`), pour
pouvoir être importé partout sans cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------

PositionTexte = Literal["aucun", "seul", "droite", "gauche", "dessous", "dessus", "milieu"]
StyleTexte = Literal["simple", "lisere", "cadre", "items", "colonnes"]


@dataclass(frozen=True)
class Modele:
    """Architecture d'une section.

    `colonnes` × `lignes` = nombre d'emplacements image (0 colonne = pas
    d'image). Des images au-delà (content.yaml écrit à la main) ajoutent des
    lignes plutôt que d'être perdues. `ratio` = part de la largeur occupée par
    la zone images quand le texte est à côté. `part_images` = part de la
    hauteur prise par les images quand le texte est dessus/dessous.
    """

    id: str
    libelle: str
    description: str
    famille: str
    hauteurs: tuple[int, ...]
    defaut: int
    texte: PositionTexte
    colonnes: int = 0
    lignes: int = 1
    style_texte: StyleTexte = "simple"
    ratio: float = 0.5
    part_images: float = 0.62
    legendes: bool = False
    images_max: int | None = None  # défaut : colonnes × lignes
    paragraphes_max: int = 4
    encarts_min: int = 0
    encarts_max: int = 2

    @property
    def emplacements(self) -> int:
        return self.colonnes * self.lignes

    @property
    def a_images(self) -> bool:
        return self.colonnes > 0


FAMILLES = [
    ("texte", "Texte"),
    ("image-texte", "Une image + texte"),
    ("images-texte", "Plusieurs images + texte"),
    ("galerie", "Images seules"),
]


def _m(**kw) -> Modele:
    return Modele(**kw)


MODELES: list[Modele] = [
    # --- Texte -------------------------------------------------------------
    _m(id="texte-seul", libelle="Texte seul", famille="texte",
       description="Titre puis paragraphes. Les encarts s'insèrent dans le fil.",
       hauteurs=(1, 2, 3, 4), defaut=1, texte="seul"),
    _m(id="texte-lisere", libelle="Texte à liseré", famille="texte",
       description="Paragraphes soulignés d'un liseré vertical.",
       hauteurs=(1, 2, 3, 4), defaut=1, texte="seul", style_texte="lisere"),
    _m(id="texte-cadre", libelle="Texte encadré", famille="texte",
       description="Chaque paragraphe dans un cadre.",
       hauteurs=(1, 2, 3, 4), defaut=1, texte="seul", style_texte="cadre"),
    _m(id="texte-deux-colonnes", libelle="Texte sur deux colonnes", famille="texte",
       description="Le texte se répartit sur deux colonnes.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="seul", style_texte="colonnes",
       paragraphes_max=6),
    _m(id="encart-seul", libelle="Encart pleine largeur", famille="texte",
       description="Un message mis en avant : astuce, attention ou info.",
       hauteurs=(1,), defaut=1, texte="seul", paragraphes_max=0, encarts_min=1),
    _m(id="pleine-page", libelle="Pleine page", famille="texte",
       description="Une page de texte et d'encarts.",
       hauteurs=(2, 3, 4), defaut=4, texte="seul", paragraphes_max=8, encarts_max=4),
    # --- Une image + texte -------------------------------------------------
    _m(id="etape-compacte", libelle="Image + texte à liseré", famille="image-texte",
       description="Capture à gauche, liseré, texte centré à droite.",
       hauteurs=(1, 2, 3, 4), defaut=1, texte="droite", colonnes=1,
       style_texte="lisere", ratio=0.48),
    _m(id="texte-lisere-image", libelle="Texte à liseré + image", famille="image-texte",
       description="Texte à liseré à gauche, capture à droite.",
       hauteurs=(1, 2, 3, 4), defaut=1, texte="gauche", colonnes=1,
       style_texte="lisere", ratio=0.48),
    _m(id="image-gauche-texte", libelle="Image à gauche + texte", famille="image-texte",
       description="Capture légendée à gauche, texte à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="droite", colonnes=1,
       ratio=0.45, legendes=True),
    _m(id="texte-image-droite", libelle="Texte + image à droite", famille="image-texte",
       description="Texte à gauche, capture légendée à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="gauche", colonnes=1,
       ratio=0.45, legendes=True),
    _m(id="image-etroite-texte", libelle="Image étroite + texte", famille="image-texte",
       description="Capture de mobile ou de fenêtre étroite, texte à liseré.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="droite", colonnes=1,
       style_texte="lisere", ratio=0.3),
    _m(id="texte-image-etroite", libelle="Texte + image étroite", famille="image-texte",
       description="Texte à liseré, capture étroite à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="gauche", colonnes=1,
       style_texte="lisere", ratio=0.3),
    _m(id="image-large-texte", libelle="Image large + texte", famille="image-texte",
       description="Capture large (barre d'outils, bandeau), texte à liseré.",
       hauteurs=(1, 2, 3), defaut=1, texte="droite", colonnes=1,
       style_texte="lisere", ratio=0.62),
    _m(id="image-cadres", libelle="Image + textes encadrés", famille="image-texte",
       description="Capture à gauche, consignes dans des cadres à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="droite", colonnes=1,
       style_texte="cadre", ratio=0.5),
    _m(id="image-items", libelle="Image + liste légendée", famille="image-texte",
       description="Capture à gauche, liste d'éléments (icône + texte) à droite.",
       hauteurs=(2, 3, 4), defaut=2, texte="droite", colonnes=1,
       style_texte="items", ratio=0.48),
    _m(id="image-dessus-texte", libelle="Image au-dessus du texte", famille="image-texte",
       description="Capture pleine largeur, texte en dessous.",
       hauteurs=(2, 3, 4), defaut=2, texte="dessous", colonnes=1,
       legendes=True, images_max=2),
    _m(id="texte-dessus-image", libelle="Texte au-dessus de l'image", famille="image-texte",
       description="Une phrase d'introduction, puis la capture pleine largeur.",
       hauteurs=(2, 3, 4), defaut=2, texte="dessus", colonnes=1,
       part_images=0.7, paragraphes_max=2),
    _m(id="etape-detaillee", libelle="Étape détaillée", famille="image-texte",
       description="Titre, grande capture, puis texte et encarts.",
       hauteurs=(2, 3, 4), defaut=3, texte="dessous", colonnes=1,
       legendes=True, part_images=0.68, images_max=2),
    # --- Plusieurs images + texte -----------------------------------------
    _m(id="deux-images-texte", libelle="Deux images + texte", famille="images-texte",
       description="Deux captures côte à côte, texte à liseré à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="droite", colonnes=2,
       style_texte="lisere", ratio=0.6),
    _m(id="texte-deux-images", libelle="Texte + deux images", famille="images-texte",
       description="Texte à liseré à gauche, deux captures à droite.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="gauche", colonnes=2,
       style_texte="lisere", ratio=0.6),
    _m(id="deux-images-empilees-texte", libelle="Deux images empilées + texte",
       famille="images-texte",
       description="Deux étapes d'écran l'une sous l'autre, texte à droite.",
       hauteurs=(2, 3, 4), defaut=2, texte="droite", colonnes=1, lignes=2,
       style_texte="lisere", ratio=0.55),
    _m(id="grille-texte", libelle="Grille 2×2 + texte", famille="images-texte",
       description="Quatre captures en grille, texte à liseré à droite.",
       hauteurs=(2, 3, 4), defaut=2, texte="droite", colonnes=2, lignes=2,
       style_texte="lisere", ratio=0.55),
    _m(id="grille-cadres", libelle="Grille 2×2 + textes encadrés", famille="images-texte",
       description="Quatre captures en grille, consignes encadrées à droite.",
       hauteurs=(2, 3, 4), defaut=3, texte="droite", colonnes=2, lignes=2,
       style_texte="cadre", ratio=0.55),
    _m(id="image-texte-image", libelle="Image + texte + image", famille="images-texte",
       description="Avant / après : une capture de chaque côté du texte.",
       hauteurs=(1, 2, 3), defaut=1, texte="milieu", colonnes=2,
       style_texte="lisere", ratio=0.33),
    _m(id="deux-images-texte-dessous", libelle="Deux images, texte dessous",
       famille="images-texte",
       description="Deux captures légendées côte à côte, texte en dessous.",
       hauteurs=(2, 3, 4), defaut=2, texte="dessous", colonnes=2, legendes=True),
    _m(id="trois-images-texte", libelle="Trois images, texte dessous",
       famille="images-texte",
       description="Trois captures légendées, texte en dessous.",
       hauteurs=(2, 3, 4), defaut=2, texte="dessous", colonnes=3, legendes=True),
    # --- Images seules ----------------------------------------------------
    _m(id="image-pleine-largeur", libelle="Image pleine largeur", famille="galerie",
       description="Une capture sur toute la largeur, légendée.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="aucun", colonnes=1, legendes=True),
    _m(id="deux-images", libelle="Deux images légendées", famille="galerie",
       description="Deux captures côte à côte, chacune légendée.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="aucun", colonnes=2, legendes=True),
    _m(id="triple-image", libelle="Trois images légendées", famille="galerie",
       description="Trois captures côte à côte, chacune légendée.",
       hauteurs=(1, 2, 3, 4), defaut=2, texte="aucun", colonnes=3, legendes=True),
    _m(id="quatre-images", libelle="Quatre images légendées", famille="galerie",
       description="Quatre captures côte à côte (écrans de mobile).",
       hauteurs=(1, 2, 3), defaut=2, texte="aucun", colonnes=4, legendes=True),
    _m(id="deux-images-empilees", libelle="Deux images empilées", famille="galerie",
       description="Deux captures pleine largeur, l'une sous l'autre.",
       hauteurs=(2, 3, 4), defaut=3, texte="aucun", colonnes=1, lignes=2, legendes=True),
    _m(id="grille-2x2", libelle="Grille 2×2", famille="galerie",
       description="Quatre captures légendées en grille.",
       hauteurs=(2, 3, 4), defaut=3, texte="aucun", colonnes=2, lignes=2, legendes=True),
    _m(id="grille-3x2", libelle="Grille 3×2", famille="galerie",
       description="Six captures légendées en grille.",
       hauteurs=(2, 3, 4), defaut=3, texte="aucun", colonnes=3, lignes=2, legendes=True),
]

MODELES_PAR_ID: dict[str, Modele] = {m.id: m for m in MODELES}


def modele(layout_id: str) -> Modele:
    try:
        return MODELES_PAR_ID[layout_id]
    except KeyError:
        raise ValueError(
            f"Modèle de section inconnu : '{layout_id}'. Modèles : {sorted(MODELES_PAR_ID)}"
        ) from None


# ---------------------------------------------------------------------------
# Géométrie
# ---------------------------------------------------------------------------

PT_EN_MM = 25.4 / 72
LARGEUR_A4_MM = 210
HAUTEUR_A4_MM = 297


@dataclass(frozen=True)
class Geometrie:
    """Mesures en mm dérivées de la charte (marges, tailles de police).

    Les réserves (titre, légende, encart) sont des hauteurs *fixes* : un titre
    qui passerait sur deux lignes, ou une légende de trois lignes, est rogné
    plutôt que de pousser la mise en page — même règle que pour les sections.
    """

    marge_mm: float
    titre_mm: float
    legende_mm: float
    encart_mm: float
    pad_haut_mm: float = 2.0
    pad_bas_mm: float = 5.0  # marge de sécurité : les sections ne se touchent jamais
    gouttiere_mm: float = 6.0  # entre la zone images et la zone texte
    espace_images_mm: float = 4.0  # entre deux images
    media_min_mm: float = 8.0

    @classmethod
    def depuis_charte(cls, charte) -> "Geometrie":
        p = charte.polices
        interligne = charte.espacements.interligne
        titre = p.titre_2.taille_pt * PT_EN_MM * 1.25 + 3.5
        legende = p.legende.taille_pt * PT_EN_MM * 1.3 * 2 + 2.5
        encart = p.corps.taille_pt * PT_EN_MM * interligne * 2 + 6 + 3
        return cls(
            marge_mm=charte.espacements.marge_mm,
            titre_mm=round(titre, 2),
            legende_mm=round(legende, 2),
            encart_mm=round(encart, 2),
        )

    @property
    def unite_mm(self) -> float:
        return (HAUTEUR_A4_MM - 2 * self.marge_mm) / 4

    @property
    def largeur_mm(self) -> float:
        return LARGEUR_A4_MM - 2 * self.marge_mm

    def section_mm(self, hauteur: int) -> float:
        return hauteur * self.unite_mm

    def corps_mm(self, hauteur: int, avec_titre: bool) -> float:
        """Hauteur disponible sous le titre, padding de sécurité déduit."""
        return (
            self.section_mm(hauteur)
            - self.pad_haut_mm
            - self.pad_bas_mm
            - (self.titre_mm if avec_titre else 0)
        )

    def zone_images_mm(
        self, m: Modele, hauteur: int, avec_titre: bool, nb_encarts: int
    ) -> float:
        """Hauteur de la zone images, selon la place du texte."""
        corps = self.corps_mm(hauteur, avec_titre)
        if m.texte in ("dessous", "dessus"):
            # Les encarts suivent le texte : ils prennent sur la part des images
            # plutôt que de repousser le texte hors de la section.
            return max(corps * m.part_images - nb_encarts * self.encart_mm, corps * 0.3)
        if m.texte == "aucun":
            # Pas de colonne texte : les encarts vont sous les images.
            return corps - nb_encarts * self.encart_mm
        return corps

    def media_mm(self, m: Modele, zone_mm: float, lignes: int) -> float:
        """Hauteur d'une boîte image (hors légende) dans une zone donnée."""
        legende = self.legende_mm if m.legendes else 0
        h = (zone_mm - (lignes - 1) * self.espace_images_mm) / lignes - legende
        return max(self.media_min_mm, round(h, 2))


def lignes_effectives(m: Modele, nb_images: int) -> int:
    """Nombre de lignes de la grille : celles du modèle, plus ce qu'il faut
    pour ne perdre aucune image fournie au-delà des emplacements prévus."""
    if not m.a_images:
        return 0
    return max(m.lignes, -(-nb_images // m.colonnes))
