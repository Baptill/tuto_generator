"""Réglages de l'application, lus dans l'environnement (voir DEPLOIEMENT.md).

Deux modes :

- **dev** (défaut) : comportement historique en local — pas d'authentification,
  vault dans le dépôt (`vault-articles/`), HTML autonome ré-éditable ouvert en
  `file://` (d'où CORS ouvert), documentation `/docs` accessible ;
- **production** (`TUTO_ENV=production`) : authentification obligatoire, clé de
  session exigée au démarrage, cookies `Secure`, pas de CORS, pas de `/docs`,
  et HTML produit sans barre d'édition (l'annotation se fait dans le composeur).

Chaque réglage peut être forcé individuellement par sa variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RACINE_PROJET = Path(__file__).resolve().parent.parent


def _booleen(nom: str, defaut: bool) -> bool:
    valeur = os.environ.get(nom)
    if valeur is None or valeur == "":
        return defaut
    return valeur.strip().lower() in {"1", "true", "oui", "yes", "on"}


@dataclass
class Reglages:
    production: bool
    vault_dir: Path
    comptes_fichier: Path
    cle_session: str
    auth_active: bool
    editeur_autonome: bool
    duree_session_h: int
    niveau_log: str


def charger() -> Reglages:
    production = os.environ.get("TUTO_ENV", "dev").strip().lower() == "production"
    cle = os.environ.get("TUTO_SECRET_KEY", "")
    if production and len(cle) < 32:
        raise RuntimeError(
            "TUTO_SECRET_KEY absente ou trop courte (32 caractères minimum). "
            "Générer : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return Reglages(
        production=production,
        vault_dir=Path(os.environ.get("TUTO_VAULT_DIR") or RACINE_PROJET / "vault-articles"),
        comptes_fichier=Path(os.environ.get("TUTO_COMPTES") or RACINE_PROJET / ".comptes.yaml"),
        # En dev, une clé éphémère suffit : les sessions ne survivent pas à un
        # redémarrage, ce qui est sans conséquence en local.
        cle_session=cle or os.urandom(32).hex(),
        auth_active=_booleen("TUTO_AUTH", production),
        editeur_autonome=_booleen("TUTO_EDITEUR_AUTONOME", not production),
        duree_session_h=int(os.environ.get("TUTO_SESSION_HEURES", "168")),
        niveau_log=os.environ.get("TUTO_LOG_LEVEL", "INFO").upper(),
    )


REGLAGES = charger()
