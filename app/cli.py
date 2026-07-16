"""CLI MVP de l'Étape 1 (voir CLAUDE.md, « UI MVP »).

Usage :
    python -m app.cli generate 2026-07-exemple-tuto
    python -m app.cli generate 2026-07-exemple-tuto --skip-pdf
    python -m app.cli pdf 2026-07-exemple-tuto
    python -m app.cli pdf 2026-07-exemple-tuto --html ~/Downloads/article.html
"""
from __future__ import annotations

from pathlib import Path

import typer

from app import storage
from app.build import generate_article
from app.pdf import PdfConversionError, convert_to_pdf
from app.validation import ContentValidationError

app = typer.Typer(add_completion=False)


@app.command()
def generate(article_id: str, skip_pdf: bool = typer.Option(False, help="Ne pas tenter la conversion PDF.")):
    """Génère le HTML (+ pdf) d'un article depuis son content.yaml."""
    try:
        result = generate_article(article_id, skip_pdf=skip_pdf)
    except ContentValidationError as exc:
        typer.secho("Contenu invalide :", fg=typer.colors.RED, bold=True)
        for error in exc.errors:
            typer.echo(f"  - {error}")
        raise typer.Exit(code=1)

    typer.secho(f"html  → {result.html_path}", fg=typer.colors.GREEN)
    if result.pdf_path:
        typer.secho(f"pdf   → {result.pdf_path}", fg=typer.colors.GREEN)
    elif result.pdf_error:
        typer.secho(f"pdf   → échec : {result.pdf_error}", fg=typer.colors.YELLOW)
    typer.echo(f"hash_contenu = {result.hash_contenu}")


@app.command()
def pdf(
    article_id: str,
    html: str = typer.Option(
        None,
        help="Chemin du HTML à convertir (défaut : output/article.html de l'article). "
        "Utile pour reconvertir un HTML retouché à la main (mode édition navigateur).",
    ),
):
    """Reconvertit un HTML (éventuellement édité) en PDF, sans repasser par
    content.yaml. Régénère uniquement le PDF depuis l'artefact HTML existant."""
    output_dir = storage.article_output_dir(article_id)
    html_path = Path(html).expanduser() if html else output_dir / "article.html"
    if not html_path.is_file():
        typer.secho(f"HTML introuvable : {html_path}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)

    try:
        pdf_path = convert_to_pdf(html_path, output_dir)
    except PdfConversionError as exc:
        typer.secho(f"pdf   → échec : {exc}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)

    typer.secho(f"html  → {html_path}", fg=typer.colors.BLUE)
    typer.secho(f"pdf   → {pdf_path}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
