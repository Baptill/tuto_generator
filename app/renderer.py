"""Moteur de rendu — content.yaml + template.docx + charte.yaml → article.docx.

Voir CLAUDE.md §3 (sections modulaires, styles nommés) et §4 (modèle de
données). Règle d'or : ce module lit `content.yaml`, jamais l'inverse.
"""

from __future__ import annotations

from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Mm, RGBColor

_ALIGNEMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}
from docxtpl import DocxTemplate

from app.layouts import build_section_subdoc
from app.pagination import paginate
from app.schemas import Article, Charte, TemplateConfig

STYLE_TITRE_1 = "Titre 1"
STYLE_TITRE_2 = "Titre 2"
STYLE_CORPS = "Corps"
STYLE_LEGENDE = "Legende"


class RenderError(Exception):
    pass


def _build_page_break_subdoc(tpl: DocxTemplate):
    subdoc = tpl.new_subdoc()
    run = subdoc.add_paragraph().add_run()
    run.add_break(WD_BREAK.PAGE)
    return subdoc


def _apply_style_typo(style, stylo, couleur_fallback: RGBColor) -> None:
    """Applique un StyleTypo de la charte à un style nommé Word."""
    from docx.shared import Pt

    font = style.font
    font.name = stylo.famille
    font.size = Pt(stylo.taille_pt)
    font.bold = stylo.gras
    font.italic = stylo.italique
    font.underline = stylo.souligne
    couleur_hex = (stylo.couleur or "").lstrip("#").upper()
    font.color.rgb = RGBColor.from_string(couleur_hex) if couleur_hex else couleur_fallback
    style.paragraph_format.alignment = _ALIGNEMENTS[stylo.text_alignement]


def _apply_charte(tpl: DocxTemplate, charte: Charte) -> None:
    """Applique toutes les propriétés typographiques et d'espacement de la
    charte aux styles nommés du document rendu.

    Les couleurs sémantiques des encadrés (astuce/attention/info) restent
    fixes dans le template : elles portent un sens indépendant de la marque.
    """
    document = tpl.docx
    styles = document.styles
    color_primaire = RGBColor.from_string(charte.couleurs.primaire.lstrip("#").upper())
    color_texte = RGBColor.from_string(charte.couleurs.texte.lstrip("#").upper())

    style_names = {s.name for s in styles}
    p = charte.polices

    if STYLE_TITRE_1 in style_names:
        _apply_style_typo(styles[STYLE_TITRE_1], p.titre_1, color_primaire)

    if STYLE_TITRE_2 in style_names:
        _apply_style_typo(styles[STYLE_TITRE_2], p.titre_2, color_primaire)

    if STYLE_CORPS in style_names:
        _apply_style_typo(styles[STYLE_CORPS], p.corps, color_texte)
        styles[STYLE_CORPS].paragraph_format.line_spacing = (
            charte.espacements.interligne
        )

    if STYLE_LEGENDE in style_names:
        _apply_style_typo(styles[STYLE_LEGENDE], p.legende, color_texte)

    # "Normal" : base de tout paragraphe sans style explicite (cellules de
    # tableau, etc.) — on aligne sa famille sur le corps.
    if "Normal" in style_names:
        styles["Normal"].font.name = p.corps.famille

    if "Prerequis Label" in style_names:
        _apply_style_typo(styles["Prerequis Label"], p.prerequis_label, color_texte)

    if "Prerequis Item" in style_names:
        _apply_style_typo(styles["Prerequis Item"], p.prerequis_item, color_texte)

    for section in document.sections:
        marge = Mm(charte.espacements.marge_mm)
        section.left_margin = marge
        section.right_margin = marge
        section.top_margin = marge
        section.bottom_margin = marge


def render_article(
    article: Article,
    config: TemplateConfig,
    charte: Charte,
    template_path: Path,
    article_dir: Path,
    output_path: Path,
) -> Path:
    """Rend `article` avec `template_path` + `charte`, écrit le docx dans
    `output_path`. `article_dir` est le dossier contenant `assets/` (les
    chemins d'image du content.yaml sont relatifs à ce dossier).
    """
    tpl = DocxTemplate(str(template_path))

    pages = paginate(article.sections)
    elements = []
    for i, page_sections in enumerate(pages):
        if i > 0:
            elements.append(_build_page_break_subdoc(tpl))
        for section in page_sections:
            elements.append(
                build_section_subdoc(
                    tpl, section, article_dir, config.image.largeur_mm_defaut
                )
            )

    context = {"article": article, "elements": elements}
    tpl.render(context)

    _apply_charte(tpl, charte)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tpl.save(str(output_path))
    return output_path
