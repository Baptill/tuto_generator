"""Réglages partagés du service local d'enregistrement.

Isolé de `app/serveur.py` pour que le moteur de rendu (qui injecte l'URL de
l'endpoint dans le HTML) n'ait pas à importer FastAPI : la génération HTML/PDF
reste utilisable sans le service.
"""
from __future__ import annotations

PORT_DEFAUT = 8765
