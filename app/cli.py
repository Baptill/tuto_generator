"""CLI MVP de l'Étape 1 (voir CLAUDE.md, « UI MVP »).

Usage :
    python -m app.cli generate 2026-07-exemple-tuto
    python -m app.cli generate 2026-07-exemple-tuto --skip-pdf
"""
from __future__ import annotations

import typer

from app.build import generate_article
from app.validation import ContentValidationError

app = typer.Typer(add_completion=False)


@app.command()
def generate(article_id: str, skip_pdf: bool = typer.Option(False, help="Ne pas tenter la conversion PDF.")):
    """Génère le docx (+ pdf) d'un article depuis son content.yaml."""
    try:
        result = generate_article(article_id, skip_pdf=skip_pdf)
    except ContentValidationError as exc:
        typer.secho("Contenu invalide :", fg=typer.colors.RED, bold=True)
        for error in exc.errors:
            typer.echo(f"  - {error}")
        raise typer.Exit(code=1)

    typer.secho(f"docx  → {result.docx_path}", fg=typer.colors.GREEN)
    if result.pdf_path:
        typer.secho(f"pdf   → {result.pdf_path}", fg=typer.colors.GREEN)
    elif result.pdf_error:
        typer.secho(f"pdf   → échec : {result.pdf_error}", fg=typer.colors.YELLOW)
    typer.echo(f"hash_contenu = {result.hash_contenu}")


if __name__ == "__main__":
    app()
