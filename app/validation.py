"""Validation d'un `content.yaml` contre le `config.yaml` de son template
(voir CLAUDE.md — Étape 1, lot « Socle & schéma »).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.schemas import Article, BlocImage, BlocParagraphe, TemplateConfig


class ContentValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.errors.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_errors(self) -> None:
        if self.errors:
            raise ContentValidationError(self.errors)


def validate_article(article: Article, config: TemplateConfig, assets_dir: Path | None = None) -> ValidationReport:
    report = ValidationReport()

    if len(article.titre) > config.contraintes.titre.max_caracteres:
        report.add(
            f"Titre trop long ({len(article.titre)} caractères, max "
            f"{config.contraintes.titre.max_caracteres})."
        )

    nb_sections = len(article.sections)
    if nb_sections < config.sections_attendues.min:
        report.add(
            f"Trop peu de sections ({nb_sections}, minimum {config.sections_attendues.min})."
        )
    if nb_sections > config.sections_attendues.max:
        report.add(
            f"Trop de sections ({nb_sections}, maximum {config.sections_attendues.max})."
        )

    formats_ok = {f.lower() for f in config.image.formats_acceptes}

    ids_vus: set[str] = set()
    for section in article.sections:
        if section.id in ids_vus:
            report.add(f"Section id dupliqué : '{section.id}'.")
        ids_vus.add(section.id)

        for bloc in section.blocs:
            if isinstance(bloc, BlocParagraphe):
                if len(bloc.texte) > config.contraintes.section_texte.max_caracteres:
                    report.add(
                        f"Section '{section.id}' : paragraphe trop long "
                        f"({len(bloc.texte)} caractères, max "
                        f"{config.contraintes.section_texte.max_caracteres})."
                    )
            elif isinstance(bloc, BlocImage):
                ext = Path(bloc.fichier).suffix.lstrip(".").lower()
                if ext not in formats_ok:
                    report.add(
                        f"Section '{section.id}' : format d'image '.{ext}' non accepté "
                        f"(formats acceptés : {sorted(formats_ok)})."
                    )
                if assets_dir is not None and not (assets_dir / bloc.fichier).is_file():
                    report.add(
                        f"Section '{section.id}' : fichier image introuvable "
                        f"'{bloc.fichier}' (attendu dans {assets_dir})."
                    )

    return report
