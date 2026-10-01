"""Journalisation : une ligne lisible par événement, sur la sortie standard.

En production, `docker compose logs -f` suffit à suivre l'activité :
connexions, enregistrements (qui, quoi, durée), téléversements, échecs de
génération. Niveau réglable par `TUTO_LOG_LEVEL` (INFO par défaut).
"""
from __future__ import annotations

import logging
import sys

from app.config import REGLAGES

FORMAT = "%(asctime)s %(levelname)-7s %(name)-14s %(message)s"


def configurer() -> None:
    racine = logging.getLogger("tuto")
    if racine.handlers:  # déjà configuré (rechargement, tests)
        return
    gestionnaire = logging.StreamHandler(sys.stdout)
    gestionnaire.setFormatter(logging.Formatter(FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    racine.addHandler(gestionnaire)
    racine.setLevel(REGLAGES.niveau_log)
    racine.propagate = False
    # WeasyPrint signale chaque propriété CSS qu'il ignore : bruit sans intérêt
    # en exploitation.
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
