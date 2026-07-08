"""Génère les templates Word pilotes `tuto-release` et `blog-standard`.

Voir CLAUDE.md, Étape 1, Lot 1.B « Templates pilotes » et §6 « Guide
d'authoring d'un template ». Ce script joue le rôle du designer qui
construirait le .docx dans Word : styles nommés, balises Jinja, pas de
couleur en dur (les couleurs de titres/corps sont injectées à chaque build
depuis charte.yaml — voir app/renderer.py::_apply_charte).

Usage : python -m scripts.build_templates
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from app import storage
from app.schemas import Charte, StyleTypo

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault-articles"

_ALIGNEMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

# Couleurs sémantiques des encadrés : fixes, indépendantes de la charte de
# marque (voir app/renderer.py::_apply_charte pour la justification).
ENCADRE_FILLS = {
    "Encadre Astuce": "E8F5E9",  # vert clair
    "Encadre Attention": "FDECEA",  # rouge/orangé clair
    "Encadre Info": "E8F0FE",  # bleu clair
}
ENCADRE_BORDER_COLORS = {
    "Encadre Astuce": "2E7D32",
    "Encadre Attention": "C62828",
    "Encadre Info": "1565C0",
}


def _set_shading(paragraph_format_element, fill_hex: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    paragraph_format_element.append(shd)


def _set_left_border(paragraph_format_element, color_hex: str) -> None:
    pBdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "4")
    left.set(qn("w:color"), color_hex)
    pBdr.append(left)
    paragraph_format_element.append(pBdr)


def _add_style(doc: Document, name: str, base: str = "Normal") -> object:
    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles[base]
    return style


def _apply_stylo(style, stylo: StyleTypo) -> None:
    """Applique un StyleTypo de la charte à un style nommé Word."""
    style.font.name = stylo.famille
    style.font.size = Pt(stylo.taille_pt)
    style.font.bold = stylo.gras
    style.font.italic = stylo.italique
    style.font.underline = stylo.souligne
    style.paragraph_format.alignment = _ALIGNEMENTS[stylo.text_alignement]


def _build_named_styles(doc: Document, charte: Charte) -> None:
    p = charte.polices

    titre1 = _add_style(doc, "Titre 1")
    _apply_stylo(titre1, p.titre_1)
    titre1.paragraph_format.space_after = Pt(12)

    titre2 = _add_style(doc, "Titre 2")
    _apply_stylo(titre2, p.titre_2)
    titre2.paragraph_format.space_before = Pt(16)
    titre2.paragraph_format.space_after = Pt(6)

    corps = _add_style(doc, "Corps")
    _apply_stylo(corps, p.corps)
    corps.paragraph_format.space_after = Pt(8)

    prerequis_label = _add_style(doc, "Prerequis Label")
    _apply_stylo(prerequis_label, p.prerequis_label)
    prerequis_label.paragraph_format.space_before = Pt(12)
    prerequis_label.paragraph_format.space_after = Pt(4)

    prerequis_item = _add_style(doc, "Prerequis Item")
    _apply_stylo(prerequis_item, p.prerequis_item)
    prerequis_item.paragraph_format.left_indent = Pt(12)
    prerequis_item.paragraph_format.space_after = Pt(2)

    legende = _add_style(doc, "Legende")
    _apply_stylo(legende, p.legende)
    legende.paragraph_format.space_after = Pt(10)

    for name, fill in ENCADRE_FILLS.items():
        style = _add_style(doc, name)
        style.font.size = Pt(11)
        pPr = style.element.get_or_add_pPr()
        _set_shading(pPr, fill)
        _set_left_border(pPr, ENCADRE_BORDER_COLORS[name])
        style.paragraph_format.space_before = Pt(6)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.left_indent = Pt(10)


def _build_body(doc: Document) -> None:
    doc.add_paragraph("{{ article.titre }}", style="Titre 1")
    # Bloc prérequis — affiché uniquement si la liste est non vide.
    # {%p if/for/endfor/endif %} : balises de contrôle Jinja qui suppriment
    # leur <w:p> englobant au rendu (nécessaire pour ne pas laisser de ligne
    # vide dans le document final).
    doc.add_paragraph("{%p if article.prerequis %}")
    doc.add_paragraph("Prérequis :", style="Prerequis Label")
    doc.add_paragraph("{%p for pr in article.prerequis %}")
    doc.add_paragraph("- {{ pr }}", style="Prerequis Item")
    doc.add_paragraph("{%p endfor %}")
    doc.add_paragraph("{%p endif %}")
    # Sections de l'article — `el` est un sous-document (XML brut) injecté
    # tel quel, d'où la variante `{{p el }}` qui supprime son <w:p> englobant.
    doc.add_paragraph("{%p for el in elements %}")
    doc.add_paragraph("{{p el }}")
    doc.add_paragraph("{%p endfor %}")


def build_template(template_id: str, libelle: str, charte: Charte) -> Path:
    doc = Document()
    _build_named_styles(doc, charte)
    _build_body(doc)

    out_dir = VAULT_ROOT / "templates" / template_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "template.docx"
    doc.save(str(out_path))
    return out_path


def main() -> None:
    charte = storage.load_charte()
    for template_id, libelle in [
        ("tuto-release", "Tutoriel de release"),
        ("blog-standard", "Article de blog"),
    ]:
        path = build_template(template_id, libelle, charte)
        print(f"{template_id} -> {path}")


if __name__ == "__main__":
    main()
