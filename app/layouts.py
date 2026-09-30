"""Rendu HTML d'une section, piloté par son modèle (voir app/modeles.py).

Un seul moteur pour tous les modèles : il lit la disposition déclarée (grille
d'images, position et style du texte) et la géométrie calculée depuis la
charte, puis produit la structure. Couleurs, bordures et typographie restent
dans le CSS du template ; ce module ne pose que des classes et des hauteurs.

Deux règles de mise en page :

- **une image ne se déforme jamais** : elle remplit sa boîte en largeur ou en
  hauteur (`object-fit: contain`), boîte dont la hauteur est calculée ici ;
  `padding_mm` agrandit la marge intérieure de la boîte pour réduire l'image ;
- **les multi-colonnes sont des tables** (`display: table`, espaceurs
  explicites entre cellules) : c'est ce que WeasyPrint rend le plus fidèlement.
"""
from __future__ import annotations

from html import escape

from app.markdown_lite import markdown_to_html
from app.modeles import Geometrie, Modele, lignes_effectives, modele
from app.schemas import BlocEncadre, BlocImage, BlocItem, BlocParagraphe, Section

_ENCADRE_ICONES = {"astuce": "✓", "attention": "!", "info": "i"}

# CSS structurel du moteur : ce dont dépend la géométrie calculée en Python
# (hauteurs, tables, gouttières, remplissage des images). Injecté au build,
# *avant* le CSS du template, qui reste libre de le surcharger pour le style.
# Les valeurs viennent des variables posées depuis la charte (renderer).
#
# Débordements : dans WeasyPrint, `overflow: hidden` ne suffit pas — un contenu
# qui dépasse sa boîte en bas de page y déclenche un saut de page au lieu d'être
# rogné (une légende de trois lignes partait seule sur une nouvelle page). D'où
# trois verrous : `continue: discard` sur la section, légendes limitées à deux
# lignes (`max-lines`), et pages à hauteur fixe à l'impression. `.sec-contenu`
# rogne *avant* le padding bas : la marge de sécurité entre sections reste
# vide quoi qu'il arrive. Les calques, eux, sont enfants directs de `.sec` : ils
# peuvent déborder de leur section (une flèche qui en traverse deux).
STRUCTURE_CSS = """
.sec{height:var(--unit-height);position:relative;continue:discard;
  padding:var(--sec-pad-haut) 0 var(--sec-pad-bas);}
.sec-contenu{height:100%;overflow:hidden;}
@media print{.page{height:calc(var(--unit-height)*4);overflow:hidden;}}
.sec.h2{height:calc(var(--unit-height)*2);}
.sec.h3{height:calc(var(--unit-height)*3);}
.sec.h4{height:calc(var(--unit-height)*4);}
.sec-contenu>h2.titre-2{height:var(--titre-h);margin:0;line-height:1.25;overflow:hidden;}
.sec a,.doc-header a{color:var(--couleur-lisere);text-decoration:underline;}
ol.corps,ul.corps{padding-left:6mm;margin:0 0 2.5mm;}
.corps li{margin-bottom:1mm;}
.s-colonnes-section{display:table;table-layout:fixed;width:100%;}
.s-col-images,.s-col-texte{display:table-cell;vertical-align:middle;}
.s-gouttiere{display:table-cell;width:var(--gouttiere);}
.s-rang{display:table;table-layout:fixed;width:100%;}
.s-cellule{display:table-cell;vertical-align:top;}
.s-espace{display:table-cell;width:var(--espace-images);}
.s-espace-rang{height:var(--espace-images);}
figure.image{margin:0;}
figure.image .media{width:100%;overflow:hidden;}
figure.image .media img{display:block;width:100%;height:100%;object-fit:contain;}
.avec-legendes figure.image .media img{object-position:50% 100%;}
figure.image .legende{height:var(--legende-h);margin:0;padding-top:2mm;overflow:hidden;
  max-lines:2;continue:discard;}
figure.image-libre{margin:0 0 3mm;}
figure.image-libre img{display:block;max-width:100%;max-height:60mm;margin:0 auto;object-fit:contain;}
@media screen{figure.image-vide .media{border:1.5px dashed #c6ccd3;background:#f6f7f9;border-radius:1.5mm;}}
.texte-dessous .s-zone-texte{padding-top:3mm;}
.texte-dessus .s-zone-texte{padding-bottom:3mm;}
.s-lisere{display:table;}
.s-lisere-barre{display:table-cell;width:4px;background:var(--couleur-lisere);border-radius:999px;}
.s-lisere-texte{display:table-cell;vertical-align:middle;padding-left:5mm;}
.s-cadre{border:1.5px solid var(--couleur-lisere);border-radius:2mm;padding:2.5mm 3.5mm;margin:0 0 3mm;}
.s-colonnes{columns:2;column-gap:8mm;}
.s-item{display:table;width:100%;margin:0 0 3mm;}
.s-item-icone{display:table-cell;width:10mm;vertical-align:middle;padding-right:3mm;}
.s-item-icone img{display:block;width:7mm;height:7mm;object-fit:contain;}
.s-item-barre{display:table-cell;width:3px;background:var(--couleur-lisere);border-radius:999px;}
.s-item-texte{display:table-cell;vertical-align:middle;padding-left:4mm;}
.s-encarts{margin-top:3mm;}
.s-cadre>:last-child,.s-item-texte>:last-child,.s-lisere-texte>:last-child,
.encadre-corps>:last-child{margin-bottom:0;}
.encadre{display:table;width:100%;border:1px solid;border-radius:2mm;margin:0 0 3mm;}
.encadre-icone{display:table-cell;width:11mm;vertical-align:middle;padding-left:3.5mm;}
.encadre-icone span{display:block;width:5.5mm;height:5.5mm;border-radius:999px;color:#fff;
  text-align:center;font-weight:700;font-size:8.5pt;line-height:5.5mm;}
.encadre-corps{display:table-cell;vertical-align:middle;padding:3mm 4mm 3mm 1mm;}
.encadre .encadre-texte{margin:0 0 1.5mm;}
.encadre>p.encadre-texte{display:table-cell;padding:3mm 4mm;}
"""


def _mm(v: float) -> str:
    return f"{v:.2f}mm"


# ---------------------------------------------------------------------------
# Blocs
# ---------------------------------------------------------------------------

def _titre_html(titre: str | None) -> str:
    return f'<h2 class="titre-2">{escape(titre)}</h2>' if titre else ""


def encadre_html(bloc: BlocEncadre) -> str:
    icone = _ENCADRE_ICONES.get(bloc.style, "i")
    texte = markdown_to_html(bloc.texte, paragraph_class="encadre-texte")
    return (
        f'<div class="encadre encadre-{bloc.style}">'
        f'<div class="encadre-icone"><span>{icone}</span></div>'
        f'<div class="encadre-corps">{texte}</div></div>'
    )


def _item_html(bloc: BlocItem, colonne_icone: bool) -> str:
    """`colonne_icone` : si un élément de la liste a une icône, tous gardent la
    colonne (vide au besoin) pour que les textes restent alignés."""
    if bloc.icone:
        icone = f'<div class="s-item-icone"><img src="{escape(bloc.icone, quote=True)}" alt=""></div>'
    else:
        icone = '<div class="s-item-icone"></div>' if colonne_icone else ""
    return (
        f'<div class="s-item">{icone}<div class="s-item-barre"></div>'
        f'<div class="s-item-texte">{markdown_to_html(bloc.texte)}</div></div>'
    )


def _image_libre_html(bloc: BlocImage) -> str:
    """Image hors grille (content.yaml écrit à la main, image dans un modèle
    texte) : taille naturelle bornée par le CSS, jamais déformée."""
    legende = (
        f'<figcaption class="legende">{escape(bloc.legende)}</figcaption>' if bloc.legende else ""
    )
    return (
        f'<figure class="image image-libre"><img src="{escape(bloc.fichier, quote=True)}" alt="">'
        f"{legende}</figure>"
    )


def _texte_html(m: Modele, blocs: list, avec_encarts_dans_le_fil: bool = False) -> str:
    """Colonne ou zone de texte, selon le style du modèle.

    `blocs` contient paragraphes et items (plus encarts et images libres pour
    les modèles « texte seul », rendus dans l'ordre du content.yaml).
    """
    morceaux: list[str] = []
    colonne_icone = any(isinstance(b, BlocItem) and b.icone for b in blocs)
    for b in blocs:
        if isinstance(b, BlocParagraphe):
            html = markdown_to_html(b.texte)
            morceaux.append(f'<div class="s-cadre">{html}</div>' if m.style_texte == "cadre" else html)
        elif isinstance(b, BlocItem):
            morceaux.append(_item_html(b, colonne_icone))
        elif isinstance(b, BlocEncadre) and avec_encarts_dans_le_fil:
            morceaux.append(encadre_html(b))
        elif isinstance(b, BlocImage) and avec_encarts_dans_le_fil:
            morceaux.append(_image_libre_html(b))
    contenu = "".join(morceaux)
    if not contenu:
        return ""
    if m.style_texte == "lisere":
        return (
            '<div class="s-lisere"><div class="s-lisere-barre"></div>'
            f'<div class="s-lisere-texte">{contenu}</div></div>'
        )
    if m.style_texte == "colonnes":
        return f'<div class="s-colonnes">{contenu}</div>'
    return contenu


def _encarts_html(encarts: list[BlocEncadre]) -> str:
    if not encarts:
        return ""
    return '<div class="s-encarts">' + "".join(encadre_html(e) for e in encarts) + "</div>"


# ---------------------------------------------------------------------------
# Grille d'images
# ---------------------------------------------------------------------------

def _figure_html(bloc: BlocImage | None, media_mm: float, legendes: bool) -> str:
    legende = ""
    if legendes:
        texte = escape(bloc.legende) if bloc and bloc.legende else ""
        legende = f'<figcaption class="legende">{texte}</figcaption>'
    if bloc is None:
        # Emplacement prévu par le modèle mais pas encore rempli : la cellule
        # garde sa place ; le pointillé n'apparaît qu'à l'écran (jamais au PDF).
        return (
            f'<figure class="image image-vide"><div class="media" style="height:{_mm(media_mm)}">'
            f"</div>{legende}</figure>"
        )
    style = [f"height:{_mm(media_mm)}"]
    if bloc.padding_mm:
        style.append(f"padding:{_mm(bloc.padding_mm)}")
    if bloc.largeur_mm:
        style.append(f"max-width:{bloc.largeur_mm}mm;margin:0 auto")
    return (
        f'<figure class="image"><div class="media" style="{";".join(style)}">'
        f'<img src="{escape(bloc.fichier, quote=True)}" alt=""></div>{legende}</figure>'
    )


def _grille_html(
    m: Modele, images: list[BlocImage], zone_mm: float, geom: Geometrie, colonnes: int
) -> str:
    """Grille `colonnes` × lignes, cellules de largeur égale, espacées."""
    if colonnes == m.colonnes:
        lignes = lignes_effectives(m, len(images))
    else:  # une moitié du modèle « milieu » : une image par ligne
        lignes = max(1, len(images))
    media = geom.media_mm(m, zone_mm, lignes)
    rangs: list[str] = []
    for r in range(lignes):
        cellules = []
        for c in range(colonnes):
            i = r * colonnes + c
            bloc = images[i] if i < len(images) else None
            cellules.append(f'<div class="s-cellule">{_figure_html(bloc, media, m.legendes)}</div>')
        rangs.append('<div class="s-rang">' + '<div class="s-espace"></div>'.join(cellules) + "</div>")
    classes = "s-grille avec-legendes" if m.legendes else "s-grille"
    return f'<div class="{classes}">' + '<div class="s-espace-rang"></div>'.join(rangs) + "</div>"


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

def _corps_html(section: Section, m: Modele, geom: Geometrie) -> str:
    images = [b for b in section.blocs if isinstance(b, BlocImage)]
    encarts = [b for b in section.blocs if isinstance(b, BlocEncadre)]
    textes = [b for b in section.blocs if isinstance(b, (BlocParagraphe, BlocItem))]
    h = section.hauteur
    avec_titre = bool(section.titre)
    corps = geom.corps_mm(h, avec_titre)

    if m.texte == "seul":
        # Les encarts (et d'éventuelles images) restent à leur place dans le fil.
        return _texte_html(m, section.blocs, avec_encarts_dans_le_fil=True)

    zone = geom.zone_images_mm(m, h, avec_titre, len(encarts))
    texte = _texte_html(m, textes) + _encarts_html(encarts)

    if m.texte == "aucun":
        return _grille_html(m, images, zone, geom, m.colonnes) + _encarts_html(encarts)

    if m.texte in ("dessous", "dessus"):
        grille = f'<div class="s-zone-images">{_grille_html(m, images, zone, geom, m.colonnes)}</div>'
        bloc_texte = f'<div class="s-zone-texte">{texte}</div>'
        return grille + bloc_texte if m.texte == "dessous" else bloc_texte + grille

    largeur = f"{m.ratio * 100:.1f}%"
    if m.texte == "milieu":
        gauche, droite = images[0::2], images[1::2]
        col_g = f'<div class="s-col-images" style="width:{largeur}">{_grille_html(m, gauche, corps, geom, 1)}</div>'
        col_d = f'<div class="s-col-images" style="width:{largeur}">{_grille_html(m, droite, corps, geom, 1)}</div>'
        col_t = f'<div class="s-col-texte">{texte}</div>'
        cols = col_g + '<div class="s-gouttiere"></div>' + col_t + '<div class="s-gouttiere"></div>' + col_d
    else:
        col_i = (
            f'<div class="s-col-images" style="width:{largeur}">'
            f"{_grille_html(m, images, corps, geom, m.colonnes)}</div>"
        )
        col_t = f'<div class="s-col-texte">{texte}</div>'
        paire = (col_i, col_t) if m.texte == "droite" else (col_t, col_i)
        cols = paire[0] + '<div class="s-gouttiere"></div>' + paire[1]
    return f'<div class="s-colonnes-section" style="height:{_mm(corps)}">{cols}</div>'


def render_section_html(section: Section, geom: Geometrie, calques_html: str = "") -> str:
    """`<section id="…" class="sec h{n} {modèle} texte-{position}">`.

    L'`id` (celui du content.yaml) sert d'ancre stable aux calques de retouche :
    un calque ancré à `sec-2` suit sa section même si un changement de charte
    la fait basculer sur une autre page (voir CLAUDE.md §3). Les calques sont
    ses derniers enfants : hors flux, ils n'affectent pas sa hauteur.
    """
    m = modele(section.layout)
    classes = f"sec h{section.hauteur} {m.id} texte-{m.texte} style-{m.style_texte}"
    return (
        f'<section id="{escape(section.id, quote=True)}" class="{classes}">'
        f'<div class="sec-contenu">{_titre_html(section.titre)}{_corps_html(section, m, geom)}</div>'
        f"{calques_html}</section>"
    )


def images_de(section: Section) -> list[str]:
    """Fichiers référencés par une section (images et icônes d'items)."""
    fichiers = [b.fichier for b in section.blocs if isinstance(b, BlocImage)]
    fichiers += [b.icone for b in section.blocs if isinstance(b, BlocItem) and b.icone]
    return fichiers

