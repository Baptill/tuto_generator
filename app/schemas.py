"""Schéma de données — colonne vertébrale du projet (voir CLAUDE.md §4).

Ces modèles sont la source de vérité du format `content.yaml` / `config.yaml` /
`charte.yaml` / `meta.yaml`. Toute évolution du schéma doit être répercutée ici
en premier.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

HauteurSection = Literal[1, 2, 3, 4]
LayoutSection = Literal["texte-seul", "image-dessus-texte", "image-gauche-texte", "texte-image-droite"]
StyleEncadre = Literal["astuce", "attention", "info"]
StatutArticle = Literal["brouillon", "valide", "publie"]


class BlocParagraphe(BaseModel):
    type: Literal["paragraphe"] = "paragraphe"
    texte: str


class BlocEncadre(BaseModel):
    type: Literal["encadre"] = "encadre"
    style: StyleEncadre
    texte: str


class BlocImage(BaseModel):
    type: Literal["image"] = "image"
    fichier: str
    legende: str | None = None
    largeur_mm: int | None = None


Bloc = Annotated[Union[BlocParagraphe, BlocEncadre, BlocImage], Field(discriminator="type")]


class Section(BaseModel):
    id: str
    titre: str
    hauteur: HauteurSection = Field(
        description="Unités de hauteur occupées sur une page divisée en 4 (voir CLAUDE.md §3)."
    )
    layout: LayoutSection = "texte-seul"
    blocs: list[Bloc]


class MetadonneesSeo(BaseModel):
    slug: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    mots_cles: list[str] = Field(default_factory=list)


class Article(BaseModel):
    """content.yaml"""

    id: str
    type: Literal["tutoriel", "blog"]
    template_id: str
    langue: Literal["fr"] = "fr"
    titre: str
    resume: str | None = None
    auteur: str
    sections: list[Section]
    prerequis: list[str] = Field(default_factory=list)
    metadonnees_seo: MetadonneesSeo = Field(default_factory=MetadonneesSeo)
    liens_internes: list[str] = Field(default_factory=list)


class SectionsAttendues(BaseModel):
    min: int = 1
    max: int = 50


class ContraintesTitre(BaseModel):
    max_caracteres: int = 90


class ContrainteSectionTexte(BaseModel):
    max_caracteres: int = 4000


class Contraintes(BaseModel):
    titre: ContraintesTitre = Field(default_factory=ContraintesTitre)
    section_texte: ContrainteSectionTexte = Field(default_factory=ContrainteSectionTexte)


class ImageConfig(BaseModel):
    formats_acceptes: list[str] = Field(default_factory=lambda: ["png", "jpg", "jpeg", "webp"])
    largeur_mm_defaut: int = 150


class BlocSectionCatalogue(BaseModel):
    """Un bloc de section du catalogue et les hauteurs pour lesquelles il est prévu."""

    nom: str
    description: str = ""
    hauteurs_compatibles: list[HauteurSection]


class TemplateConfig(BaseModel):
    """config.yaml d'un template."""

    template_id: str
    libelle: str
    fichier: str = "template.docx"
    type: Literal["tutoriel", "blog"]
    sections_attendues: SectionsAttendues = Field(default_factory=SectionsAttendues)
    contraintes: Contraintes = Field(default_factory=Contraintes)
    image: ImageConfig = Field(default_factory=ImageConfig)
    catalogue_blocs: list[BlocSectionCatalogue] = Field(default_factory=list)


class Couleurs(BaseModel):
    primaire: str
    secondaire: str
    texte: str
    fond: str


class StyleTypo(BaseModel):
    """Propriétés typographiques d'un style nommé Word.

    `gras`, `italique` et `souligne` sont cumulables : les trois à true
    donnent du texte gras + italique + souligné.
    `couleur` est un code hex optionnel ; si absent, la couleur sémantique
    de la charte s'applique (primaire pour les titres, texte pour le corps).
    """
    famille: str
    taille_pt: float
    gras: bool = False
    italique: bool = False
    souligne: bool = False
    couleur: str | None = None
    text_alignement: Literal["left", "center", "right", "justify"] = "left"


class Polices(BaseModel):
    titre_1: StyleTypo
    titre_2: StyleTypo
    corps: StyleTypo
    legende: StyleTypo
    prerequis_label: StyleTypo
    prerequis_item: StyleTypo


class Espacements(BaseModel):
    interligne: float = 1.15
    marge_mm: int = 20


class Charte(BaseModel):
    """charte.yaml"""

    version: int
    nom: str
    couleurs: Couleurs
    polices: Polices
    logo: str | None = None
    espacements: Espacements = Field(default_factory=Espacements)


class Meta(BaseModel):
    """meta.yaml (par article)"""

    id: str
    template_id: str
    template_version: int = 1
    charte_version: int
    hash_contenu: str
    statut: StatutArticle = "brouillon"
    url_publiee: str | None = None
    cree_le: date
    build_le: date
