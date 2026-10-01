"""Authentification — comptes locaux et session par cookie signé.

Dimensionné pour une petite équipe interne : pas d'inscription, pas de rôles.
Les comptes sont créés en ligne de commande (`python -m app.cli compte-ajouter`)
et rangés dans un fichier YAML *hors* du vault (le vault est servi en statique).

- Mots de passe : `scrypt` de la bibliothèque standard, sel aléatoire par
  compte — aucune dépendance supplémentaire.
- Session : cookie `HttpOnly` + `SameSite=Lax` (+ `Secure` en production),
  contenant l'identifiant et l'échéance, signé en HMAC-SHA256 avec
  `TUTO_SECRET_KEY`. Changer la clé déconnecte tout le monde.
- `SameSite=Lax` suffit contre la falsification de requête (CSRF) : un site
  tiers ne peut pas faire émettre au navigateur un POST portant le cookie.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import REGLAGES

NOM_COOKIE = "tuto_session"

# scrypt : n=2^14, r=8, p=1 — ~16 Mo et quelques dizaines de ms par essai.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


@dataclass(frozen=True)
class Compte:
    identifiant: str
    nom: str
    hash: str


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------

def hacher(mot_de_passe: str) -> str:
    sel = os.urandom(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode(), salt=sel, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${sel}${emp}".format(
        **_SCRYPT, sel=sel.hex(), emp=empreinte.hex()
    )


def verifier(mot_de_passe: str, hache: str) -> bool:
    try:
        algo, n, r, p, sel, emp = hache.split("$")
        if algo != "scrypt":
            return False
        calcule = hashlib.scrypt(
            mot_de_passe.encode(), salt=bytes.fromhex(sel), dklen=len(emp) // 2,
            n=int(n), r=int(r), p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calcule.hex(), emp)


# ---------------------------------------------------------------------------
# Fichier des comptes
# ---------------------------------------------------------------------------

def _fichier() -> Path:
    return REGLAGES.comptes_fichier


def charger_comptes() -> dict[str, Compte]:
    path = _fichier()
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        c["identifiant"]: Compte(c["identifiant"], c.get("nom") or c["identifiant"], c["hash"])
        for c in data.get("comptes", [])
    }


def _ecrire_comptes(comptes: dict[str, Compte]) -> None:
    from app.storage import ecrire_atomique

    data = {"comptes": [c.__dict__ for c in comptes.values()]}
    ecrire_atomique(_fichier(), yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    os.chmod(_fichier(), 0o600)


def enregistrer_compte(identifiant: str, nom: str, mot_de_passe: str) -> bool:
    """Crée le compte, ou remplace son mot de passe s'il existe. Retourne True
    si le compte est nouveau."""
    comptes = charger_comptes()
    nouveau = identifiant not in comptes
    comptes[identifiant] = Compte(identifiant, nom or identifiant, hacher(mot_de_passe))
    _ecrire_comptes(comptes)
    return nouveau


def supprimer_compte(identifiant: str) -> bool:
    comptes = charger_comptes()
    if comptes.pop(identifiant, None) is None:
        return False
    _ecrire_comptes(comptes)
    return True


def authentifier(identifiant: str, mot_de_passe: str) -> Compte | None:
    compte = charger_comptes().get(identifiant)
    if compte is None:
        # Même coût de calcul qu'un vrai essai : ne pas révéler par le temps de
        # réponse qu'un identifiant n'existe pas.
        hacher(mot_de_passe)
        return None
    return compte if verifier(mot_de_passe, compte.hash) else None


# ---------------------------------------------------------------------------
# Jeton de session
# ---------------------------------------------------------------------------

def _b64(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()


def _signature(charge: str) -> str:
    return _b64(hmac.new(REGLAGES.cle_session.encode(), charge.encode(), hashlib.sha256).digest())


def emettre_jeton(compte: Compte) -> str:
    echeance = int(time.time()) + REGLAGES.duree_session_h * 3600
    charge = _b64(json.dumps({"u": compte.identifiant, "exp": echeance}).encode())
    return f"{charge}.{_signature(charge)}"


def lire_jeton(jeton: str | None) -> Compte | None:
    """Compte associé à un jeton valide, non expiré, dont le compte existe
    encore (supprimer un compte coupe ses sessions en cours)."""
    if not jeton or "." not in jeton:
        return None
    charge, signature = jeton.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(charge)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(charge + "=" * (-len(charge) % 4)))
    except (ValueError, TypeError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    return charger_comptes().get(data.get("u"))
