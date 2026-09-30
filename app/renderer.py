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

from app.editeur import editeur_html
from app.layouts import STRUCTURE_CSS, render_section_html
from app.modeles import Geometrie
from app.pagination import paginate
from app.schemas import Article, Calque, Charte, Retouches, StyleTypo, TemplateConfig

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


# Style écran-seulement de l'aperçu du composeur : le zoom est piloté depuis le
# composeur (variable --apercu-zoom) plutôt que par une transformation de
# l'<iframe>, pour que la barre d'édition et la palette gardent leur taille
# native et restent à droite du volet (voir app/ui/composeur.js).
_APERCU_CSS = """
@media screen {
  html { background: #eceef1; }
  /* Dégage la barre d'édition (fixée en haut à droite) du haut de la 1re page. */
  body { padding-top: 40px; }
  .page { zoom: var(--apercu-zoom, 1); }
}
"""


def _font_face_css(charte_base: str | None = None) -> str:
    """`charte_base` sert l'aperçu du composeur : servi en http://, le
    navigateur refuse les `file://` du build. Par défaut (CLI, PDF), on garde
    les chemins absolus du disque — WeasyPrint n'a pas de serveur."""
    faces = []
    for famille, style, weight, fichier in _FONT_FACES:
        path = CHARTE_FONTS_DIR / fichier
        if path.is_file():
            src = f"{charte_base}fonts/{fichier}" if charte_base else path.as_uri()
            faces.append(
                f"@font-face{{font-family:'{famille}';font-style:{style};"
                f"font-weight:{weight};src:url('{src}');}}"
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


def _charte_css(charte: Charte, charte_base: str | None = None) -> str:
    """Génère le bloc CSS injecté depuis la charte : @page, @font-face,
    variables `:root` et règles des styles nommés (typographie)."""
    c = charte.couleurs
    p = charte.polices
    marge = charte.espacements.marge_mm
    unit_mm = (A4_HEIGHT_MM - 2 * marge) / 4
    g = Geometrie.depuis_charte(charte)

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
        # Géométrie des sections (app/modeles.py) : les mêmes valeurs servent au
        # calcul des hauteurs d'images côté Python et au CSS du template.
        f"--sec-pad-haut:{g.pad_haut_mm}mm;"
        f"--sec-pad-bas:{g.pad_bas_mm}mm;"
        f"--titre-h:{g.titre_mm}mm;"
        f"--legende-h:{g.legende_mm}mm;"
        f"--gouttiere:{g.gouttiere_mm}mm;"
        f"--espace-images:{g.espace_images_mm}mm;"
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

    # Le CSS structurel du moteur de sections voyage avec la charte : il en
    # consomme les variables et doit précéder le CSS du template.
    return _font_face_css(charte_base) + root_vars + typo + STRUCTURE_CSS


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


def _calque_html(calque: Calque) -> str:
    """Rend un calque de retouche. `calque.html` provient de l'éditeur : il est
    assaini à l'écriture de `retouches.yaml` (voir app/serveur.py), pas ici."""
    return (
        f'<div class="{escape(calque.classes, quote=True)}"'
        f' style="{escape(calque.style, quote=True)}"'
        f' data-texte="{"oui" if calque.texte else "non"}"'
        f' data-redim="{calque.redim}"'
        f' contenteditable="{"true" if calque.texte else "false"}">{calque.html}</div>'
    )


def _grouper_calques(retouches: Retouches) -> tuple[dict[str, str], dict[int, str]]:
    """Répartit les calques par ancre : par id de section, ou par index de page
    pour ceux posés hors section (en-tête, marge)."""
    par_section: dict[str, list[str]] = {}
    par_page: dict[int, list[str]] = {}
    for c in retouches.calques:
        html = _calque_html(c)
        if c.ancre_section:
            par_section.setdefault(c.ancre_section, []).append(html)
        else:
            par_page.setdefault(c.page, []).append(html)
    return (
        {k: "".join(v) for k, v in par_section.items()},
        {k: "".join(v) for k, v in par_page.items()},
    )


def _pages_html(
    article: Article,
    geometrie: Geometrie,
    logo_uri: str | None,
    retouches: Retouches,
) -> str:
    """Assemble le HTML page par page selon la grille des 4 hauteurs. Chaque
    page est un `<div class="page">` : à l'écran une feuille A4 distincte, à
    l'impression une feuille physique (voir CSS du template)."""
    # Le bloc titre + prérequis occupe 1 unité de hauteur sur la première page.
    pages = paginate(article.sections, premiere_page_reservee=1)
    if not pages:
        pages = [[]]  # au moins la page d'en-tête même sans section
    calques_section, calques_page = _grouper_calques(retouches)
    out: list[str] = []
    for page_idx, page_sections in enumerate(pages):
        inner = _header_html(article, logo_uri) if page_idx == 0 else ""
        inner += "".join(
            render_section_html(s, geometrie, calques_html=calques_section.pop(s.id, ""))
            for s in page_sections
        )
        inner += calques_page.get(page_idx, "")
        out.append(f'<div class="page">{inner}</div>')
    # Calques dont l'ancre a disparu (section supprimée du content.yaml) ou dont
    # la page n'existe plus : reversés sur la dernière page plutôt que perdus.
    orphelins = "".join(calques_section.values()) + "".join(
        html for idx, html in calques_page.items() if idx >= len(pages)
    )
    if orphelins:
        out[-1] = out[-1][: -len("</div>")] + orphelins + "</div>"
    return "".join(out)


def _editeur_et_apercu(
    article_id: str, avec_editeur: bool, api_url: str | None, apercu: bool
) -> str:
    """Fragment de fin de `<body>` : surface d'édition, plus le style d'aperçu
    quand le rendu est affiché dans le composeur. Ce style est ajouté ici plutôt
    que dans les templates pour qu'aucun template n'ait à connaître le
    composeur."""
    fragment = ""
    if avec_editeur:
        fragment += editeur_html(
            article_id=article_id,
            api_url=api_url,
            regenerer=bool(api_url),
            # Dans le composeur, c'est « Enregistrer & générer » qui persiste
            # la source *et* les calques : pas de second bouton dans l'aperçu.
            avec_enregistrement=not api_url,
        )
    if apercu:
        fragment += f'\n<style id="apercu-css">{_APERCU_CSS}</style>'
    return fragment


def render_article(
    article: Article,
    config: TemplateConfig,
    charte: Charte,
    template_path: Path,
    article_dir: Path,
    output_path: Path | None,
    retouches: Retouches | None = None,
    base_href: str | None = None,
    charte_base: str | None = None,
    avec_editeur: bool = True,
    editeur_api_url: str | None = None,
    apercu: bool = False,
) -> str:
    """Rend `article` avec `template_path` (HTML/Jinja) + `charte`, et écrit le
    HTML dans `output_path` (sauf si None). Retourne le HTML produit.

    Les chemins d'image du content.yaml sont relatifs à `article_dir` (résolus
    via <base href>). `base_href`/`charte_base`/`avec_editeur` ne servent qu'à
    l'aperçu du composeur (servi en http://, sans barre d'édition) ; le build
    de production garde les valeurs par défaut.
    """
    template = Template(template_path.read_text(encoding="utf-8"), autoescape=True)

    logo_path = VAULT_ROOT / "charte" / (charte.logo or "")
    if not (charte.logo and logo_path.is_file()):
        logo_uri = None
    elif charte_base:
        logo_uri = f"{charte_base}{charte.logo}"
    else:
        logo_uri = logo_path.as_uri()

    html = template.render(
        article=article,
        charte_css=_charte_css(charte, charte_base),
        base_href=base_href or (article_dir.as_uri() + "/"),
        pages_html=_pages_html(
            article, Geometrie.depuis_charte(charte), logo_uri, retouches or Retouches()
        ),
        editeur_html=_editeur_et_apercu(
            article_dir.name, avec_editeur, editeur_api_url, apercu
        ),
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    return html
