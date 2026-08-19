"""Composeur — l'UI de saisie d'un article (CLAUDE.md, Étape 1 « UI MVP »).

L'utilisateur saisit l'en-tête (titre, sous-titre, prérequis) puis empile des
sections choisies dans le catalogue de layouts (`app/catalogue.py`), présenté
sous forme de wireframes avec leur poids. Chaque frappe recompose l'aperçu :
le front POSTe l'article complet, le serveur le rend avec le vrai moteur
(`app/renderer.py`) et renvoie le HTML.

Point d'architecture (§2) : le composeur écrit **`content.yaml`**, jamais le
HTML rendu. L'aperçu n'est pas persisté (aucun fichier écrit tant que
l'utilisateur n'enregistre pas), et l'enregistrement passe par le même
`generate_article` que la CLI — pas de second pipeline.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ValidationError

from app import storage
from app.build import generate_article
from app.catalogue import catalogue_json
from app.editeur import assainir_html
from app.renderer import render_article
from app.schemas import Article, Calque, Retouches
from app.validation import ContentValidationError, validate_article

UI_DIR = Path(__file__).resolve().parent / "ui"

# Préfixe de montage des fichiers du vault (assets, polices, logo) : l'aperçu
# est servi en http://, il ne peut pas lire les file:// du build.
VAULT_MOUNT = "/vault"

router = APIRouter()

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def _valider_id(article_id: str) -> str:
    """Un id d'article est aussi un nom de dossier : on le contraint plutôt que
    de rattraper les traversées de chemin après coup."""
    if not _ID_RE.match(article_id) or ".." in article_id:
        raise HTTPException(status_code=400, detail=f"Identifiant de tutoriel invalide : {article_id}")
    return article_id


def _slug(texte: str) -> str:
    sans_accent = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", sans_accent.lower())).strip("-")


def _article_depuis_charge(charge: dict) -> Article:
    try:
        return Article.model_validate(charge)
    except ValidationError as exc:
        details = [
            f"{'.'.join(str(p) for p in e['loc'])} : {e['msg']}" for e in exc.errors()
        ]
        raise HTTPException(status_code=422, detail=details) from exc


# ---------------------------------------------------------------------------
# Page et catalogue
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def page_composeur() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@router.get("/api/catalogue")
def catalogue(template_id: str = "tuto-release") -> dict:
    """Layouts disponibles (wireframe + poids + champs) et contraintes du
    template, pour construire le panneau « Ajouter une section »."""
    _valider_id(template_id)
    try:
        config = storage.load_template_config(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Template inconnu : {template_id}") from exc
    return {
        "template": {
            "id": config.template_id,
            "libelle": config.libelle,
            "type": config.type,
            "sections_min": config.sections_attendues.min,
            "sections_max": config.sections_attendues.max,
            "formats_images": config.image.formats_acceptes,
        },
        "layouts": catalogue_json(),
    }


@router.get("/api/templates")
def templates() -> list[dict]:
    base = storage.VAULT_ROOT / "templates"
    out = []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        if not (d / "config.yaml").is_file():
            continue
        config = storage.load_template_config(d.name)
        out.append({"id": config.template_id, "libelle": config.libelle, "type": config.type})
    return out


@router.get("/api/articles")
def articles() -> list[dict]:
    out = []
    for article_id in storage.list_article_ids():
        article, _ = storage.load_article(article_id)
        meta = storage.load_meta(article_id)
        out.append({
            "id": article_id,
            "titre": article.titre,
            "sections": len(article.sections),
            "statut": meta.statut if meta else "brouillon",
        })
    return out


@router.get("/api/articles/{article_id}/content")
def contenu(article_id: str) -> dict:
    _valider_id(article_id)
    if not storage.content_path(article_id).is_file():
        raise HTTPException(status_code=404, detail=f"Tutoriel inconnu : {article_id}")
    article, _ = storage.load_article(article_id)
    return article.model_dump(mode="json")


@router.get("/api/id-propose")
def id_propose(titre: str) -> dict:
    """Identifiant proposé pour un nouvel article : AAAA-MM-<slug du titre>."""
    base = f"{date.today():%Y-%m}-{_slug(titre) or 'article'}"[:80]
    candidat, n = base, 2
    while storage.article_dir(candidat).exists():
        candidat = f"{base}-{n}"
        n += 1
    return {"id": candidat}


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


@router.post("/api/articles/{article_id}/assets")
async def televerser_image(
    article_id: str,
    fichier: UploadFile = File(...),
    template_id: str = "tuto-release",
) -> dict:
    """Range l'image dans `articles/<id>/assets/` et renvoie le chemin relatif
    à écrire dans `content.yaml`. Le dossier est créé au premier envoi : un
    article n'existe sur disque qu'à partir du moment où il a du contenu."""
    _valider_id(article_id)
    nom = Path(fichier.filename or "image").name
    ext = Path(nom).suffix.lstrip(".").lower()
    _valider_id(template_id)
    formats = {f.lower() for f in storage.load_template_config(template_id).image.formats_acceptes}
    if ext not in formats:
        raise HTTPException(
            status_code=400,
            detail=f"Format « .{ext} » non accepté (attendus : {sorted(formats)}).",
        )

    assets = storage.article_assets_dir(article_id)
    assets.mkdir(parents=True, exist_ok=True)
    cible = assets / f"{_slug(Path(nom).stem) or 'image'}.{ext}"
    n = 2
    while cible.exists():
        cible = assets / f"{_slug(Path(nom).stem) or 'image'}-{n}.{ext}"
        n += 1
    cible.write_bytes(await fichier.read())
    return {"fichier": f"assets/{cible.name}", "url": _url_asset(article_id, cible.name)}


def _url_asset(article_id: str, nom: str) -> str:
    return f"{VAULT_MOUNT}/articles/{article_id}/assets/{nom}"


# ---------------------------------------------------------------------------
# Aperçu et enregistrement
# ---------------------------------------------------------------------------


class ChargeArticle(BaseModel):
    """Corps des POST du composeur.

    `calques` accompagne l'enregistrement : ce sont les annotations relevées
    dans l'aperçu (`retouches.yaml`). `None` — champ absent — signifie « ne
    touche pas aux retouches existantes », à distinguer d'une liste vide qui,
    elle, les efface.
    """

    article: dict
    calques: list[Calque] | None = None


@router.post("/api/articles/{article_id}/apercu")
def apercu(article_id: str, charge: ChargeArticle, request: Request) -> dict:
    """Rend le tutoriel *tel qu'il est saisi*, sans rien écrire sur disque.

    Aucune validation métier ici (sections minimales, images manquantes) : un
    tutoriel en cours de saisie est incomplet par nature, les contraintes du
    template sont vérifiées à l'enregistrement.

    L'aperçu embarque la surface d'édition (barre + palette d'annotations) et
    les calques déjà posés (`retouches.yaml`) : on retrouve ses annotations en
    rouvrant un tutoriel. L'URL d'enregistrement est celle de *ce* service —
    déduite de la requête, donc juste quel que soit le port d'écoute.

    Si la charge porte des `calques`, ce sont ceux de l'aperçu en cours : ils
    priment sur `retouches.yaml`. C'est ce qui permet à une annotation posée
    mais pas encore enregistrée de survivre au rafraîchissement déclenché par
    la frappe suivante dans le formulaire.
    """
    _valider_id(article_id)
    article = _article_depuis_charge({**charge.article, "id": article_id})
    config = storage.load_template_config(article.template_id)
    template_path = storage.template_file_path(article.template_id, config.fichier)
    if not template_path.is_file():
        raise HTTPException(status_code=404, detail=f"Template introuvable : {template_path}")

    html = render_article(
        article=article,
        config=config,
        charte=storage.load_charte(),
        template_path=template_path,
        article_dir=storage.article_dir(article_id),
        output_path=None,
        retouches=_retouches_de(article_id, charge.calques),
        base_href=f"{VAULT_MOUNT}/articles/{article_id}/",
        charte_base=f"{VAULT_MOUNT}/charte/",
        editeur_api_url=f"{str(request.base_url).rstrip('/')}/articles/{article_id}/html",
        apercu=True,
    )
    return {"html": html, "avertissements": _avertissements(article, config)}


def _retouches_de(article_id: str, calques: list[Calque] | None) -> Retouches:
    """Calques à rendre : ceux de l'aperçu s'ils sont fournis, sinon ceux
    déjà persistés."""
    if calques is None:
        return storage.load_retouches(article_id)
    return Retouches(
        calques=[c.model_copy(update={"html": assainir_html(c.html)}) for c in calques]
    )


def _avertissements(article: Article, config) -> list[str]:
    """Ce qui empêcherait l'enregistrement, affiché sans bloquer la saisie."""
    rapport = validate_article(article, config, assets_dir=storage.article_dir(article.id))
    return rapport.errors


@router.post("/api/articles/{article_id}/enregistrer")
def enregistrer(article_id: str, charge: ChargeArticle, auto: bool = False) -> dict:
    """Écrit `content.yaml` puis relance la génération complète (HTML + PDF).

    Même chemin que `python -m app.cli generate` : le composeur n'est qu'une
    façon de produire la source, pas un pipeline parallèle.

    `auto=1` est l'enregistrement de fond du composeur (dès la saisie du titre,
    puis périodiquement). Il diffère sur deux points, et sur deux seulement :

    - il n'exige pas un tutoriel complet — la source est écrite telle quelle,
      et les manques sont renvoyés en avertissements ; un brouillon reste un
      brouillon valide au sens du schéma, pas au sens du template ;
    - il ne produit pas le PDF (quelques secondes de WeasyPrint), réservé à
      l'enregistrement explicite.
    """
    _valider_id(article_id)
    article = _article_depuis_charge({**charge.article, "id": article_id})
    config = storage.load_template_config(article.template_id)
    rapport = validate_article(article, config, assets_dir=storage.article_dir(article_id))
    if not rapport.ok and not auto:
        return {"ok": False, "erreurs": rapport.errors}

    storage.write_article(article)
    if charge.calques is not None:
        storage.write_retouches(article_id, _retouches_de(article_id, charge.calques))

    if not rapport.ok:
        # Brouillon incomplet : la source est écrite, le rendu attendra.
        return {
            "ok": True,
            "content": str(storage.content_path(article_id)),
            "html": None,
            "pdf": None,
            "avertissements": rapport.errors,
        }

    try:
        result = generate_article(article_id, skip_pdf=auto)
    except ContentValidationError as exc:
        return {"ok": False, "erreurs": exc.errors}

    return {
        "ok": True,
        "content": str(storage.content_path(article_id)),
        "html": str(result.html_path),
        "pdf": str(result.pdf_path) if result.pdf_path else None,
        "pdf_erreur": result.pdf_error,
        "avertissements": [],
    }
