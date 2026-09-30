"""Schéma de données — colonne vertébrale du projet (voir CLAUDE.md §4).

Ces modèles sont la source de vérité du format `content.yaml` / `config.yaml` /
`charte.yaml` / `meta.yaml`. Toute évolution du schéma doit être répercutée ici
en premier.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modeles import MODELES_PAR_ID, modele

HauteurSection = Literal[1, 2, 3, 4]

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
    """Une image. Elle remplit sa boîte sans être déformée (`object-fit:
    contain`) ; `padding_mm` ajoute une marge intérieure à la boîte, ce qui
    réduit l'image d'autant sans toucher à la mise en page."""

    type: Literal["image"] = "image"
    fichier: str
    legende: str | None = None
    largeur_mm: int | None = None
    padding_mm: float | None = Field(default=None, ge=0, le=40)


class BlocItem(BaseModel):
    """Élément d'une liste légendée : une petite icône optionnelle + un texte
    (ex. « Dictée vocale » avec l'icône du micro)."""

    type: Literal["item"] = "item"
    texte: str
    icone: str | None = None


Bloc = Annotated[
    Union[BlocParagraphe, BlocEncadre, BlocImage, BlocItem], Field(discriminator="type")
]


class Section(BaseModel):
    """Une section = un modèle (`layout`, voir app/modeles.py) + un poids.

    `hauteur` (1 à 4 unités de page) est facultative dans content.yaml : elle
    prend alors le poids par défaut du modèle. Elle doit figurer parmi les poids
    compatibles du modèle.
    """

    id: str
    titre: str | None = None
    layout: str = "texte-seul"
    hauteur: int | None = None
    blocs: list[Bloc]

    @field_validator("layout")
    @classmethod
    def _layout_connu(cls, v: str) -> str:
        if v not in MODELES_PAR_ID:
            raise ValueError(f"modèle de section inconnu : '{v}'")
        return v

    @model_validator(mode="after")
    def _hauteur_compatible(self) -> "Section":
        m = modele(self.layout)
        if self.hauteur is None:
            self.hauteur = m.defaut
        elif self.hauteur not in m.hauteurs:
            raise ValueError(
                f"section '{self.id}' : le modèle '{self.layout}' n'existe pas en poids "
                f"{self.hauteur} (poids possibles : {list(m.hauteurs)})"
            )
        return self


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
    fichier: str = "template.html"
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
    lisere: str


class StyleTypo(BaseModel):
    """Propriétés typographiques d'un style nommé (classe CSS).

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


class Calque(BaseModel):
    """Un ajout hors flux posé dans l'éditeur navigateur (voir CLAUDE.md §3).

    Ancré à une **section** (`ancre_section`) dès que le point de pose tombe
    dans une section : le calque suit alors sa section même si un changement
    de charte la déplace sur une autre page. À défaut (en-tête, marge), il est
    ancré à la page par son index.
    """

    ancre_section: str | None = None
    page: int = 0
    classes: str = "calque"
    style: str = ""
    texte: bool = False
    redim: Literal["boite", "largeur", "fleche", "non"] = "boite"
    html: str = ""


class Retouches(BaseModel):
    """retouches.yaml (par article) — calques survivant aux régénérations.

    Source de vérité des retouches, au même titre que `content.yaml` l'est du
    contenu : `output/` reste un cache reconstructible.
    """

    version: int = 1
    calques: list[Calque] = Field(default_factory=list)


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
    # Retouche du HTML rendu depuis l'éditeur navigateur (§3). Effacé à chaque
    # génération : signale donc un output/ plus récent que son content.yaml.
    retouche_html_le: date | None = None
