"""Serveur local d'enregistrement des retouches (voir CLAUDE.md §3).

Le bouton « Enregistrer HTML » de la surface d'édition ne télécharge pas une
copie : il **écrase** `output/article.html` puis **régénère** `output/article.pdf`.
Un navigateur ne pouvant pas écrire sur le disque, cette opération passe par ce
petit service local.

Portée volontairement minimale : un seul endpoint d'écriture. Il a vocation à
être absorbé par l'API FastAPI de l'UI (Étape 1, « UI MVP ») — d'où le choix de
FastAPI plutôt qu'un serveur ad hoc.

Rappel du principe §2 : `output/` reste un cache. L'enregistrement écrit donc
deux choses de natures différentes :

- `output/article.html` + `output/article.pdf` — artefacts, reconstructibles ;
- `retouches.yaml` — **source** des calques, versionnée dans Git au même titre
  que `content.yaml`, et réinjectée à chaque build. C'est elle qui permet à une
  régénération (changement de charte) de ne pas perdre les retouches.

Ce qui n'est PAS repris : les modifications de texte faites directement dans le
flux du document (elles appartiennent à `content.yaml`). D'où le marqueur
`retouche_html_le` dans `meta.yaml` (avertissement de re-synchro, §6).
"""
from __future__ import annotations

from datetime import date

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from app import journal, storage
from app.config import REGLAGES
from app.connexion import garde, router as connexion_router
from app.build import generate_article
from app.composer import UI_DIR, VAULT_MOUNT, router as composer_router
from app.editeur import assainir_html
from app.pdf import PdfConversionError, convert_to_pdf
from app.schemas import Calque, Retouches
from app.serveur_config import PORT_DEFAUT  # noqa: F401 — réexport pour la CLI

journal.configurer()
log = logging.getLogger("tuto.serveur")

app = FastAPI(
    title="tuto-generator — composeur & enregistrement des retouches",
    # En production, la documentation de l'API n'est pas exposée.
    docs_url=None if REGLAGES.production else "/docs",
    redoc_url=None if REGLAGES.production else "/redoc",
    openapi_url=None if REGLAGES.production else "/openapi.json",
)

# Garde d'accès : toutes les routes, montages statiques compris (app/connexion.py).
app.add_middleware(BaseHTTPMiddleware, dispatch=garde)

# Le composeur (UI de saisie du content.yaml) partage ce service : un seul
# `python -m app.cli serve` sert la saisie, l'aperçu et l'enregistrement.
app.include_router(connexion_router)
app.include_router(composer_router)
app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")
# Assets, polices et logo lisibles en http:// pour l'aperçu du composeur
# (le HTML de production, lui, garde ses chemins file://).
app.mount(VAULT_MOUNT, StaticFiles(directory=str(storage.VAULT_ROOT)), name="vault")


class ChargeEnregistrement(BaseModel):
    """Corps du POST : le document complet + ses calques déjà structurés par
    l'éditeur (le navigateur a le DOM, inutile de re-parser le HTML côté
    serveur).

    `regenerer` : le HTML envoyé est un rendu de travail (aperçu du composeur,
    servi en http://) qu'il ne faut pas figer dans `output/`. On ne garde alors
    que les calques et on reconstruit l'artefact depuis `content.yaml`.
    """

    html: str
    calques: list[Calque] = Field(default_factory=list)
    regenerer: bool = False


# Le HTML autonome est ouvert en file:// : il appelle ce service avec
# « Origin: null », d'où un CORS ouvert. Ce mode n'existe qu'en dev ; en
# production l'annotation passe par le composeur, servi par ce même domaine,
# et aucune autre origine n'a à appeler l'API.
if REGLAGES.editeur_autonome:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )


def _output_dir(article_id: str):
    """Résout le dossier de sortie en refusant tout identifiant qui sortirait
    de `vault-articles/articles/` (traversée de chemin)."""
    base = (storage.VAULT_ROOT / "articles").resolve()
    a_dir = storage.article_dir(article_id).resolve()
    if base not in a_dir.parents or not storage.content_path(article_id).is_file():
        raise HTTPException(status_code=404, detail=f"Tutoriel inconnu : {article_id}")
    return a_dir / "output"


@app.get("/sante")
def sante() -> dict:
    """Healthcheck (Docker, Envoy) : public, ne révèle rien."""
    return {"ok": True}


@app.post("/articles/{article_id}/html")
async def enregistrer_html(article_id: str, charge: ChargeEnregistrement) -> dict:
    """Écrase `output/article.html`, régénère le PDF, et persiste les calques.

    Les calques sont enregistrés à part, dans `retouches.yaml` : c'est ce qui
    leur permet de survivre à une régénération (changement de charte, correction
    du content.yaml). Le HTML écrit reste un cache — il est reconstruit à
    l'identique par `generate`.
    """
    if "<html" not in charge.html.lower():
        raise HTTPException(status_code=400, detail="Champ `html` : document HTML attendu.")

    out_dir = _output_dir(article_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "article.html"

    calques = [c.model_copy(update={"html": assainir_html(c.html)}) for c in charge.calques]
    storage.write_retouches(article_id, Retouches(calques=calques))

    pdf_erreur = None
    if charge.regenerer:
        # Aperçu du composeur : on rebâtit depuis la source, calques réinjectés.
        resultat = generate_article(article_id)
        pdf_erreur = resultat.pdf_error
    else:
        storage.ecrire_atomique(html_path, charge.html)
        try:
            convert_to_pdf(html_path, out_dir)
        except PdfConversionError as exc:
            pdf_erreur = str(exc)
        _marquer_retouche(article_id)
    return {
        "html": str(html_path),
        "pdf": None if pdf_erreur else str(out_dir / "article.pdf"),
        "pdf_erreur": pdf_erreur,
        "calques": len(calques),
    }


def _marquer_retouche(article_id: str) -> None:
    """Trace la retouche dans meta.yaml. Le marqueur disparaît à la prochaine
    génération (`write_meta` reconstruit le fichier) : il ne signale donc qu'un
    HTML plus récent que son content.yaml."""
    meta = storage.load_meta(article_id)
    if meta is None:
        return
    storage.write_meta_model(meta.model_copy(update={"retouche_html_le": date.today()}))
