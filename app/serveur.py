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

import re
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import storage
from app.pdf import PdfConversionError, convert_to_pdf
from app.schemas import Calque, Retouches
from app.serveur_config import PORT_DEFAUT  # noqa: F401 — réexport pour la CLI

app = FastAPI(title="tuto-generator — enregistrement des retouches")


class ChargeEnregistrement(BaseModel):
    """Corps du POST : le document complet + ses calques déjà structurés par
    l'éditeur (le navigateur a le DOM, inutile de re-parser le HTML côté
    serveur)."""

    html: str
    calques: list[Calque] = Field(default_factory=list)


# L'aperçu est ouvert en file:// : le navigateur envoie « Origin: null ».
# Service lié à la boucle locale uniquement (voir `python -m app.cli serve`).
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
        raise HTTPException(status_code=404, detail=f"Article inconnu : {article_id}")
    return a_dir / "output"


@app.get("/sante")
def sante() -> dict:
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
    html_path.write_text(charge.html, encoding="utf-8")

    calques = [c.model_copy(update={"html": _assainir(c.html)}) for c in charge.calques]
    storage.write_retouches(article_id, Retouches(calques=calques))

    pdf_erreur = None
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


_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
_HANDLER_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)


def _assainir(html: str) -> str:
    """Le contenu d'un calque est saisi dans le navigateur puis réinjecté à
    chaque build : on en retire scripts et gestionnaires d'événements avant de
    le persister."""
    return _HANDLER_RE.sub("", _SCRIPT_RE.sub("", html))


def _marquer_retouche(article_id: str) -> None:
    """Trace la retouche dans meta.yaml. Le marqueur disparaît à la prochaine
    génération (`write_meta` reconstruit le fichier) : il ne signale donc qu'un
    HTML plus récent que son content.yaml."""
    meta = storage.load_meta(article_id)
    if meta is None:
        return
    storage.write_meta_model(meta.model_copy(update={"retouche_html_le": date.today()}))
