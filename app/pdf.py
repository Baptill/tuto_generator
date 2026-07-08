"""Conversion Word → PDF via LibreOffice headless (voir CLAUDE.md §3 et Risques).

Le serveur cible est Linux sans MS Office : LibreOffice headless est le moteur
figé du projet. En local (poste de dev sans LibreOffice), la conversion échoue
proprement avec un message explicite plutôt qu'une trace confuse.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SOFFICE_BIN_CANDIDATES = ["soffice", "libreoffice"]

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault-articles"
CHARTE_FONTS_DIR = VAULT_ROOT / "charte" / "fonts"


class PdfConversionError(Exception):
    pass


def _find_soffice() -> str | None:
    for candidate in SOFFICE_BIN_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def convert_to_pdf(docx_path: Path, out_dir: Path, timeout: int = 120) -> Path:
    """Convertit `docx_path` en PDF dans `out_dir` via `soffice --headless`.

    Retourne le chemin du PDF généré. Lève `PdfConversionError` si LibreOffice
    est introuvable ou si la conversion échoue.
    """
    soffice = _find_soffice()
    if soffice is None:
        raise PdfConversionError(
            "LibreOffice (soffice) est introuvable sur cette machine. "
            "Installer LibreOffice headless sur le serveur de génération "
            "(voir CLAUDE.md §6, risque « Fidélité PDF »)."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]
    env = os.environ.copy()
    if CHARTE_FONTS_DIR.is_dir():
        # SAL_FONTS_PATH indique à LibreOffice un répertoire de polices
        # supplémentaires — utile sur le serveur Linux où les polices de la
        # charte ne sont pas installées au niveau système.
        existing = env.get("SAL_FONTS_PATH", "")
        env["SAL_FONTS_PATH"] = f"{CHARTE_FONTS_DIR}:{existing}" if existing else str(CHARTE_FONTS_DIR)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise PdfConversionError(
            f"Échec de la conversion PDF pour {docx_path.name} : "
            f"{result.stderr or result.stdout}"
        )

    pdf_path = out_dir / (docx_path.stem + ".pdf")
    if not pdf_path.is_file():
        raise PdfConversionError(
            f"Conversion annoncée réussie mais fichier PDF absent : {pdf_path}"
        )
    return pdf_path
