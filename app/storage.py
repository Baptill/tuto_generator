"""Arborescence `vault-articles/` et traçabilité (voir CLAUDE.md §4).

Règle d'or : `content.yaml` + `meta.yaml` suffisent à tout reconstruire.
`output/` est un cache, jamais la source.
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import yaml

from app.schemas import Article, Charte, Meta, Retouches, TemplateConfig

VAULT_ROOT = Path(__file__).resolve().parent.parent / "vault-articles"


def article_dir(article_id: str) -> Path:
    return VAULT_ROOT / "articles" / article_id


def article_output_dir(article_id: str) -> Path:
    return article_dir(article_id) / "output"


def article_assets_dir(article_id: str) -> Path:
    return article_dir(article_id) / "assets"


def content_path(article_id: str) -> Path:
    return article_dir(article_id) / "content.yaml"


def meta_path(article_id: str) -> Path:
    return article_dir(article_id) / "meta.yaml"


def template_dir(template_id: str) -> Path:
    return VAULT_ROOT / "templates" / template_id


def template_file_path(template_id: str, fichier: str = "template.html") -> Path:
    return template_dir(template_id) / fichier


def template_config_path(template_id: str) -> Path:
    return template_dir(template_id) / "config.yaml"


def retouches_path(article_id: str) -> Path:
    return article_dir(article_id) / "retouches.yaml"


def charte_path() -> Path:
    return VAULT_ROOT / "charte" / "charte.yaml"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class _Dumper(yaml.SafeDumper):
    """Dumper YAML du projet : les textes multilignes sortent en bloc (`|`).

    `content.yaml` est relu et édité à la main autant qu'il est écrit par
    l'outil : un paragraphe doit y rester lisible, pas s'aplatir en chaîne
    échappée sur une ligne.
    """


def _representer_str(dumper: yaml.SafeDumper, valeur: str):
    style = "|" if "\n" in valeur.rstrip("\n") else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", valeur, style=style)


_Dumper.add_representer(str, _representer_str)


def _dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=_Dumper, allow_unicode=True, sort_keys=False)


def load_article(article_id: str) -> tuple[Article, bytes]:
    """Charge content.yaml et retourne (Article, contenu_brut) — le contenu
    brut sert au calcul de `hash_contenu`."""
    path = content_path(article_id)
    raw = path.read_bytes()
    data = yaml.safe_load(raw)
    return Article.model_validate(data), raw


def load_template_config(template_id: str) -> TemplateConfig:
    return TemplateConfig.model_validate(_load_yaml(template_config_path(template_id)))


def load_charte() -> Charte:
    return Charte.model_validate(_load_yaml(charte_path()))


def load_meta(article_id: str) -> Meta | None:
    path = meta_path(article_id)
    if not path.is_file():
        return None
    return Meta.model_validate(_load_yaml(path))


def load_retouches(article_id: str) -> Retouches:
    """Calques posés dans l'éditeur navigateur. Absent = aucune retouche."""
    path = retouches_path(article_id)
    if not path.is_file():
        return Retouches()
    return Retouches.model_validate(_load_yaml(path))


def write_retouches(article_id: str, retouches: Retouches) -> Path:
    """Écrit (ou supprime, si plus aucun calque) le fichier de retouches."""
    path = retouches_path(article_id)
    if not retouches.calques:
        path.unlink(missing_ok=True)
        return path
    _dump_yaml(path, retouches.model_dump(mode="json"))
    return path


def compute_hash_contenu(raw_content_yaml: bytes) -> str:
    return hashlib.sha256(raw_content_yaml).hexdigest()


def write_meta(
    article_id: str,
    template_id: str,
    charte_version: int,
    hash_contenu: str,
    statut: str = "brouillon",
    url_publiee: str | None = None,
    template_version: int = 1,
) -> Meta:
    existing = load_meta(article_id)
    cree_le = existing.cree_le if existing else date.today()
    meta = Meta(
        id=article_id,
        template_id=template_id,
        template_version=template_version,
        charte_version=charte_version,
        hash_contenu=hash_contenu,
        statut=statut,
        url_publiee=url_publiee,
        cree_le=cree_le,
        build_le=date.today(),
    )
    write_meta_model(meta)
    return meta


def write_meta_model(meta: Meta) -> Meta:
    """Écrit un `Meta` déjà construit (utilisé pour les mises à jour ciblées,
    ex. le marqueur de retouche HTML posé par le serveur d'édition)."""
    _dump_yaml(meta_path(meta.id), meta.model_dump(mode="json"))
    return meta


def write_article(article: Article) -> Path:
    """Écrit `content.yaml` — seule voie d'écriture de la source de vérité
    (le composeur passe par ici, jamais par l'artefact rendu ; CLAUDE.md §2).

    Les champs optionnels non renseignés des sections et des blocs sont omis
    (`legende: null`, `largeur_mm: null`…) : le fichier reste aussi lisible
    qu'écrit à la main. Les clés de premier niveau, elles, sont conservées même
    vides — `metadonnees_seo` et `liens_internes` sont des emplacements réservés
    aux Étapes 5-6 (CLAUDE.md §4).
    """
    data = article.model_dump(mode="json")
    for section in data.get("sections", []):
        if section.get("titre") is None:
            section.pop("titre", None)
        section["blocs"] = [
            {k: v for k, v in bloc.items() if v is not None} for bloc in section.get("blocs", [])
        ]
    _dump_yaml(content_path(article.id), data)
    return content_path(article.id)


def list_article_ids() -> list[str]:
    base = VAULT_ROOT / "articles"
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if (d / "content.yaml").is_file())
