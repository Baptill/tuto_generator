"""Orchestration : content.yaml → article.html + article.pdf + meta.yaml.

Voir CLAUDE.md, Étape 1, flux détaillé (§3 de la note d'origine).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app import storage
from app.pdf import PdfConversionError, convert_to_pdf
from app.renderer import render_article
from app.validation import validate_article


@dataclass
class BuildResult:
    article_id: str
    html_path: Path
    pdf_path: Path | None
    pdf_error: str | None
    hash_contenu: str


def generate_article(article_id: str, skip_pdf: bool = False) -> BuildResult:
    article, raw_content = storage.load_article(article_id)
    config = storage.load_template_config(article.template_id)
    charte = storage.load_charte()

    a_dir = storage.article_dir(article_id)
    report = validate_article(article, config, assets_dir=a_dir)
    report.raise_if_errors()

    template_path = storage.template_file_path(article.template_id, config.fichier)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template introuvable : {template_path}")

    output_dir = storage.article_output_dir(article_id)
    html_path = output_dir / "article.html"
    render_article(
        article=article,
        config=config,
        charte=charte,
        template_path=template_path,
        article_dir=a_dir,
        output_path=html_path,
    )

    pdf_path: Path | None = None
    pdf_error: str | None = None
    if not skip_pdf:
        try:
            pdf_path = convert_to_pdf(html_path, output_dir)
        except PdfConversionError as exc:
            pdf_error = str(exc)

    hash_contenu = storage.compute_hash_contenu(raw_content)
    storage.write_meta(
        article_id=article_id,
        template_id=article.template_id,
        charte_version=charte.version,
        hash_contenu=hash_contenu,
    )

    return BuildResult(
        article_id=article_id,
        html_path=html_path,
        pdf_path=pdf_path,
        pdf_error=pdf_error,
        hash_contenu=hash_contenu,
    )
