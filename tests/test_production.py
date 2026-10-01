"""Mode production (voir DEPLOIEMENT.md) : authentification, garde d'accès,
rendu sans barre d'édition, écritures atomiques, initialisation du volume.

Les réglages sont un objet partagé (`app.config.REGLAGES`) : chaque test bascule
ce dont il a besoin avec `monkeypatch`, sans redémarrer l'application.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import auth, storage
from app.config import REGLAGES
from app.renderer import render_article
from app.schemas import Calque, Retouches
from app.serveur import app

EXEMPLE = "2026-07-exemple-tuto"
MDP = "un-mot-de-passe-solide"


@pytest.fixture
def comptes(tmp_path, monkeypatch):
    monkeypatch.setattr(REGLAGES, "comptes_fichier", tmp_path / "comptes.yaml")
    auth.enregistrer_compte("baptiste", "Baptiste Lemoine", MDP)
    return tmp_path / "comptes.yaml"


@pytest.fixture
def client_prod(comptes, monkeypatch):
    monkeypatch.setattr(REGLAGES, "auth_active", True)
    return TestClient(app, follow_redirects=False)


def _connecter(client) -> None:
    rep = client.post("/connexion", data={"identifiant": "baptiste", "mot_de_passe": MDP})
    assert rep.status_code == 303 and auth.NOM_COOKIE in rep.cookies


# ---------------------------------------------------------------------------
# Mots de passe et jetons
# ---------------------------------------------------------------------------

def test_mot_de_passe_hache_et_verifie():
    h = auth.hacher("secret")
    assert h.startswith("scrypt$") and "secret" not in h
    assert auth.verifier("secret", h)
    assert not auth.verifier("autre", h)
    assert auth.hacher("secret") != h  # sel aléatoire
    assert not auth.verifier("secret", "n'importe quoi")


def test_fichier_des_comptes_prive(comptes):
    assert "hash: scrypt$" in comptes.read_text()
    assert oct(comptes.stat().st_mode & 0o777) == "0o600"


def test_jeton_valide_falsifie_expire_revoque(comptes, monkeypatch):
    compte = auth.authentifier("baptiste", MDP)
    jeton = auth.emettre_jeton(compte)
    assert auth.lire_jeton(jeton) == compte

    charge, signature = jeton.rsplit(".", 1)
    assert auth.lire_jeton(f"{charge}.{signature[:-2]}AA") is None  # signature altérée
    assert auth.lire_jeton("pas-un-jeton") is None

    monkeypatch.setattr(REGLAGES, "duree_session_h", -1)
    assert auth.lire_jeton(auth.emettre_jeton(compte)) is None  # expiré
    monkeypatch.setattr(REGLAGES, "duree_session_h", 1)

    auth.supprimer_compte("baptiste")
    assert auth.lire_jeton(jeton) is None  # compte supprimé → sessions coupées


def test_changer_la_cle_deconnecte(comptes, monkeypatch):
    jeton = auth.emettre_jeton(auth.authentifier("baptiste", MDP))
    monkeypatch.setattr(REGLAGES, "cle_session", "une-toute-autre-cle-de-session-32c")
    assert auth.lire_jeton(jeton) is None


# ---------------------------------------------------------------------------
# Garde d'accès
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("chemin", [
    "/api/articles",
    f"/api/articles/{EXEMPLE}/content",
    f"/api/articles/{EXEMPLE}/pdf",
    "/vault/charte/charte.yaml",
    f"/vault/articles/{EXEMPLE}/content.yaml",
])
def test_donnees_inaccessibles_sans_session(client_prod, chemin):
    assert client_prod.get(chemin).status_code == 401


def test_navigation_redirigee_vers_la_connexion(client_prod):
    rep = client_prod.get("/")
    assert rep.status_code == 303
    assert rep.headers["location"] == "/connexion?suite=/"


def test_routes_publiques(client_prod):
    assert client_prod.get("/sante").status_code == 200
    assert client_prod.get("/connexion").status_code == 200
    assert client_prod.get("/ui/composeur.css").status_code == 200


def test_ecritures_refusees_sans_session(client_prod):
    rep = client_prod.post(f"/api/articles/{EXEMPLE}/enregistrer", json={"article": {}})
    assert rep.status_code == 401


def test_connexion_puis_acces(client_prod):
    _connecter(client_prod)
    assert client_prod.get("/").status_code == 200
    assert client_prod.get("/api/articles").status_code == 200
    moi = client_prod.get("/api/moi").json()
    assert moi == {"auth": True, "identifiant": "baptiste", "nom": "Baptiste Lemoine"}


def test_mauvais_mot_de_passe(client_prod, monkeypatch):
    monkeypatch.setattr("app.connexion.asyncio.sleep", _sans_attente)
    rep = client_prod.post("/connexion", data={"identifiant": "baptiste", "mot_de_passe": "faux"})
    assert rep.status_code == 303
    assert "erreur=1" in rep.headers["location"]
    assert auth.NOM_COOKIE not in rep.cookies


async def _sans_attente(_):
    return None


@pytest.mark.parametrize("suite", ["//evil.example", "https://evil.example", "\\\\evil"])
def test_pas_de_redirection_vers_un_autre_site(client_prod, suite):
    rep = client_prod.post(
        "/connexion", data={"identifiant": "baptiste", "mot_de_passe": MDP, "suite": suite}
    )
    assert rep.headers["location"] == "/"


def test_deconnexion(client_prod):
    _connecter(client_prod)
    rep = client_prod.post("/deconnexion")
    assert rep.status_code == 303
    client_prod.cookies.clear()
    assert client_prod.get("/api/articles").status_code == 401


def test_cookie_securise_en_production(client_prod, monkeypatch):
    monkeypatch.setattr(REGLAGES, "production", True)
    rep = client_prod.post("/connexion", data={"identifiant": "baptiste", "mot_de_passe": MDP})
    cookie = rep.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_mode_dev_sans_authentification():
    client = TestClient(app)
    assert not REGLAGES.auth_active
    assert client.get("/api/articles").status_code == 200


# ---------------------------------------------------------------------------
# Rendu de production
# ---------------------------------------------------------------------------

def test_html_de_production_sans_barre_mais_avec_annotations(tmp_path):
    """Régression : les styles des calques étaient livrés avec la barre
    d'édition. Sans barre (production), une pastille retombait en simple
    texte dans le flux."""
    article, _ = storage.load_article(EXEMPLE)
    config = storage.load_template_config(article.template_id)
    retouches = Retouches(calques=[Calque(
        ancre_section="sec-1", classes="calque calque-pastille", style="left:10%;top:10%;",
        redim="non", html="1",
    )])
    sortie = tmp_path / "article.html"
    html = render_article(
        article, config, storage.load_charte(),
        storage.template_file_path(article.template_id, config.fichier),
        storage.article_dir(EXEMPLE), sortie, retouches=retouches, avec_editeur=False,
    )
    assert "editor-bar" not in html and "enregistrerHTML" not in html
    assert 'id="modules-css"' in html
    assert ".calque { position: absolute" in html
    assert 'class="calque calque-pastille"' in html


def test_apercu_sans_url_absolue(client_prod):
    """Derrière Envoy, l'adresse vue par le serveur est interne : l'aperçu ne
    doit embarquer que des chemins relatifs."""
    _connecter(client_prod)
    article, _ = storage.load_article(EXEMPLE)
    html = client_prod.post(
        f"/api/articles/{EXEMPLE}/apercu", json={"article": article.model_dump(mode="json")}
    ).json()["html"]
    assert f'"/articles/{EXEMPLE}/html"' in html
    assert "http://testserver" not in html


def test_telechargement_du_pdf(client_prod, tmp_path, monkeypatch):
    _connecter(client_prod)
    assert client_prod.get("/api/articles/n-existe-pas/pdf").status_code == 404
    pdf = storage.article_output_dir(EXEMPLE) / "article.pdf"
    if not pdf.is_file():
        pytest.skip("pas de PDF généré pour l'exemple")
    rep = client_prod.get(f"/api/articles/{EXEMPLE}/pdf")
    assert rep.status_code == 200
    assert rep.headers["content-type"] == "application/pdf"
    assert f'filename="{EXEMPLE}.pdf"' in rep.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------------

def test_ecriture_atomique(tmp_path):
    cible = tmp_path / "content.yaml"
    storage.ecrire_atomique(cible, "v1")
    storage.ecrire_atomique(cible, "v2")
    assert cible.read_text() == "v2"
    assert [p.name for p in tmp_path.iterdir()] == ["content.yaml"]  # aucun temporaire


def test_ecriture_interrompue_garde_l_ancienne_version(tmp_path, monkeypatch):
    cible = tmp_path / "content.yaml"
    storage.ecrire_atomique(cible, "version intacte")

    def panne(*_):
        raise OSError("disque plein")

    monkeypatch.setattr("app.storage.os.replace", panne)
    with pytest.raises(OSError):
        storage.ecrire_atomique(cible, "version tronquée")
    assert cible.read_text() == "version intacte"
    assert [p.name for p in tmp_path.iterdir()] == ["content.yaml"]


def test_init_vault_prepare_un_volume_vide(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from app.cli import app as cli

    vault = tmp_path / "vault"
    monkeypatch.setattr(storage, "VAULT_ROOT", vault)
    (vault / "articles" / "mon-tuto").mkdir(parents=True)
    (vault / "articles" / "mon-tuto" / "content.yaml").write_text("titre: garde-moi")

    rep = CliRunner().invoke(cli, ["init-vault"])
    assert rep.exit_code == 0, rep.output
    assert (vault / "charte" / "charte.yaml").is_file()
    assert (vault / "charte" / "fonts" / "Inter-Regular.ttf").is_file()
    assert (vault / "templates" / "tuto-release" / "template.html").is_file()
    # Les tutoriels ne sont jamais touchés.
    assert (vault / "articles" / "mon-tuto" / "content.yaml").read_text() == "titre: garde-moi"
    assert "1 tutoriel(s)" in rep.output


def test_production_exige_une_cle(monkeypatch):
    from app import config

    monkeypatch.setenv("TUTO_ENV", "production")
    monkeypatch.delenv("TUTO_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TUTO_SECRET_KEY"):
        config.charger()
    monkeypatch.setenv("TUTO_SECRET_KEY", "x" * 40)
    r = config.charger()
    assert r.production and r.auth_active and not r.editeur_autonome


def test_session_dure_le_temps_configure(comptes):
    compte = auth.authentifier("baptiste", MDP)
    jeton = auth.emettre_jeton(compte)
    import base64
    import json

    charge = jeton.rsplit(".", 1)[0]
    exp = json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)))["exp"]
    assert exp == pytest.approx(time.time() + REGLAGES.duree_session_h * 3600, abs=5)
