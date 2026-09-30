"""Markdown léger → HTML (voir CLAUDE.md, Étape 1).

Supporté volontairement minimal :
- **gras**
- liens `[texte](https://…)` et adresses nues `https://…` — **http et https
  uniquement** : un lien `javascript:`, `mailto:` ou relatif reste du texte ;
- lignes commençant par « - » ou « * » → liste à puces ;
- lignes commençant par « 1. » ou « 1) » → liste numérotée (la numérotation
  suit celle du premier élément) ;
- paragraphes séparés par des lignes vides.

Tout le reste est traité comme du texte brut, systématiquement échappé.
"""
from __future__ import annotations

import re
from html import escape
from typing import Iterable

# Un seul passage sur le texte brut : chaque fragment reconnu est échappé
# individuellement, jamais le HTML produit.
_INLINE_RE = re.compile(
    r"\*\*(?P<gras>.+?)\*\*"
    r"|\[(?P<lien_texte>[^\]\n]+)\]\((?P<lien_url>https?://[^\s)]+)\)"
    r"|(?P<url>https?://[^\s<>\"]+)"
)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_NUMERO_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+(.*)$")
# Ponctuation finale d'une adresse nue : « voir https://x.fr. » → le point
# termine la phrase, il n'appartient pas au lien.
_PONCTUATION_FINALE = ".,;:!?)»"


def _lien(url: str, texte_html: str) -> str:
    return (
        f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">'
        f"{texte_html}</a>"
    )


def _inline_to_html(text: str) -> str:
    parts: list[str] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        parts.append(escape(text[pos : m.start()]))
        if m.group("gras") is not None:
            parts.append(f"<strong>{_inline_to_html(m.group('gras'))}</strong>")
        elif m.group("lien_url") is not None:
            parts.append(_lien(m.group("lien_url"), escape(m.group("lien_texte"))))
        else:
            url = m.group("url")
            fin = ""
            while url and url[-1] in _PONCTUATION_FINALE:
                fin = url[-1] + fin
                url = url[:-1]
            parts.append(_lien(url, escape(url)) + escape(fin))
        pos = m.end()
    parts.append(escape(text[pos:]))
    return "".join(parts)


def _split_blocks(texte: str) -> Iterable[tuple[str, list[str], int]]:
    """Regroupe les lignes en blocs (type, lignes, numéro de départ)."""
    blocks: list[tuple[str, list[str], int]] = []
    current_kind: str | None = None
    buffer: list[str] = []
    debut = 1

    def vider():
        nonlocal buffer, current_kind
        if buffer:
            blocks.append((current_kind or "paragraphe", buffer, debut))
        buffer = []
        current_kind = None

    for raw_line in texte.strip("\n").splitlines():
        line = raw_line.strip()
        if not line:
            vider()
            continue
        puce = _BULLET_RE.match(line)
        numero = _NUMERO_RE.match(line)
        if puce:
            kind, content = "liste", puce.group(1)
        elif numero:
            kind, content = "numerotee", numero.group(2)
        else:
            kind, content = "paragraphe", line
        if buffer and kind != current_kind:
            vider()
        if not buffer and kind == "numerotee":
            debut = int(numero.group(1))
        current_kind = kind
        buffer.append(content)
    vider()
    return blocks


def markdown_to_html(texte: str, paragraph_class: str = "corps") -> str:
    """Convertit `texte` (markdown léger) en fragment HTML.

    Les paragraphes reçoivent la classe `paragraph_class`, les listes deviennent
    des <ul>/<ol>. Le texte est systématiquement échappé (sécurité + fidélité).
    """
    out: list[str] = []
    for kind, lines, debut in _split_blocks(texte):
        if kind in ("liste", "numerotee"):
            items = "".join(f"<li>{_inline_to_html(line)}</li>" for line in lines)
            if kind == "liste":
                out.append(f'<ul class="{paragraph_class}">{items}</ul>')
            else:
                start = f' start="{debut}"' if debut != 1 else ""
                out.append(f'<ol class="{paragraph_class}"{start}>{items}</ol>')
        else:
            joined = _inline_to_html(" ".join(lines))
            out.append(f'<p class="{paragraph_class}">{joined}</p>')
    return "".join(out)
