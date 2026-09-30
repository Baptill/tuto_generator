"""Rendu des sections (app/modeles.py + app/layouts.py).

Couvre les règles de mise en page des sections : images jamais déformées qui
remplissent leur boîte, padding d'image, marge de sécurité en bas de section,
gouttière entre images, liens cliquables, encarts disponibles partout — et,
surtout, qu'une section garde dans le PDF exactement le poids annoncé.
"""
from __future__ import annotations

import re

import pytest
from weasyprint import HTML

from app import storage
from app.layouts import STRUCTURE_CSS, render_section_html
from app.markdown_lite import markdown_to_html
from app.modeles import MODELES, MODELES_PAR_ID, Geometrie
from app.pagination import paginate
from app.renderer import render_article
from app.schemas import (
    Article,
    BlocEncadre,
    BlocImage,
    BlocItem,
    BlocParagraphe,
    Section,
)

EXEMPLE = "2026-07-exemple-tuto"
IMAGES = ["assets/img1.png", "assets/img4.png", "assets/img2.png", "assets/img3.png"]


@pytest.fixture(scope="module")
def geom() -> Geometrie:
    return Geometrie.depuis_charte(storage.load_charte())


def _section_complete(m, hauteur: int, sid: str = "s") -> Section:
    """Une section qui remplit tous les champs de son modèle, encart compris."""
    blocs: list = [
        BlocImage(fichier=IMAGES[k % len(IMAGES)], legende="Légende" if m.legendes else None)
        for k in range(m.emplacements)
    ]
    if m.style_texte == "items":
        blocs += [BlocItem(texte="Élément", icone=IMAGES[1]), BlocItem(texte="Autre")]
    elif m.texte != "aucun" and m.paragraphes_max:
        blocs.append(BlocParagraphe(texte="Texte de l'étape."))
    blocs.append(BlocEncadre(style="astuce", texte="La licence est activée."))
    return Section(id=sid, titre="Titre", layout=m.id, hauteur=hauteur, blocs=blocs)


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------

def test_hauteur_par_defaut_et_compatibilite():
    assert Section(id="a", layout="triple-image", blocs=[]).hauteur == 2
    assert Section(id="a", layout="triple-image", hauteur=1, blocs=[]).hauteur == 1
    with pytest.raises(ValueError, match="poids possibles"):
        Section(id="a", layout="encart-seul", hauteur=3, blocs=[])
    with pytest.raises(ValueError, match="inconnu"):
        Section(id="a", layout="n-existe-pas", blocs=[])


def test_padding_borne():
    with pytest.raises(ValueError):
        BlocImage(fichier="a.png", padding_mm=-1)
    assert BlocImage(fichier="a.png", padding_mm=6).padding_mm == 6


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_images_remplissent_leur_boite_sans_deformation():
    assert re.search(r"\.media img\{[^}]*width:100%;height:100%;object-fit:contain", STRUCTURE_CSS)


def test_boite_image_a_une_hauteur_calculee(geom):
    m = MODELES_PAR_ID["image-gauche-texte"]
    html = render_section_html(_section_complete(m, 2), geom)
    hauteur = float(re.search(r'class="media" style="height:([\d.]+)mm', html).group(1))
    attendu = geom.corps_mm(2, True) - geom.legende_mm
    assert hauteur == pytest.approx(attendu, abs=0.05)


def test_padding_reduit_l_image_sans_changer_la_boite(geom):
    m = MODELES_PAR_ID["etape-compacte"]
    s = _section_complete(m, 1)
    sans = render_section_html(s, geom)
    s.blocs[0].padding_mm = 6
    avec = render_section_html(s, geom)
    hauteur = lambda html: re.search(r'class="media" style="height:([\d.]+)mm', html).group(1)
    assert hauteur(sans) == hauteur(avec)
    assert "padding:6.00mm" in avec and "padding:" not in sans.split('class="media"')[1][:60]


def test_gouttiere_entre_les_images(geom):
    html = render_section_html(_section_complete(MODELES_PAR_ID["triple-image"], 2), geom)
    assert html.count('class="s-cellule"') == 3
    assert html.count('class="s-espace"') == 2  # entre les 3 images, pas autour
    assert re.search(r"\.s-espace\{display:table-cell;width:var\(--espace-images\)", STRUCTURE_CSS)


def test_emplacement_vide_garde_sa_place(geom):
    m = MODELES_PAR_ID["triple-image"]
    s = Section(id="s", layout=m.id, blocs=[BlocImage(fichier=IMAGES[0])])
    html = render_section_html(s, geom)
    assert html.count('class="s-cellule"') == 3
    assert html.count("image-vide") == 2


def test_images_en_trop_ne_sont_pas_perdues(geom):
    """Un content.yaml écrit à la main avec plus d'images que d'emplacements :
    elles ajoutent des lignes plutôt que de disparaître."""
    m = MODELES_PAR_ID["deux-images"]
    s = Section(id="s", layout=m.id, blocs=[BlocImage(fichier=f) for f in IMAGES[:3]])
    assert render_section_html(s, geom).count("<img") == 3


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

def test_marge_de_securite_en_bas_de_section(geom):
    assert geom.pad_bas_mm >= 4
    assert "padding:var(--sec-pad-haut) 0 var(--sec-pad-bas)" in STRUCTURE_CSS
    # La géométrie la déduit bien de la place disponible.
    assert geom.corps_mm(1, False) == pytest.approx(
        geom.unite_mm - geom.pad_haut_mm - geom.pad_bas_mm
    )


def test_encart_disponible_dans_chaque_modele(geom):
    for m in MODELES:
        html = render_section_html(_section_complete(m, m.defaut), geom)
        assert 'class="encadre encadre-astuce"' in html, m.id


def test_chaque_modele_se_rend_dans_chaque_poids(geom):
    for m in MODELES:
        for h in m.hauteurs:
            html = render_section_html(_section_complete(m, h), geom)
            assert f'class="sec h{h} {m.id} ' in html, (m.id, h)
            assert html.count("<img") >= m.emplacements, (m.id, h)


def test_pdf_respecte_le_poids_de_chaque_section(tmp_path):
    """Tous les modèles, dans tous leurs poids, remplis au maximum : le PDF
    doit compter exactement les pages prévues par `paginate`. Si une section
    débordait de son quota, WeasyPrint ajouterait des pages."""
    sections = [
        _section_complete(m, h, sid=f"{m.id}-{h}") for m in MODELES for h in m.hauteurs
    ]
    article = Article(
        id=EXEMPLE, type="tutoriel", template_id="tuto-release",
        titre="Tous les modèles", auteur="Test", prerequis=["Un prérequis"],
        sections=sections,
    )
    config = storage.load_template_config("tuto-release")
    sortie = tmp_path / "article.html"
    render_article(
        article, config, storage.load_charte(),
        storage.template_file_path("tuto-release", config.fichier),
        storage.article_dir(EXEMPLE), sortie, avec_editeur=False,
    )
    pages_pdf = len(HTML(filename=str(sortie)).render().pages)
    assert pages_pdf == len(paginate(sections, premiere_page_reservee=1))


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------

def test_liens_internet_cliquables():
    html = markdown_to_html("Voir [la plateforme](https://app.syope.fr) ou http://x.fr/a.")
    assert '<a href="https://app.syope.fr" target="_blank" rel="noopener">la plateforme</a>' in html
    assert '<a href="http://x.fr/a" target="_blank" rel="noopener">http://x.fr/a</a>.' in html


def test_seuls_les_liens_internet_sont_acceptes():
    for piege in ("[x](javascript:alert(1))", "[x](mailto:a@b.fr)", "[x](/relatif)"):
        assert "<a " not in markdown_to_html(piege), piege


def test_liste_numerotee():
    assert markdown_to_html("1. Un\n2. Deux") == '<ol class="corps"><li>Un</li><li>Deux</li></ol>'
    assert 'start="5"' in markdown_to_html("5. Cinq")


def test_items_alignes_meme_sans_icone(geom):
    m = MODELES_PAR_ID["image-items"]
    s = Section(id="s", layout=m.id, blocs=[
        BlocImage(fichier=IMAGES[0]),
        BlocItem(texte="Avec icône", icone=IMAGES[1]),
        BlocItem(texte="Sans icône"),
    ])
    assert render_section_html(s, geom).count('class="s-item-icone"') == 2


def test_icone_d_item_validee():
    from app.validation import validate_article

    article, _ = storage.load_article(EXEMPLE)
    article.sections[0].blocs.append(BlocItem(texte="x", icone="assets/absente.png"))
    config = storage.load_template_config(article.template_id)
    rapport = validate_article(article, config, assets_dir=storage.article_dir(EXEMPLE))
    assert any("absente.png" in e for e in rapport.errors)


def test_legende_trop_longue_en_bas_de_page_ne_cree_pas_de_page(tmp_path):
    """Régression : une légende de trois lignes (deux réservées) dans une
    section qui finit pile en bas de page. WeasyPrint reportait la légende sur
    une nouvelle page au lieu de la rogner. Le moteur doit s'en protéger seul,
    sans compter sur le CSS de l'éditeur (verrou de hauteur des pages)."""
    longue = "Cliquez sur l'icône en forme de trombone présente dans l'en-tête " * 3
    sections = [
        Section(id="a", titre="Étape", layout="etape-compacte", hauteur=1,
                blocs=[BlocImage(fichier=IMAGES[0]), BlocParagraphe(texte="Texte.")]),
        Section(id="b", titre="Trois captures", layout="triple-image", hauteur=2,
                blocs=[BlocImage(fichier=f, legende=longue) for f in IMAGES[:3]]),
    ]
    article = Article(id=EXEMPLE, type="tutoriel", template_id="tuto-release",
                      titre="Bas de page", auteur="Test", sections=sections)
    config = storage.load_template_config("tuto-release")
    sortie = tmp_path / "article.html"
    render_article(
        article, config, storage.load_charte(),
        storage.template_file_path("tuto-release", config.fichier),
        storage.article_dir(EXEMPLE), sortie, avec_editeur=False,
    )
    assert len(HTML(filename=str(sortie)).render().pages) == 1


def test_calques_hors_du_conteneur_rogne(geom):
    """Les calques restent enfants directs de la section (l'éditeur les y
    cherche) et hors du conteneur qui rogne le contenu."""
    html = render_section_html(
        _section_complete(MODELES_PAR_ID["etape-compacte"], 1), geom,
        calques_html='<div class="calque calque-fleche"></div>',
    )
    assert html.endswith('</div><div class="calque calque-fleche"></div></section>')
    assert html.index('class="sec-contenu"') < html.index('class="calque')
