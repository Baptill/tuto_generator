"""Connexion / déconnexion et garde d'accès (voir app/auth.py).

Le middleware protège **toutes** les routes — y compris les fichiers bruts du
vault servis sous `/vault` — sauf la page de connexion, le healthcheck et le
code statique de l'interface (`/ui`, sans donnée). Une navigation non
authentifiée est redirigée vers la connexion ; un appel d'API reçoit un 401,
que le composeur transforme lui-même en redirection.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from app import auth
from app.config import REGLAGES

log = logging.getLogger("tuto.auth")

router = APIRouter()

# Seules routes accessibles sans session : la connexion elle-même, le
# healthcheck (Docker, Envoy) et le code statique de l'interface.
CHEMINS_PUBLICS = {"/connexion", "/sante"}
PREFIXE_PUBLIC = "/ui/"


def _ip(request: Request) -> str:
    # Derrière Envoy, uvicorn --proxy-headers renseigne request.client.
    return request.client.host if request.client else "?"


def _suite_sure(suite: str | None) -> str:
    """Retour après connexion : chemin local uniquement (pas de redirection
    ouverte vers un autre site via `//domaine` ou `https://…`)."""
    if suite and suite.startswith("/") and not suite.startswith("//") and "\\" not in suite:
        return suite
    return "/"


async def garde(request: Request, call_next) -> Response:
    request.state.compte = None
    if not REGLAGES.auth_active:
        return await call_next(request)
    chemin = request.url.path
    if chemin in CHEMINS_PUBLICS or chemin.startswith(PREFIXE_PUBLIC):
        return await call_next(request)
    compte = auth.lire_jeton(request.cookies.get(auth.NOM_COOKIE))
    if compte is None:
        if chemin.startswith(("/api/", "/articles/", "/vault/")):
            return JSONResponse({"detail": "Authentification requise."}, status_code=401)
        return RedirectResponse(f"/connexion?suite={quote(chemin)}", status_code=303)
    request.state.compte = compte
    return await call_next(request)


@router.get("/connexion", include_in_schema=False)
def page_connexion() -> FileResponse:
    from app.composer import UI_DIR

    return FileResponse(UI_DIR / "connexion.html")


@router.post("/connexion", include_in_schema=False)
async def se_connecter(
    request: Request,
    identifiant: str = Form(...),
    mot_de_passe: str = Form(...),
    suite: str = Form("/"),
) -> Response:
    # scrypt est volontairement coûteux : hors de la boucle d'événements.
    compte = await asyncio.to_thread(auth.authentifier, identifiant.strip(), mot_de_passe)
    if compte is None:
        log.warning("connexion refusée pour « %s » depuis %s", identifiant, _ip(request))
        await asyncio.sleep(1)  # freine les essais en rafale
        return RedirectResponse(
            f"/connexion?erreur=1&suite={quote(_suite_sure(suite))}", status_code=303
        )
    log.info("connexion de %s depuis %s", compte.identifiant, _ip(request))
    reponse = RedirectResponse(_suite_sure(suite), status_code=303)
    reponse.set_cookie(
        auth.NOM_COOKIE,
        auth.emettre_jeton(compte),
        max_age=REGLAGES.duree_session_h * 3600,
        httponly=True,
        secure=REGLAGES.production,
        samesite="lax",
        path="/",
    )
    return reponse


@router.post("/deconnexion", include_in_schema=False)
def se_deconnecter(request: Request) -> Response:
    compte = request.state.compte
    if compte:
        log.info("déconnexion de %s", compte.identifiant)
    reponse = RedirectResponse("/connexion", status_code=303)
    reponse.delete_cookie(auth.NOM_COOKIE, path="/")
    return reponse


@router.get("/api/moi")
def moi(request: Request) -> dict:
    """Utilisateur connecté (l'auteur par défaut d'un nouveau tutoriel)."""
    compte = request.state.compte
    if compte is None:
        return {"auth": REGLAGES.auth_active, "identifiant": None, "nom": None}
    return {"auth": True, "identifiant": compte.identifiant, "nom": compte.nom}
