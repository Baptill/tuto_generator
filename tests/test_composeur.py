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
from app.catalogue import catalogue_json, champs_de
from app.modeles import MODELES, MODELES_PAR_ID, Geometrie
from app.serveur import app

ARTICLE_EXEMPLE = "2026-07-exemple-tuto"

# Poids historiques : les content.yaml écrits avant l'introduction de
# `hauteur` doivent garder exactement la même mise en page.
POIDS_HISTORIQUES = {
    "texte-seul": 1,
    "etape-compacte": 1,
    "image-gauche-texte": 2,
    "texte-image-droite": 2,
    "image-dessus-texte": 2,
    "triple-image": 2,
    "etape-detaillee": 3,
    "pleine-page": 4,
}


@pytest.fixture
def client():
    return TestClient(app)


def test_modeles_historiques_gardent_leur_poids():
    for layout_id, poids in POIDS_HISTORIQUES.items():
        assert MODELES_PAR_ID[layout_id].defaut == poids, layout_id


def test_chaque_modele_est_coherent():
    for m in MODELES:
        assert m.defaut in m.hauteurs, m.id
        assert set(m.hauteurs) <= {1, 2, 3, 4}, m.id
        assert 0 < m.ratio < 1, m.id


def test_champs_derives_du_modele():
    """Le formulaire demande exactement les emplacements du modèle, et tous
    les modèles proposent des encarts en option."""
    for m in MODELES:
        champs = champs_de(m)
        types = [c.type for c in champs]
        assert "encadre" in types, f"{m.id} : pas d'encart proposé"
        images = [c for c in champs if c.type == "image"]
        if m.a_images:
            assert images[0].mini == m.emplacements, m.id
            assert images[0].padding, m.id
        else:
            assert not images, m.id
        if m.texte == "aucun":
            assert "paragraphe" not in types and "item" not in types, m.id
    triple = champs_de(MODELES_PAR_ID["triple-image"])[0]
    assert (triple.type, triple.mini, triple.maxi, triple.legende) == ("image", 3, 3, True)


def test_endpoint_catalogue(client):
    rep = client.get("/api/catalogue", params={"template_id": "tuto-release"})
    assert rep.status_code == 200
    corps = rep.json()
    assert corps["template"]["sections_min"] == 2
    assert {m["id"] for m in corps["modeles"]} == set(MODELES_PAR_ID)
    assert {f["id"] for f in corps["familles"]} >= {m.famille for m in MODELES}
    for poids in "1234":
        assert sum(poids in m["wireframes"] for m in corps["modeles"]) >= 15, poids
    for m in corps["modeles"]:
        assert set(m["wireframes"]) == {str(h) for h in m["hauteurs"]}
        assert all("<svg" in svg for svg in m["wireframes"].values())


def test_wireframe_a_lechelle_de_la_section():
    """Le wireframe est dessiné en mm : son rapport hauteur/largeur est celui
    de la section rendue."""
    g = Geometrie.depuis_charte(storage.load_charte())
    cat = catalogue_json(g)
    svg = next(m for m in cat["modeles"] if m["id"] == "grille-2x2")["wireframes"]["4"]
    assert f'viewBox="0 0 {g.largeur_mm:.1f} {g.section_mm(4):.1f}"' in svg


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
    article, contenu_avant = storage.load_article(ARTICLE_EXEMPLE)
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
        # L'enregistrement réécrit content.yaml : on rend l'exemple tel quel.
        storage.content_path(ARTICLE_EXEMPLE).write_bytes(contenu_avant)
        storage.retouches_path(ARTICLE_EXEMPLE).write_bytes(avant)
        from app.build import generate_article

        generate_article(ARTICLE_EXEMPLE, skip_pdf=True)


def test_aller_retour_des_nouveaux_champs(client):
    """Poids, padding d'image, éléments de liste à icône et liens survivent à
    l'enregistrement dans content.yaml."""
    article_id = "test-composeur-modeles"
    assets = storage.article_assets_dir(article_id)
    assets.mkdir(parents=True, exist_ok=True)
    for nom in ("img1.png", "img4.png"):
        shutil.copy(storage.article_assets_dir(ARTICLE_EXEMPLE) / nom, assets / nom)
    charge = {
        "type": "tutoriel", "template_id": "tuto-release", "titre": "Modèles", "auteur": "Test",
        "sections": [
            {"id": "sec-1", "layout": "image-items", "hauteur": 3, "blocs": [
                {"type": "image", "fichier": "assets/img1.png", "padding_mm": 8},
                {"type": "item", "texte": "Dictée vocale", "icone": "assets/img4.png"},
                {"type": "item", "texte": "Voir [l'aide](https://app.syope.fr/aide)"},
                {"type": "encadre", "style": "astuce", "texte": "La licence est activée."},
            ]},
            {"id": "sec-2", "layout": "encart-seul", "blocs": [
                {"type": "encadre", "style": "info", "texte": "Fin."},
            ]},
        ],
    }
    try:
        rep = client.post(f"/api/articles/{article_id}/enregistrer", json={"article": charge})
        assert rep.json()["ok"], rep.json()
        relu, brut = storage.load_article(article_id)
        s1 = relu.sections[0]
        assert (s1.layout, s1.hauteur) == ("image-items", 3)
        assert s1.blocs[0].padding_mm == 8
        assert s1.blocs[1].icone == "assets/img4.png"
        assert relu.sections[1].hauteur == 1  # poids par défaut du modèle
        html = storage.article_output_dir(article_id).joinpath("article.html").read_text()
        assert 'href="https://app.syope.fr/aide"' in html
        assert "padding:8.00mm" in html
        # Pas de clé vide parasite dans le fichier écrit.
        assert b"padding_mm: null" not in brut and b"icone: null" not in brut
    finally:
        shutil.rmtree(storage.article_dir(article_id), ignore_errors=True)


def test_hauteur_incompatible_refusee(client):
    charge = {
        "type": "tutoriel", "template_id": "tuto-release", "titre": "X", "auteur": "Test",
        "sections": [{"id": "s", "layout": "encart-seul", "hauteur": 4, "blocs": []}],
    }
    rep = client.post(f"/api/articles/{ARTICLE_EXEMPLE}/apercu", json={"article": charge})
    assert rep.status_code == 422
    assert "poids possibles" in " ".join(rep.json()["detail"])
