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


@app.command()
def serve(
    port: int = typer.Option(None, help="Port d'écoute (défaut : 8765)."),
    host: str = typer.Option("127.0.0.1", help="Interface d'écoute (0.0.0.0 en conteneur)."),
):
    """Lance le service local : composeur (UI de saisie) + enregistrement des
    retouches.

    Le composeur est servi sur `/` (voir app/composer.py) ; l'endpoint
    d'enregistrement permet au bouton « Enregistrer HTML » de l'aperçu
    d'écraser output/article.html et de régénérer le PDF (voir app/serveur.py).
    """
    import uvicorn

    from app.serveur_config import PORT_DEFAUT

    port = port or PORT_DEFAUT
    typer.secho(f"Composeur          → http://{host}:{port}/", fg=typer.colors.GREEN)
    typer.secho(f"Retouches (API)    → http://{host}:{port}/articles/<id>/html", fg=typer.colors.BLUE)
    uvicorn.run("app.serveur:app", host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Administration (production : `docker compose exec app python -m app.cli …`)
# ---------------------------------------------------------------------------


@app.command("compte-ajouter")
def compte_ajouter(
    identifiant: str,
    nom: str = typer.Option("", help="Nom affiché (auteur par défaut des tutoriels)."),
):
    """Crée un compte, ou change le mot de passe d'un compte existant."""
    from app import auth

    mot_de_passe = typer.prompt("Mot de passe", hide_input=True, confirmation_prompt=True)
    if len(mot_de_passe) < 10:
        typer.secho("Mot de passe trop court (10 caractères minimum).", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    nouveau = auth.enregistrer_compte(identifiant, nom, mot_de_passe)
    typer.secho(
        f"Compte « {identifiant} » {'créé' if nouveau else 'mis à jour'}.", fg=typer.colors.GREEN
    )


@app.command("compte-supprimer")
def compte_supprimer(identifiant: str):
    """Supprime un compte. Ses sessions en cours cessent aussitôt d'être valides."""
    from app import auth

    if not auth.supprimer_compte(identifiant):
        typer.secho(f"Compte « {identifiant} » introuvable.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(f"Compte « {identifiant} » supprimé.", fg=typer.colors.GREEN)


@app.command("comptes")
def comptes():
    """Liste les comptes."""
    from app import auth

    liste = auth.charger_comptes()
    if not liste:
        typer.echo("Aucun compte. Créer : python -m app.cli compte-ajouter <identifiant>")
    for c in liste.values():
        typer.echo(f"{c.identifiant:20} {c.nom}")


@app.command("init-vault")
def init_vault():
    """Prépare le dossier de données (TUTO_VAULT_DIR) au démarrage du conteneur.

    Crée l'arborescence, puis synchronise `templates/` et `charte/` depuis ceux
    livrés avec le code : dans cette version, charte et templates ne se
    modifient pas depuis l'interface — les changer, c'est modifier le dépôt et
    redéployer. `articles/` n'est jamais touché.
    """
    import shutil

    from app.config import RACINE_PROJET
    from app.storage import VAULT_ROOT

    source = RACINE_PROJET / "vault-articles"
    (VAULT_ROOT / "articles").mkdir(parents=True, exist_ok=True)
    if source.resolve() == VAULT_ROOT.resolve():
        typer.echo(f"Vault : {VAULT_ROOT} (celui du dépôt, rien à synchroniser)")
        return
    for dossier in ("templates", "charte"):
        cible = VAULT_ROOT / dossier
        if cible.exists():
            shutil.rmtree(cible)
        shutil.copytree(source / dossier, cible)
    nb = sum(1 for d in (VAULT_ROOT / "articles").iterdir() if (d / "content.yaml").is_file())
    typer.echo(f"Vault : {VAULT_ROOT} — templates et charte à jour, {nb} tutoriel(s).")


@app.command("generer-tout")
def generer_tout(skip_pdf: bool = typer.Option(False, help="Ne pas produire les PDF.")):
    """Régénère tous les tutoriels (après un changement de charte ou de template)."""
    ok, echecs = 0, []
    for article_id in storage.list_article_ids():
        try:
            result = generate_article(article_id, skip_pdf=skip_pdf)
        except (ContentValidationError, ValueError) as exc:
            echecs.append(article_id)
            typer.secho(f"✗ {article_id} : {exc}", fg=typer.colors.RED)
            continue
        ok += 1
        etat = f" (PDF : {result.pdf_error})" if result.pdf_error else ""
        typer.echo(f"✓ {article_id}{etat}")
    typer.echo(f"{ok} tutoriel(s) régénéré(s), {len(echecs)} échec(s).")
    if echecs:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
