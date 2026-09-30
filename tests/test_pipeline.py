"""Tests de bout en bout du pipeline Étape 1 (voir CLAUDE.md, DoD Étape 1).

Le moteur produit du HTML (converti en PDF par WeasyPrint) : les tests vérifient
la structure HTML plutôt qu'un document Word.
"""
from __future__ import annotations

from app import storage
from app.build import generate_article
from app.pagination import paginate
from app.schemas import Section
from app.validation import validate_article


def _section(id_: str, layout: str = "texte-seul") -> Section:
    return Section(id=id_, titre=id_, layout=layout, blocs=[])


def test_pagination_respects_grid():
    # h=1, h=1, h=2, h=4, h=3
    sections = [
        _section("a", "texte-seul"),
        _section("b", "texte-seul"),
        _section("c", "image-gauche-texte"),
        _section("d", "pleine-page"),
        _section("e", "etape-detaillee"),
    ]
    pages = paginate(sections)
    assert [[s.id for s in page] for page in pages] == [["a", "b", "c"], ["d"], ["e"]]
    for page in pages:
        assert sum(s.hauteur for s in page) <= 4


def test_pagination_reserves_first_page():
    # h=1, h=1, h=2, h=4, h=3
    sections = [
        _section("a", "texte-seul"),
        _section("b", "texte-seul"),
        _section("c", "image-gauche-texte"),
        _section("d", "pleine-page"),
        _section("e", "etape-detaillee"),
    ]
    pages = paginate(sections, premiere_page_reservee=1)
    # Première page : budget 3 (4-1 réservé titre) → a(1)+b(1)=2, c(2) ferait 4>3
    assert [[s.id for s in page] for page in pages] == [["a", "b"], ["c"], ["d"], ["e"]]


def test_validate_article_rejects_too_long_title():
    article, _ = storage.load_article("2026-07-exemple-tuto")
    config = storage.load_template_config(article.template_id)
    article.titre = "x" * 200
    report = validate_article(article, config, assets_dir=storage.article_dir(article.id))
    assert not report.ok
    assert "Titre trop long" in report.errors[0]


def test_generate_sample_article_end_to_end():
    result = generate_article("2026-07-exemple-tuto", skip_pdf=True)
    assert result.html_path.is_file()
    assert len(result.hash_contenu) == 64

    html = result.html_path.read_text(encoding="utf-8")
    # Le fragment de l'éditeur (barre, palette, script) est injecté en fin de
    # <body> et contient lui aussi du balisage : on n'inspecte que le document.
    document = html.split('<style id="editeur-css">')[0]

    # 5 images : sec-1(1) + sec-2(3) + sec-3(1)
    assert document.count("<img") == 5

    # Styles nommés de la charte appliqués via classes
    for cls in ("titre-1", "titre-2", "corps", "legende"):
        assert cls in document

    # Le liseré de l'étape compacte est bien rendu
    assert '<div class="s-lisere-barre">' in document

    # Deux feuilles : sec-1(h=1)+sec-2(h=2)=3 sur page 1 (budget 3),
    # sec-3(h=2) → page 2. Chaque page est un <div class="page">.
    assert document.count('<div class="page">') == 2


def test_hauteurs_fixes_rognent_au_lieu_de_pousser():
    """Un en-tête chargé et une section trop longue ne doivent pas repousser la
    mise en page : chaque bloc garde exactement son quota (CLAUDE.md §3), le
    surplus est rogné. Sans cela, la pagination calculée par `paginate` et
    celle du PDF divergeraient."""
    import shutil

    from weasyprint import HTML

    from app.schemas import Article, BlocParagraphe, Section

    article_id = "tmp-test-debordement"
    article = Article(
        id=article_id,
        type="tutoriel",
        template_id="tuto-release",
        titre="Débordement",
        auteur="Test",
        resume="Un résumé volontairement long. " * 30,
        prerequis=[f"Prérequis {i}" for i in range(12)],
        sections=[
            Section(
                id="sec-1",
                titre="Section d'une unité",
                layout="texte-seul",
                blocs=[BlocParagraphe(texte="Texte volontairement très long. " * 120)],
            ),
            Section(
                id="sec-2",
                titre="Section suivante",
                layout="texte-seul",
                blocs=[BlocParagraphe(texte="Court.")],
            ),
        ],
    )
    storage.write_article(article)
    try:
        result = generate_article(article_id, skip_pdf=True)
        # 1 unité d'en-tête + 1 + 1 = 3 unités : tout tient sur une seule page.
        assert len(HTML(filename=str(result.html_path)).render().pages) == 1
    finally:
        shutil.rmtree(storage.article_dir(article_id), ignore_errors=True)
