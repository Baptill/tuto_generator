"""Catalogue des layouts de section — rendu HTML (voir CLAUDE.md §3).

Chaque layout transforme une `Section` en fragment HTML. La mise en page fine
(colonnes, gap, liseré arrondi, centrage vertical) est portée par le CSS du
design-system défini dans le template, jamais par des valeurs codées ici : ce
module ne produit que la structure et les classes.

La grille des 4 hauteurs se traduit par une classe `h1`…`h4` sur la section ;
le CSS lui donne une hauteur minimale correspondante.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from app.markdown_lite import markdown_to_html
from app.schemas import BlocEncadre, BlocImage, BlocParagraphe, Section

_ENCADRE_CLASSES = {
    "astuce": "encadre encadre-astuce",
    "attention": "encadre encadre-attention",
    "info": "encadre encadre-info",
}


# ---------------------------------------------------------------------------
# Helpers de rendu de blocs
# ---------------------------------------------------------------------------

def _titre_html(titre: str | None) -> str:
    return f'<h2 class="titre-2">{escape(titre)}</h2>' if titre else ""


def _image_html(bloc: BlocImage) -> str:
    """<figure> avec l'image (src relatif à article_dir, résolu via base_url)
    et une légende optionnelle."""
    src = escape(bloc.fichier)
    largeur = f' style="width:{bloc.largeur_mm}mm"' if bloc.largeur_mm else ""
    legende = (
        f'<figcaption class="legende">{escape(bloc.legende)}</figcaption>'
        if bloc.legende
        else ""
    )
    return f'<figure class="image"><img src="{src}"{largeur} alt="">{legende}</figure>'


def _bloc_html(bloc) -> str:
    if isinstance(bloc, BlocParagraphe):
        return markdown_to_html(bloc.texte, paragraph_class="corps")
    if isinstance(bloc, BlocEncadre):
        cls = _ENCADRE_CLASSES[bloc.style]
        inner = markdown_to_html(bloc.texte, paragraph_class="encadre-texte")
        return f'<div class="{cls}">{inner}</div>'
    if isinstance(bloc, BlocImage):
        return _image_html(bloc)
    return ""


def _texte_blocs_html(blocs) -> str:
    return "".join(_bloc_html(b) for b in blocs)


def _split_images(section: Section) -> tuple[list[BlocImage], list]:
    images = [b for b in section.blocs if isinstance(b, BlocImage)]
    autres = [b for b in section.blocs if not isinstance(b, BlocImage)]
    return images, autres


def _section_wrapper(section: Section, layout_class: str, inner: str) -> str:
    """Enveloppe le contenu dans <section id="…" class="sec h{n} {layout}">.

    L'`id` (celui du content.yaml) sert d'ancre stable aux calques de retouche :
    un calque ancré à `sec-2` suit sa section même si un changement de charte
    la fait basculer sur une autre page (voir CLAUDE.md §3).
    """
    return (
        f'<section id="{escape(section.id, quote=True)}" '
        f'class="sec h{section.hauteur} {layout_class}">{inner}</section>'
    )


# ---------------------------------------------------------------------------
# Layouts h=1
# ---------------------------------------------------------------------------

def layout_texte_seul(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=1 — titre optionnel puis blocs empilés verticalement."""
    inner = _titre_html(section.titre) + _texte_blocs_html(section.blocs)
    return _section_wrapper(section, "texte-seul", inner)


def layout_etape_compacte(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=1 — image (≤50%) | liseré arrondi | texte centré verticalement.

    Structure : la colonne texte et son liseré sont regroupés dans `.ec-textwrap`,
    dont la hauteur suit le texte (pas l'image) ; le liseré (`.ec-lisere`)
    s'étire à cette hauteur → pill de la hauteur du texte, coins 100% arrondis
    (CSS). Le gap image/liseré et le centrage vertical sont gérés en CSS.
    """
    images, autres = _split_images(section)
    image_html = _image_html(images[0]) if images else ""
    texte_html = _texte_blocs_html(autres)
    inner = (
        _titre_html(section.titre)
        + '<div class="ec-row">'
        + f'<div class="ec-image">{image_html}</div>'
        + '<div class="ec-textwrap"><div class="ec-textinner">'
        + '<div class="ec-lisere"></div>'
        + f'<div class="ec-text">{texte_html}</div>'
        + "</div></div>"
        + "</div>"
    )
    return _section_wrapper(section, "etape-compacte", inner)


# ---------------------------------------------------------------------------
# Layouts h=2
# ---------------------------------------------------------------------------

def _deux_colonnes(section: Section, layout_class: str, image_a_gauche: bool) -> str:
    images, autres = _split_images(section)
    image_html = f'<div class="col-image">{_image_html(images[0])}</div>' if images else ""
    texte_html = (
        f'<div class="col-texte">{_titre_html(section.titre)}{_texte_blocs_html(autres)}</div>'
    )
    cols = (image_html + texte_html) if image_a_gauche else (texte_html + image_html)
    inner = f'<div class="deux-colonnes">{cols}</div>'
    return _section_wrapper(section, layout_class, inner)


def layout_image_gauche_texte(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=2 — image à gauche, titre + texte à droite."""
    return _deux_colonnes(section, "image-gauche-texte", image_a_gauche=True)


def layout_texte_image_droite(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=2 — titre + texte à gauche, image à droite."""
    return _deux_colonnes(section, "texte-image-droite", image_a_gauche=False)


def layout_image_dessus_texte(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=2 — titre optionnel, image(s) pleine largeur, texte en dessous."""
    images, autres = _split_images(section)
    inner = (
        _titre_html(section.titre)
        + "".join(_image_html(img) for img in images)
        + _texte_blocs_html(autres)
    )
    return _section_wrapper(section, "image-dessus-texte", inner)


def layout_triple_image(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=2 — titre optionnel + jusqu'à 3 images côte à côte avec légendes.

    largeur_mm des blocs ignoré ici : la grille impose une largeur égale à
    chaque cellule (width: 100% via CSS), indépendamment de la taille native
    des images.
    """
    images, _ = _split_images(section)
    images = images[:3]
    cells = []
    for img in images:
        src = escape(img.fichier)
        legende = (
            f'<figcaption class="legende">{escape(img.legende)}</figcaption>'
            if img.legende else ""
        )
        fig = f'<figure class="image"><img src="{src}" alt="">{legende}</figure>'
        cells.append(f'<div class="ti-cell">{fig}</div>')
    inner = _titre_html(section.titre) + f'<div class="triple-image-row">{"".join(cells)}</div>'
    return _section_wrapper(section, "triple-image", inner)


# ---------------------------------------------------------------------------
# Layouts h=3 et h=4
# ---------------------------------------------------------------------------

def layout_etape_detaillee(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=3 — titre optionnel + image(s) pleine largeur + texte/encadrés."""
    images, autres = _split_images(section)
    inner = (
        _titre_html(section.titre)
        + "".join(_image_html(img) for img in images)
        + _texte_blocs_html(autres)
    )
    return _section_wrapper(section, "etape-detaillee", inner)


def layout_pleine_page(section: Section, article_dir: Path, largeur_defaut: int) -> str:
    """h=4 — titre optionnel + tous les blocs. Occupe une page entière."""
    inner = _titre_html(section.titre) + _texte_blocs_html(section.blocs)
    return _section_wrapper(section, "pleine-page", inner)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

LAYOUTS = {
    "texte-seul":         layout_texte_seul,
    "etape-compacte":     layout_etape_compacte,
    "image-gauche-texte": layout_image_gauche_texte,
    "texte-image-droite": layout_texte_image_droite,
    "image-dessus-texte": layout_image_dessus_texte,
    "triple-image":       layout_triple_image,
    "etape-detaillee":    layout_etape_detaillee,
    "pleine-page":        layout_pleine_page,
}


def render_section_html(
    section: Section,
    article_dir: Path,
    largeur_defaut: int,
    extra_classes: str = "",
    calques_html: str = "",
) -> str:
    fn = LAYOUTS.get(section.layout)
    if fn is None:
        raise ValueError(f"Layout inconnu : '{section.layout}'. Valeurs : {list(LAYOUTS)}")
    html = fn(section, article_dir, largeur_defaut)
    if extra_classes:
        html = html.replace('class="sec ', f'class="sec {extra_classes} ', 1)
    if calques_html:
        # Les calques ancrés à cette section sont ses derniers enfants : hors
        # flux (position:absolute), ils n'affectent pas sa hauteur.
        html = html[: -len("</section>")] + calques_html + "</section>"
    return html
