"""Conversion HTML → PDF via WeasyPrint (voir CLAUDE.md §3 et Risques).

WeasyPrint est un moteur de rendu CSS paged-media pur Python : pas de navigateur
ni de LibreOffice à installer, fonctionne tel quel sur le serveur Linux. Les
polices de la charte sont déclarées en `@font-face` dans le HTML (chemins
absolus vers `charte/fonts/`), donc la fidélité ne dépend pas des polices
installées au niveau système.
"""
from __future__ import annotations

import os
from pathlib import Path


class PdfConversionError(Exception):
    pass


def convert_to_pdf(html_path: Path, out_dir: Path) -> Path:
    """Convertit `html_path` en PDF dans `out_dir` via WeasyPrint.

    Retourne le chemin du PDF généré. Lève `PdfConversionError` en cas d'échec
    (WeasyPrint absent, ou erreur de rendu).
    """
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise PdfConversionError(
            "WeasyPrint est introuvable. Installer la dépendance "
            "(`pip install weasyprint`) sur la machine de génération "
            "(voir CLAUDE.md §6, risque « Fidélité PDF »)."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (html_path.stem + ".pdf")
    # Rendu dans un fichier voisin puis renommage : un PDF téléchargé pendant
    # une régénération est toujours l'ancien ou le nouveau, jamais un fragment.
    tmp_path = out_dir / f".{pdf_path.name}.tmp"
    try:
        HTML(filename=str(html_path)).write_pdf(str(tmp_path))
        os.replace(tmp_path, pdf_path)
    except Exception as exc:  # noqa: BLE001 - on remonte un message propre
        tmp_path.unlink(missing_ok=True)
        raise PdfConversionError(
            f"Échec de la conversion PDF pour {html_path.name} : {exc}"
        ) from exc

    if not pdf_path.is_file():
        raise PdfConversionError(
            f"Conversion annoncée réussie mais fichier PDF absent : {pdf_path}"
        )
    return pdf_path
