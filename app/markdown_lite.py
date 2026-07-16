"""Markdown léger → HTML (voir CLAUDE.md, Étape 1).

Supporté volontairement minimal :
- **gras**
- lignes commençant par « - » ou « * » → liste à puces
- paragraphes séparés par des lignes vides

Tout le reste est traité comme du texte brut. Pas de markdown imbriqué, pas de
liens, pas de listes numérotées — à étendre si le besoin apparaît en pratique.
"""
from __future__ import annotations

import re
from html import escape
from typing import Iterable

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")


def _inline_to_html(text: str) -> str:
    """Échappe le texte puis réinjecte les **gras** en <strong>."""
    parts: list[str] = []
    pos = 0
    for match in _BOLD_RE.finditer(text):
        if match.start() > pos:
            parts.append(escape(text[pos : match.start()]))
        parts.append(f"<strong>{escape(match.group(1))}</strong>")
        pos = match.end()
    if pos < len(text):
        parts.append(escape(text[pos:]))
    return "".join(parts)


def _split_blocks(texte: str) -> Iterable[tuple[str, list[str]]]:
    """Regroupe les lignes en blocs ('paragraphe' | 'liste', [lignes])."""
    lines = texte.strip("\n").splitlines()
    blocks: list[tuple[str, list[str]]] = []
    current_kind: str | None = None
    buffer: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if buffer:
                blocks.append((current_kind or "paragraphe", buffer))
                buffer = []
                current_kind = None
            continue
        bullet_match = _BULLET_RE.match(line)
        kind = "liste" if bullet_match else "paragraphe"
        content = bullet_match.group(1) if bullet_match else line
        if buffer and kind != current_kind:
            blocks.append((current_kind or "paragraphe", buffer))
            buffer = []
        current_kind = kind
        buffer.append(content)
    if buffer:
        blocks.append((current_kind or "paragraphe", buffer))
    return blocks


def markdown_to_html(texte: str, paragraph_class: str = "corps") -> str:
    """Convertit `texte` (markdown léger) en fragment HTML.

    Les paragraphes reçoivent la classe `paragraph_class`, les listes deviennent
    des <ul><li>. Le texte est systématiquement échappé (sécurité + fidélité).
    """
    out: list[str] = []
    for kind, lines in _split_blocks(texte):
        if kind == "liste":
            items = "".join(f"<li>{_inline_to_html(line)}</li>" for line in lines)
            out.append(f'<ul class="{paragraph_class}">{items}</ul>')
        else:
            joined = _inline_to_html(" ".join(lines))
            out.append(f'<p class="{paragraph_class}">{joined}</p>')
    return "".join(out)
