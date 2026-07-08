"""Grille de page en 4 hauteurs (voir CLAUDE.md §3, « Sections modulaires »).

Le moteur empile les sections dans l'ordre du `content.yaml` et déclenche un
saut de page dès que la section suivante ferait dépasser 4 unités de hauteur
sur la page courante. Ce module ne fait que le regroupement ; le rendu Word
(saut de page effectif) est géré par `app.renderer`.
"""
from __future__ import annotations

from app.schemas import Section

PAGE_HEIGHT_UNITS = 4


def paginate(sections: list[Section]) -> list[list[Section]]:
    """Regroupe les sections en pages selon la règle de la grille 4 hauteurs.

    Une section dont la hauteur dépasse à elle seule PAGE_HEIGHT_UNITS ne
    devrait jamais arriver (contrainte du schéma : hauteur ∈ [1,4]), mais on
    la protège en la plaçant seule sur sa page.
    """
    pages: list[list[Section]] = []
    current_page: list[Section] = []
    current_height = 0

    for section in sections:
        if current_page and current_height + section.hauteur > PAGE_HEIGHT_UNITS:
            pages.append(current_page)
            current_page = []
            current_height = 0
        current_page.append(section)
        current_height += section.hauteur

    if current_page:
        pages.append(current_page)

    return pages
