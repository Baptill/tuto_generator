"""Tests du composeur — l'UI de saisie (voir CLAUDE.md, Étape 1 « UI MVP »).

Deux invariants tiennent tout le reste :
- le catalogue proposé à la saisie décrit exactement les layouts que le moteur
  sait rendre (sinon l'utilisateur compose une section irrendable) ;
- l'aperçu n'écrit rien : seul « Enregistrer » touche `content.yaml`.
"""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from app import storage
from app.catalogue import CATALOGUE, CATALOGUE_PAR_ID
from app.layouts import LAYOUTS
from app.schemas import LAYOUT_HAUTEURS
from app.serveur import app

ARTICLE_EXEMPLE = "2026-07-exemple-tuto"


@pytest.fixture
def client():
    return TestClient(app)


def test_catalogue_couvre_exactement_les_layouts_rendus():
    assert set(CATALOGUE_PAR_ID) == set(LAYOUTS) == set(LAYOUT_HAUTEURS)
    for entree in CATALOGUE:
        assert entree.hauteur == LAYOUT_HAUTEURS[entree.id]


def test_catalogue_champs_coherents_avec_le_rendu():
    """Les layouts qui n'affichent qu'une image ne doivent pas en demander
    plusieurs — et `triple-image` doit bien en demander trois."""
    for entree in CATALOGUE:
        assert entree.champs, f"{entree.id} : aucun champ à saisir"
        for champ in entree.champs:
            assert champ.type in {"image", "paragraphe", "encadre"}
            assert 0 <= champ.mini <= champ.maxi
    triple = CATALOGUE_PAR_ID["triple-image"].champs[0]
    assert (triple.type, triple.mini, triple.maxi, triple.legende) == ("image", 3, 3, True)


def test_endpoint_catalogue(client):
    rep = client.get("/api/catalogue", params={"template_id": "tuto-release"})
    assert rep.status_code == 200
    corps = rep.json()
    assert corps["template"]["sections_min"] == 2
    assert {l["id"] for l in corps["layouts"]} == set(LAYOUTS)
    assert all("<svg" in l["wireframe"] for l in corps["layouts"])


def test_apercu_rend_sans_rien_ecrire(client):
    article, brut_avant = storage.load_article(ARTICLE_EXEMPLE)
    charge = article.model_dump(mode="json")
    charge["titre"] = "Titre modifié dans le composeur"

    rep = client.post(f"/api/articles/{ARTICLE_EXEMPLE}/apercu", json={"article": charge})
    assert rep.status_code == 200
    html = rep.json()["html"]

    assert "Titre modifié dans le composeur" in html
    # L'aperçu est servi en http:// : aucune ressource en file:// (images,
    # polices, logo) — le navigateur les refuserait.
    assert "url('file://" not in html
    assert 'src="file://' not in html
    assert f'<base href="/vault/articles/{ARTICLE_EXEMPLE}/"' in html
    # Surface d'édition embarquée (annotations), en mode « régénérer » : ce qui
    # sera persisté, ce sont les calques, pas ce rendu de travail.
    assert "editeur-css" in html
    assert "var REGENERER = true" in html
    assert f"/articles/{ARTICLE_EXEMPLE}/html" in html
    # `content.yaml` n'a pas bougé.
    assert storage.content_path(ARTICLE_EXEMPLE).read_bytes() == brut_avant


def test_apercu_tolere_un_article_incomplet(client):
    """En cours de saisie, une seule section sans image : l'aperçu doit rendre
    quand même et signaler ce qui bloquerait l'enregistrement."""
    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Brouillon",
        "auteur": "—",
        "sections": [{"id": "sec-1", "layout": "texte-seul", "blocs": []}],
    }
    rep = client.post(f"/api/articles/{ARTICLE_EXEMPLE}/apercu", json={"article": charge})
    assert rep.status_code == 200
    assert "Brouillon" in rep.json()["html"]
    assert any("Trop peu de sections" in a for a in rep.json()["avertissements"])


def test_apercu_refuse_un_layout_inconnu(client):
    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Brouillon",
        "auteur": "—",
        "sections": [{"id": "sec-1", "layout": "layout-fantome", "blocs": []}],
    }
    rep = client.post(f"/api/articles/{ARTICLE_EXEMPLE}/apercu", json={"article": charge})
    assert rep.status_code == 422


def test_id_article_hors_vault_refuse(client):
    rep = client.get("/api/articles/..%2F..%2Fetc/content")
    assert rep.status_code in (400, 404)


def test_enregistrer_ecrit_content_yaml_puis_genere(client, tmp_path):
    """Parcours complet du composeur : saisie → content.yaml → HTML + PDF."""
    article_id = "test-composeur-tmp"
    source = storage.article_assets_dir(ARTICLE_EXEMPLE) / "img1.png"
    assets = storage.article_assets_dir(article_id)
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, assets / "img1.png")

    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Article du composeur",
        "resume": "Sous-titre",
        "auteur": "Test",
        "prerequis": ["Être connecté"],
        "sections": [
            {
                "id": "sec-1",
                "titre": "1 - Ouvrir",
                "layout": "etape-compacte",
                "blocs": [
                    {"type": "image", "fichier": "assets/img1.png"},
                    {"type": "paragraphe", "texte": "Cliquez sur le bouton."},
                ],
            },
            {
                "id": "sec-2",
                "titre": "2 - Conclure",
                "layout": "texte-seul",
                "blocs": [{"type": "encadre", "style": "astuce", "texte": "Pensez à enregistrer."}],
            },
        ],
    }

    try:
        rep = client.post(
            f"/api/articles/{article_id}/enregistrer", json={"article": charge}
        )
        assert rep.status_code == 200, rep.text
        corps = rep.json()
        assert corps["ok"], corps

        relu, _ = storage.load_article(article_id)
        assert relu.titre == "Article du composeur"
        assert [s.layout for s in relu.sections] == ["etape-compacte", "texte-seul"]
        assert storage.article_output_dir(article_id).joinpath("article.html").is_file()

        html = storage.article_output_dir(article_id).joinpath("article.html").read_text()
        assert "encadre-astuce" in html
    finally:
        shutil.rmtree(storage.article_dir(article_id), ignore_errors=True)


def test_enregistrer_refuse_un_article_invalide(client):
    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Une seule section",
        "auteur": "Test",
        "sections": [{"id": "sec-1", "layout": "texte-seul", "blocs": []}],
    }
    rep = client.post("/api/articles/test-composeur-invalide/enregistrer", json={"article": charge})
    assert rep.status_code == 200
    assert rep.json()["ok"] is False
    assert not storage.article_dir("test-composeur-invalide").exists()


def test_enregistrement_auto_ecrit_un_brouillon_incomplet(client):
    """Dès la saisie du titre, le tutoriel existe sur disque — même s'il ne
    respecte pas encore les contraintes du template (ici : 0 section)."""
    article_id = "test-composeur-brouillon"
    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Brouillon tout juste commencé",
        "auteur": "—",
        "sections": [],
    }
    try:
        rep = client.post(
            f"/api/articles/{article_id}/enregistrer", params={"auto": 1}, json={"article": charge}
        )
        assert rep.status_code == 200
        corps = rep.json()
        assert corps["ok"] is True
        assert any("Trop peu de sections" in a for a in corps["avertissements"])

        relu, _ = storage.load_article(article_id)
        assert relu.titre == "Brouillon tout juste commencé"
        # Pas de rendu tant que le tutoriel est incomplet — et jamais de PDF en
        # enregistrement de fond.
        assert corps["html"] is None and corps["pdf"] is None
    finally:
        shutil.rmtree(storage.article_dir(article_id), ignore_errors=True)


def test_enregistrement_auto_ne_produit_pas_de_pdf(client):
    """Un tutoriel valide enregistré automatiquement est rendu en HTML, mais le
    PDF (quelques secondes de WeasyPrint) reste réservé au bouton explicite."""
    article_id = "test-composeur-auto"
    assets = storage.article_assets_dir(article_id)
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(storage.article_assets_dir(ARTICLE_EXEMPLE) / "img1.png", assets / "img1.png")
    charge = {
        "type": "tutoriel",
        "template_id": "tuto-release",
        "titre": "Tutoriel valide",
        "auteur": "Test",
        "sections": [
            {
                "id": "sec-1",
                "layout": "etape-compacte",
                "blocs": [
                    {"type": "image", "fichier": "assets/img1.png"},
                    {"type": "paragraphe", "texte": "Texte."},
                ],
            },
            {"id": "sec-2", "layout": "texte-seul", "blocs": [{"type": "paragraphe", "texte": "Fin."}]},
        ],
    }
    try:
        rep = client.post(
            f"/api/articles/{article_id}/enregistrer", params={"auto": 1}, json={"article": charge}
        )
        assert rep.json()["ok"] is True
        assert rep.json()["html"] is not None
        assert rep.json()["pdf"] is None
        assert not storage.article_output_dir(article_id).joinpath("article.pdf").exists()
    finally:
        shutil.rmtree(storage.article_dir(article_id), ignore_errors=True)


def test_annotation_depuis_apercu_persiste_et_regenere(client):
    """Enregistrer depuis l'aperçu ne fige pas le rendu de travail : seuls les
    calques sont persistés, puis l'artefact est reconstruit depuis la source
    (chemins locaux, PDF correct). Voir app/serveur.py."""
    retouches_avant = storage.retouches_path(ARTICLE_EXEMPLE).read_bytes()
    calque = {
        "ancre_section": "sec-1",
        "page": 0,
        "classes": "calque calque-pastille",
        "style": "left: 10%; top: 20%;",
        "texte": False,
        "redim": "non",
        "html": "9<script>alert(1)</script>",
    }
    try:
        rep = client.post(
            f"/articles/{ARTICLE_EXEMPLE}/html",
            json={"html": "<html><body>rendu de travail</body></html>",
                  "calques": [calque], "regenerer": True},
        )
        assert rep.status_code == 200, rep.text

        html = storage.article_output_dir(ARTICLE_EXEMPLE).joinpath("article.html").read_text()
        # Le rendu de travail posté n'a pas été figé : c'est bien un artefact
        # reconstruit, avec ses chemins locaux et le calque réinjecté.
        assert "rendu de travail" not in html
        assert "file://" in html
        assert "calque-pastille" in html
        assert "<script>alert(1)</script>" not in html  # calque assaini
        assert storage.load_retouches(ARTICLE_EXEMPLE).calques[0].ancre_section == "sec-1"
    finally:
        storage.retouches_path(ARTICLE_EXEMPLE).write_bytes(retouches_avant)
        from app.build import generate_article

        generate_article(ARTICLE_EXEMPLE, skip_pdf=True)


def test_apercu_sans_bouton_enregistrer_html(client):
    """Dans le composeur, l'enregistrement est celui de la page principale : la
    barre de l'aperçu ne doit pas proposer un second bouton concurrent."""
    article, _ = storage.load_article(ARTICLE_EXEMPLE)
    rep = client.post(
        f"/api/articles/{ARTICLE_EXEMPLE}/apercu", json={"article": article.model_dump(mode="json")}
    )
    html = rep.json()["html"]
    assert '<button onclick="enregistrerHTML(this)">' not in html
    assert 'id="btn-edit"' in html  # le mode édition, lui, reste
    # Le HTML autonome, seule voie de persistance quand il est ouvert seul, garde le sien.
    autonome = storage.article_output_dir(ARTICLE_EXEMPLE).joinpath("article.html").read_text()
    assert '<button onclick="enregistrerHTML(this)">' in autonome


def test_apercu_prend_les_calques_de_la_charge(client):
    """Un calque posé mais pas encore enregistré est renvoyé avec l'aperçu :
    il doit survivre au rafraîchissement, sans toucher à `retouches.yaml`."""
    article, _ = storage.load_article(ARTICLE_EXEMPLE)
    avant = storage.retouches_path(ARTICLE_EXEMPLE).read_bytes()
    calque = {
        "ancre_section": "sec-1",
        "page": 0,
        "classes": "calque calque-cadre",
        "style": "left: 10%; top: 20%;",
        "texte": False,
        "redim": "boite",
        "html": "",
    }
    rep = client.post(
        f"/api/articles/{ARTICLE_EXEMPLE}/apercu",
        json={"article": article.model_dump(mode="json"), "calques": [calque]},
    )
    html = rep.json()["html"]
    # On compte les calques *rendus* (le CSS et le catalogue de l'éditeur citent
    # aussi ces classes).
    assert html.count('class="calque calque-cadre"') == 1
    # Les calques déjà enregistrés ne sont pas rendus en plus : la charge fait foi.
    assert 'class="calque calque-pastille"' not in html
    assert storage.retouches_path(ARTICLE_EXEMPLE).read_bytes() == avant


def test_enregistrer_persiste_les_calques_de_lapercu(client):
    """« Enregistrer & générer » écrit la source *et* les annotations."""
    article, _ = storage.load_article(ARTICLE_EXEMPLE)
    avant = storage.retouches_path(ARTICLE_EXEMPLE).read_bytes()
    calque = {
        "ancre_section": "sec-2",
        "page": 0,
        "classes": "calque calque-etiquette",
        "style": "left: 10%; top: 20%;",
        "texte": True,
        "redim": "boite",
        "html": "Annotation<script>alert(1)</script>",
    }
    try:
        rep = client.post(
            f"/api/articles/{ARTICLE_EXEMPLE}/enregistrer",
            params={"auto": 1},
            json={"article": article.model_dump(mode="json"), "calques": [calque]},
        )
        assert rep.json()["ok"] is True
        calques = storage.load_retouches(ARTICLE_EXEMPLE).calques
        assert [c.classes for c in calques] == ["calque calque-etiquette"]
        assert "<script>" not in calques[0].html  # assaini au passage
        assert 'class="calque calque-etiquette"' in (
            storage.article_output_dir(ARTICLE_EXEMPLE) / "article.html"
        ).read_text()
    finally:
        storage.retouches_path(ARTICLE_EXEMPLE).write_bytes(avant)
        from app.build import generate_article

        generate_article(ARTICLE_EXEMPLE, skip_pdf=True)
