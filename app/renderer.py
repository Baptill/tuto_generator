"""Moteur de rendu — content.yaml + template.html + charte.yaml → article.html.

Voir CLAUDE.md §3 (moteur HTML/CSS, sections modulaires) et §4 (modèle de
données). Règle d'or : ce module lit `content.yaml`, jamais l'inverse.

Le HTML produit est à la fois l'artefact éditable (dans le navigateur) et la
source de la conversion PDF (WeasyPrint). La charte est injectée sous forme de
variables CSS + règles typographiques ; le template porte le design-system
(layout des blocs), jamais de couleur codée en dur.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from jinja2 import Template

from app.layouts import render_section_html
from app.pagination import paginate
from app.schemas import Article, Charte, StyleTypo, TemplateConfig

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault-articles"
CHARTE_FONTS_DIR = VAULT_ROOT / "charte" / "fonts"

A4_HEIGHT_MM = 297

# Correspondance police → fichiers pour le @font-face (famille « Inter »).
_FONT_FACES = [
    ("Inter", "normal", "400", "Inter-Regular.ttf"),
    ("Inter", "normal", "600", "Inter-SemiBold.ttf"),
    ("Inter", "normal", "700", "Inter-Bold.ttf"),
]


class RenderError(Exception):
    pass


def _font_face_css() -> str:
    faces = []
    for famille, style, weight, fichier in _FONT_FACES:
        path = CHARTE_FONTS_DIR / fichier
        if path.is_file():
            faces.append(
                f"@font-face{{font-family:'{famille}';font-style:{style};"
                f"font-weight:{weight};src:url('{path.as_uri()}');}}"
            )
    return "".join(faces)


def _typo_rules(selector: str, stylo: StyleTypo, couleur_fallback: str) -> str:
    """Traduit un StyleTypo de la charte en règle CSS pour un style nommé."""
    couleur = stylo.couleur or couleur_fallback
    props = [
        f"font-family:'{stylo.famille}',sans-serif",
        f"font-size:{stylo.taille_pt}pt",
        f"font-weight:{'700' if stylo.gras else '400'}",
        f"font-style:{'italic' if stylo.italique else 'normal'}",
        f"text-decoration:{'underline' if stylo.souligne else 'none'}",
        f"color:{couleur}",
        f"text-align:{stylo.text_alignement}",
    ]
    return f"{selector}{{{';'.join(props)};}}"


def _charte_css(charte: Charte) -> str:
    """Génère le bloc CSS injecté depuis la charte : @page, @font-face,
    variables `:root` et règles des styles nommés (typographie)."""
    c = charte.couleurs
    p = charte.polices
    marge = charte.espacements.marge_mm
    unit_mm = (A4_HEIGHT_MM - 2 * marge) / 4

    root_vars = (
        ":root{"
        f"--couleur-primaire:{c.primaire};"
        f"--couleur-secondaire:{c.secondaire};"
        f"--couleur-texte:{c.texte};"
        f"--couleur-fond:{c.fond};"
        f"--couleur-lisere:{c.lisere};"
        f"--interligne:{charte.espacements.interligne};"
        f"--marge:{marge}mm;"
        f"--unit-height:{unit_mm:.3f}mm;"
        "}"
    )

    typo = "".join([
        f"@page{{size:A4;margin:{marge}mm;}}",
        _typo_rules("h1.titre-1", p.titre_1, c.primaire),
        _typo_rules("h2.titre-2", p.titre_2, c.primaire),
        _typo_rules(".corps", p.corps, c.texte)
        .rstrip("}") + f"line-height:{charte.espacements.interligne};}}",
        _typo_rules(".legende", p.legende, c.texte),
        _typo_rules(".prerequis-label", p.prerequis_label, c.texte),
        _typo_rules(".prerequis-item", p.prerequis_item, c.texte),
    ])

    return _font_face_css() + root_vars + typo


def _header_html(article: Article, logo_uri: str | None) -> str:
    """En-tête du document (titre + résumé + prérequis), placé en tête de la
    première page. Occupe ~1 unité de hauteur (réservée par la pagination)."""
    parts = ['<header class="doc-header">']
    if logo_uri:
        parts.append(f'<img class="logo" src="{escape(logo_uri, quote=True)}" alt="">')
    parts.append(f'<h1 class="titre-1">{escape(article.titre)}</h1>')
    if article.resume:
        parts.append(f'<p class="resume">{escape(article.resume)}</p>')
    if article.prerequis:
        items = "".join(f'<li class="prerequis-item">{escape(p)}</li>' for p in article.prerequis)
        parts.append(
            '<div class="prerequis"><p class="prerequis-label">Prérequis</p>'
            f"<ul>{items}</ul></div>"
        )
    parts.append("</header>")
    return "".join(parts)


def _pages_html(
    article: Article, config: TemplateConfig, article_dir: Path, logo_uri: str | None
) -> str:
    """Assemble le HTML page par page selon la grille des 4 hauteurs. Chaque
    page est un `<div class="page">` : à l'écran une feuille A4 distincte, à
    l'impression une feuille physique (voir CSS du template)."""
    # Le bloc titre + prérequis occupe 1 unité de hauteur sur la première page.
    pages = paginate(article.sections, premiere_page_reservee=1)
    if not pages:
        pages = [[]]  # au moins la page d'en-tête même sans section
    largeur = config.image.largeur_mm_defaut
    out: list[str] = []
    for page_idx, page_sections in enumerate(pages):
        inner = _header_html(article, logo_uri) if page_idx == 0 else ""
        inner += "".join(render_section_html(s, article_dir, largeur) for s in page_sections)
        out.append(f'<div class="page">{inner}</div>')
    return "".join(out)


def render_article(
    article: Article,
    config: TemplateConfig,
    charte: Charte,
    template_path: Path,
    article_dir: Path,
    output_path: Path,
) -> Path:
    """Rend `article` avec `template_path` (HTML/Jinja) + `charte`, écrit le
    HTML dans `output_path`. Les chemins d'image du content.yaml sont relatifs
    à `article_dir` (résolus via <base href>)."""
    template = Template(template_path.read_text(encoding="utf-8"), autoescape=True)

    logo_path = VAULT_ROOT / "charte" / (charte.logo or "")
    logo_uri = logo_path.as_uri() if charte.logo and logo_path.is_file() else None

    html = template.render(
        article=article,
        charte_css=_charte_css(charte),
        base_href=article_dir.as_uri() + "/",
        pages_html=_pages_html(article, config, article_dir, logo_uri),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
