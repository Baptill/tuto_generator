# CLAUDE.md — Générateur de tutoriels & articles

> Référence unique du projet : direction, principes d'architecture, roadmap. À tenir à jour à chaque étape franchie (voir `Statut` en fin de fichier).

## 1. Vision

Outil interne qui transforme un **contenu structuré** (template + sections + images) en **livrables HTML éditables (dans le navigateur) + PDF** conformes à une charte graphique, avec montée en puissance progressive : rédaction assistée par IA → déploiement autonome sur le site → SEO et maillage interne.

**Objectifs :**
- Accélérer la production de tutoriels à chaque release du logiciel client, et d'articles de blog.
- Garantir une cohérence graphique totale, avec mise à jour globale en un clic quand la charte change.
- Réduire le temps de rédaction (IA), de publication (déploiement) et de référencement (SEO).

**Contexte confirmé :** 2 utilisateurs techniques · serveur Linux · dépôt GitHub pour le contenu · site maison pour la publication · volume cible de quelques centaines d'articles · français uniquement · publication toujours en brouillon + édition + validation humaine.

## 2. Principe directeur : le document n'est pas la source, c'est un build

La source de vérité = **contenu structuré** (`content.yaml`) + **template** (`.html`) + **charte** (`charte.yaml`). Le HTML et le PDF sont des **artefacts recompilés à la demande**. Le HTML rendu peut recevoir des **retouches finales dans le navigateur** avant mise en production (voir §3, « Surface d'édition »), mais ces retouches sont une touche de finition à sens unique : la source de vérité reste `content.yaml`.

Conséquence directe : régénérer 200 tutos après un changement de charte = relancer le build, pas éditer 200 fichiers. Ce principe conditionne toute l'architecture — toute nouvelle fonctionnalité **lit ou écrit `content.yaml`**, jamais l'artefact HTML rendu.

```
content.yaml + template.html + charte.yaml  →  [Moteur de rendu HTML/CSS]  →  article.html (éditable navigateur) + article.pdf
```

## 3. Stack technique

| Besoin | Choix | Raison |
|---|---|---|
| Moteur de rendu | HTML + CSS via **Jinja2** | Liberté visuelle totale (séparateurs, liserés, labels, grille) impossible à obtenir en pilotant Word par API |
| Conversion HTML → PDF | **WeasyPrint** (pur Python, CSS paged-media) | Pas de navigateur ni de LibreOffice à installer ; tourne tel quel sur serveur Linux ; polices via `@font-face` |
| Surface d'édition | HTML `contenteditable` dans le navigateur | Retouche libre (texte **et** ajout d'éléments) sans régénérer ; remplace l'édition Word |
| Backend / API | FastAPI | — |
| Tâches longues (synchro, IA) | Worker (RQ / Celery / arq) | Ne pas bloquer l'UI sur 200 articles |
| Stockage du contenu | Dépôt Git (GitHub) | Historique, diff, rollback, traçabilité gratuits |
| Index / recherche (Étape 5) | SQLite + embeddings légers (`sqlite-vec`) | Volume = centaines d'articles, pas besoin de plus lourd |

Dimensionnement volontairement léger (2 utilisateurs, quelques centaines d'articles) : pas d'infra distribuée, pas de base vectorielle managée, pas de queue complexe.

> **Pourquoi pas Word (`docxtpl`) ?** Piloter Word/`.docx` par API plafonne la mise en page : ajouter un séparateur, un liseré arrondi, un label ou centrer verticalement du contenu est très laborieux voire impossible. HTML/CSS lève ce plafond, et `contenteditable` offre en prime une retouche libre dans le navigateur. Word est abandonné comme livrable ; si un `.docx` devenait un jour exigé, il ne serait qu'un export secondaire dégradé (Pandoc), jamais la surface d'édition.

### Template HTML : design-system CSS + variables de charte, jamais de couleur en dur

Le template est un fichier `template.html` (Jinja2 : `{{ article.titre }}`, `{% for … %}`) qui porte le **design-system** (layout des blocs de section) en CSS. Il utilise exclusivement des **classes de style nommées** (`titre-1`, `corps`, `legende`…) et des **variables CSS** (`var(--couleur-primaire)`, `var(--couleur-lisere)`…) — jamais de valeur codée en dur. Au build, la charte est injectée sous forme d'un bloc `:root { --couleur-… }` + `@font-face` + règles typographiques des styles nommés. Une seule famille de templates, la charte varie par injection — pas un template par charte. Les couleurs **sémantiques** des encadrés (astuce/attention/info) restent fixes dans le template : elles portent un sens indépendant de la marque.

### Surface d'édition : retouches finales dans le navigateur

Le HTML rendu est éditable via `designMode`. L'utilisateur peut **modifier** le texte **et ajouter** du contenu depuis une palette (`app/editeur.py`, injectée dans les templates via `{{ editeur_html }}` — source unique pour toutes les chartes et tous les templates). Modèle retenu : **retouche finale à sens unique** (générer → retoucher → produire le PDF pour la prod), les retouches ne remontant pas dans `content.yaml` — cohérent avec le principe « le document est un build ». Point ouvert : proposer aussi un mode « ajout remonté dans `content.yaml` » qui survivrait aux régénérations de charte (voir §7).

Trois règles gouvernent cette surface :

1. **La hauteur du document est verrouillée.** Chaque `.page` a une hauteur fixe (4 unités de la grille) et `overflow:hidden` : aucune retouche ne peut décaler la pagination, ce qui dépasse est rogné et non repoussé.
2. **Tout ajout est un calque hors flux** — paragraphe, titre, liste, encadré, image, colonnes, séparateur, et annotations (flèche, cadre, pastille, étiquette). Position et taille en **% de la page**, donc fidèles au PDF quelle que soit l'échelle de rendu ; déplaçables et redimensionnables à la souris, posables n'importe où (aucun ancrage obligatoire à une image).
3. **Toute action est annulable** (historique de snapshots couvrant calques et frappe, Ctrl+Z).

« Enregistrer HTML » n'est pas un « enregistrer sous » : il **écrase `output/article.html`** et **régénère le PDF**, via le service local `app/serveur.py` (`python -m app.cli serve`). Le fichier écrit conserve la barre d'édition (masquée à l'impression, ignorée par WeasyPrint) et reste donc ré-éditable.

Depuis l'aperçu du composeur, l'enregistrement bascule en mode **`regenerer`** : le document affiché y est un rendu de travail (URL `http://`, texte piloté par le formulaire) qu'il ne faut pas figer dans `output/`. Seuls les calques sont alors persistés, et l'artefact est **reconstruit depuis `content.yaml` + `retouches.yaml`** — chemins locaux, PDF correct, annotations conservées.

Le chrome de l'éditeur (barre, palette, poignées) reprend les jetons visuels du composeur — gris, accent, rayons, ombres — portés par les éléments de chrome et non par `:root`, pour ne pas se mêler aux variables `--couleur-*` de la charte, qui habillent le document. Dans l'aperçu du composeur, la barre se réduit à « Mode édition » et « Annuler » : c'est « Enregistrer & générer » qui écrit la source *et* les calques. Le HTML autonome conserve son bouton « Enregistrer HTML » — c'est sa seule voie de persistance.

**Les calques survivent aux régénérations.** L'enregistrement les persiste dans `retouches.yaml` (une **source**, versionnée dans Git au même titre que `content.yaml` — pas un artefact), et le moteur de rendu les réinjecte à chaque build. Un calque est ancré à sa **section** (`ancre_section`, l'`id` du `content.yaml`) plutôt qu'à une page : si un changement de charte déplace la section sur une autre feuille, le calque la suit. Les calques posés hors section (en-tête, marge) sont ancrés à l'index de page ; ceux dont l'ancre a disparu sont reversés sur la dernière page plutôt que perdus. Cela tranche partiellement le point ouvert §7 : les **ajouts** remontent bien dans une source durable, mais les **modifications de texte dans le flux** ne sont toujours pas reprises (elles appartiennent à `content.yaml`) — d'où le marqueur `meta.retouche_html_le`, effacé à la génération suivante, qui alimentera l'avertissement de re-synchro de l'Étape 2.

### Composeur : la saisie d'un `content.yaml` à la souris

L'UI de saisie (`app/composer.py` + `app/ui/`, servie sur `/` par
`python -m app.cli serve`) est la façon normale de produire un `content.yaml` :
en-tête du document (titre, sous-titre, prérequis), puis empilement de sections
choisies dans un **panneau de wireframes**. Chaque modèle y est montré en gris
(l'architecture du bloc, pas son contenu) avec son **poids explicite** (1/4 à
4/4 de page) et les champs qu'il réclame ; le choix d'un modèle génère
exactement le formulaire correspondant — trois images légendées pour
`triple-image`, une image + un texte pour `etape-compacte`, etc.

Ce que le formulaire doit demander pour chaque layout est décrit dans
`app/catalogue.py` (wireframe SVG, poids, champs `mini`/`maxi`). C'est le
pendant *saisie* de `app/layouts.py` (le *rendu*) : les deux modules déclarent
les mêmes layouts, un test vérifie qu'ils ne divergent pas.

Trois garde-fous d'architecture :

1. **L'aperçu est le vrai rendu.** À chaque frappe, le front POSTe l'article
   complet et le serveur le rend avec `app/renderer.py` : aucune maquette
   approximative réimplémentée en JS. Il est simplement rendu sans barre
   d'édition et avec des URL http:// (assets, polices, logo servis sous
   `/vault`), le build de production gardant ses chemins `file://`.
2. **L'aperçu n'écrit rien.** Seuls le téléversement d'une image (rangée dans
   `assets/`) et le bouton « Enregistrer & générer » touchent le disque.
3. **Le composeur écrit `content.yaml`, jamais le HTML rendu** (§2), puis
   appelle le même `generate_article` que la CLI — pas de second pipeline.
   Rouvrir un tutoriel recharge le formulaire depuis `content.yaml` : l'aller-
   retour est sans perte.

**Enregistrement automatique.** Quitter le champ titre crée le tutoriel sur
disque ; ensuite, toute modification est écrite dans les 30 secondes. Cet
enregistrement de fond n'exige pas un tutoriel complet (un brouillon reste
écrit, les contraintes du template sont renvoyées en avertissements) et ne
produit pas de PDF — WeasyPrint coûte quelques secondes, il est réservé au
bouton « Enregistrer & générer ». Ouvrir un tutoriel ne le modifie pas : rien
n'est réécrit tant que l'utilisateur n'a rien changé.

**Annotations dans l'aperçu.** L'aperçu embarque la surface d'édition (§
« Surface d'édition ») : barre et palette à droite du volet, calques déjà posés
réaffichés depuis `retouches.yaml`. « Enregistrer & générer » relève les calques
de l'aperçu et les écrit dans `retouches.yaml` en même temps que `content.yaml`
— un seul bouton pour le contenu et les annotations. Entre deux
enregistrements, les calques posés voyagent avec chaque requête d'aperçu : une
annotation non enregistrée survit donc au rafraîchissement que déclenche la
frappe suivante. Ces calques sont ceux du tutoriel *affiché* : tant que le
nouveau document n'est pas chargé, l'aperçu montre encore le précédent, et le
composeur s'interdit d'attribuer ses calques au suivant. Changer de tutoriel
enregistre au passage les annotations en attente. Le zoom s'applique aux pages *dans* le
document (variable CSS `--apercu-zoom`) et non à l'`<iframe>`, pour que la
palette garde sa taille native. L'aperçu se fige tant que le mode édition est
actif : une frappe dans le formulaire ne peut donc pas effacer des calques non
enregistrés.

### Sections modulaires : grille de page en 4 hauteurs

Un template n'est plus un document figé avec des sections prédéfinies à l'avance : c'est une **bibliothèque de blocs de section** que l'utilisateur assemble librement pour construire chaque page. Une page est découpée en **4 unités de hauteur**. Chaque section déclare une hauteur de **1 à 4 unités** — une section de hauteur 4 occupe une page entière ; deux sections de hauteur 2, ou quatre de hauteur 1, se partagent une page ; toute combinaison dont la somme fait 4 est valide.

Le moteur de rendu empile les sections dans l'ordre du `content.yaml` et déclenche un **saut de page** dès que la section suivante ferait dépasser 4 unités sur la page courante. Intérêt : un catalogue de blocs réutilisables (« texte pleine page », « image + légende demi-page », « deux encadrés côte à côte »…) plutôt qu'un template monolithique par type d'article — la mise en page devient une composition pilotée par le contenu, pas un gabarit figé par le template.

- **Une section occupe exactement son quota** : hauteur fixe (`height`, pas `min-height`) et débordement rogné. Elle ne s'étire donc jamais pour remplir la place restante d'une page, et ne mord jamais sur le quota de la suivante — les sections se posent bout à bout depuis le haut de la page. Même règle pour l'en-tête du document, qui vaut exactement 1 unité (celle que la pagination lui réserve), son contenu réparti en `space-evenly`.
- Chaque bloc de section du catalogue est conçu pour une ou plusieurs hauteurs compatibles (ex. un bloc « image + légende » pensé pour 1 ou 2 unités, pas pour 4).
- Contrainte à valider au rendu : la somme des hauteurs des sections d'une même page ne doit pas dépasser 4 (le moteur gère lui-même le passage à la page suivante, l'utilisateur n'a pas à la calculer).

## 4. Modèle de données (colonne vertébrale)

Tout le monde (utilisateur, moteur de rendu, IA, publication) parle le même schéma. À figer avant de coder quoi que ce soit.

- **`content.yaml`** (par article) — source de vérité : métadonnées + `sections[]`, chaque section déclarant une **`hauteur`** (1 à 4 unités, voir [Sections modulaires](#sections-modulaires--grille-de-page-en-4-hauteurs)) et une **liste ordonnée de `blocs`** (`paragraphe`, `encadre` (astuce/attention/info), `image`) plutôt qu'un simple titre+texte. Contient aussi `metadonnees_seo` et `liens_internes`, vides tant que les étapes 5-6 ne sont pas actives (évite une migration de schéma plus tard).
- **`config.yaml`** (par template) — ce que le template attend : catalogue des blocs de section disponibles et leurs hauteurs compatibles (1-4), sections min/max, contraintes de longueur, formats d'image acceptés.
- **`charte.yaml`** — couleurs (dont `lisere`), polices, logo, espacements. Injectée en variables CSS au build. Versionné (`version`, archives dans `charte/versions/`).
- **`meta.yaml`** (par article) — `template_id`/version, `charte_version` (clé de la synchro), `hash_contenu`, `statut` (brouillon/validé/publié), `url_publiee`, dates.

### Arborescence `vault-articles/` (dépôt Git dédié)

```
vault-articles/
├── templates/<template_id>/{template.html, config.yaml}
├── charte/{charte.yaml, logo.png, fonts/, versions/}
├── articles/<id>/{content.yaml, assets/, output/{article.html, article.pdf}, meta.yaml}
└── _index/registry.sqlite
```

`content.yaml` + `meta.yaml` suffisent à tout reconstruire : `output/` est un cache, jamais versionné (`.gitignore`). Chaque génération/modification = un commit.

## 5. Roadmap — 6 étapes

Construction de gauche à droite : chaque brique s'appuie sur la précédente sans la casser.

```
Étape 1 (Génération) ─┬─→ Étape 2 (Synchro charte)
                       ├─→ Étape 3 (Rédaction IA) ─┐
                       └─→ Étape 4 (Déploiement) ──┴─→ Étape 5 (Base & doublons) ─→ Étape 6 (SEO)
```

### Étape 1 — Génération sans IA (fondation, priorité haute)
Template + sections saisies manuellement → HTML + PDF conformes à la charte, rangés et tracés. Zéro IA, 100% déterministe.
- Figer le schéma `content.yaml`, dont le champ `hauteur` par section (bloquant pour tout le reste).
- Créer les catalogues de blocs de section pilotes `tuto-release` et `blog-standard` (classes CSS nommées, balises Jinja, un bloc par hauteur/usage compatible).
- Moteur de rendu HTML/CSS : boucle sections → blocs, gestion Markdown léger → HTML (gras/listes), images (`<figure>`/`<img>`), encadrés (classes sémantiques), **logique de pagination sur la grille 4 hauteurs** (`break-before: page` dès que la somme dépasse 4 sur la page courante). Layouts multi-colonnes en `display:table` (support print robuste dans WeasyPrint, contrairement à flexbox).
- Conversion PDF via WeasyPrint, vérifier fidélité (polices `@font-face` de `charte/fonts/`, sauts de page).
- Rangement + `meta.yaml` + `hash_contenu`.
- UI MVP (**fait**) : composeur web — en-tête, panneau de wireframes avec poids,
  formulaire dérivé du layout choisi, upload d'images, aperçu live, bouton
  « Enregistrer & générer » (voir « Composeur » ci-dessus).
- **DoD** : tuto 5 sections + 3 images → HTML éditable propre + PDF fidèle ; template créé par un non-développeur fonctionne ; des sections de hauteurs variées (ex. 1+1+2, ou 4 seule) se composent correctement sur la page sans intervention manuelle.

### Étape 2 — Synchronisation charte
Bouton « Synchroniser la charte » qui recompile tous les articles obsolètes après un changement de charte — pas de ré-édition manuelle.
- Écran d'édition de charte → incrémente `charte.version`, archive l'ancienne.
- Job de re-build asynchrone (worker), sélectif (`charte_version < version actuelle`), avec rapport (succès/échecs/ignorés).
- Portée : tous les articles, sans filtre (simplicité, 2 utilisateurs).
- Un article déjà publié dont le rendu est régénéré n'est **jamais republié automatiquement** — statut « rendu mis à jour, publication en attente ».
- Risque connu : retouches finales du HTML dans le navigateur écrasées à la synchro (elles ne remontent pas dans `content.yaml`) → politique « on édite le contenu dans l'outil » + détection de modif.

### Étape 3 — Rédaction assistée par IA
Module en amont : brief textuel → LLM génère le contenu de chaque section, au format `content.yaml` exact (l'IA est une source de contenu de plus, pas un pipeline parallèle).
- Sortie structurée contrainte au schéma `content.yaml`. Flux en 2 temps : plan de sections (validé humain) → rédaction.
- Images : phase manuelle (upload, actuelle) vs phase automatisée (génération IA, fournisseur externe à choisir — Anthropic ne génère pas d'images). Point de vigilance non tranché : une image générée ne peut pas représenter fidèlement une vraie capture d'écran logicielle — prévoir un point de contrôle humain ou réserver la génération au blog.
- Relecture humaine obligatoire avant rendu ; journalisation brief + modèle + sortie.
- **DoD** : un brief produit un `content.yaml` valide qui passe sans modification dans le pipeline Étape 1.

### Étape 4 — Déploiement sur le site
Connexion au site maison (pas de CMS du marché → adaptateur et API à spécifier avec l'équipe web). Flux : brouillon → édition dans l'outil → bouton Publier.
- Atelier avec l'équipe web : endpoints (`POST /articles`, `PATCH`, `POST /publish`), format d'échange, authentification, notion brouillon/publié.
- Adaptateur `content.yaml` → format CMS, y compris rendu des blocs `encadre`. Upload images vers médiathèque du site.
- Toute édition d'un brouillon passe par l'outil, jamais directement sur le site.
- Synchro charte sur un article publié → ne republie jamais automatiquement (lien Étape 2).
- Secrets en coffre/variables d'environnement, jamais en clair dans le dépôt ; compte de publication à permissions minimales.
- **DoD** : article validé poussé en brouillon avec images/métadonnées correctes ; mises à jour sans doublon.

### Étape 5 — Base d'articles : anti-doublons & maillage
Index vectoriel (SQLite + `sqlite-vec`) des articles existants (site + vault) pour détecter les doublons et suggérer des liens internes.
- Ingestion + embeddings, mis à jour à chaque publication.
- Détection de similarité avant rédaction : seuils « doublon » vs « thème connexe », décision toujours humaine.
- Suggestions de liens internes écrites dans `content.yaml.liens_internes`.
- **DoD** : sujet déjà traité déclenche une alerte avant rédaction ; suggestions de liens pertinentes et éditables.

### Étape 6 — SEO & maillage avancé
Étude SEO en amont de la rédaction (remplit `metadonnees_seo`, guide le brief de l'Étape 3) + structuration en silos pilier/satellites.
- Mots-clés, intention, analyse SERP via **Ahrefs** (déjà connecté) ; SEMrush en complément si besoin non couvert.
- Pages piliers ↔ articles satellites, ancres variées, détection d'orphelins et de liens cassés.
- Cache des requêtes API pour maîtriser les coûts/quotas.
- **DoD** : brief SEO exploitable par l'Étape 3 ; chaque article publié a slug + meta + mots-clés cohérents ; maillage sans orphelins.

## 6. Risques principaux (voir aussi journal des décisions)

- **Fidélité PDF** : polices manquantes ou support CSS partiel → polices de la charte embarquées en `@font-face` (dossier `charte/fonts/`), moteur figé (WeasyPrint). Attention : WeasyPrint a un support **flexbox/grid partiel** → privilégier `display:table`/`table-cell` pour les mises en page multi-colonnes et le centrage vertical. Si un cas CSS moderne bloque, échappatoire = Chrome headless (Playwright).
- **Licences de polices et d'images** : usage serveur automatisé ≠ usage bureautique classique — à vérifier explicitement.
- **Retouches manuelles écrasées** par une re-synchro — politique claire + détection de modification.
- **Exactitude des tutos générés par IA** — relecture par un référent produit obligatoire avant publication.
- **Adaptateur site maison** = zéro réutilisation externe, dépendance de planning avec l'équipe web — ne bloque pas les Étapes 1-2, indépendantes.
- **Coûts API** (IA, images, SEO) — cache et quotas dès le départ.
- **Secrets** (clés CMS/IA/SEO) — jamais en clair dans le dépôt.

## 7. Points ouverts non bloquants

- Liste exacte des types d'encadrés (astuce, attention…) et leur charte visuelle précise.
- Modèle d'édition navigateur : retouches finales **jetables** (retenu) vs option d'**ajout remonté dans `content.yaml`** (survit aux régénérations) ; catalogue exact des éléments insérables dans l'éditeur `contenteditable`.
- Composeur : réordonnancement des sections par glisser-déposer (aujourd'hui ↑/↓), et choix du template à la création (aujourd'hui `tuto-release` par défaut).
- Catalogue exact des blocs de section par hauteur (1/2/3/4 unités) et comportement si une section ne correspond à aucune hauteur compatible dans le template.
- Spécification de l'API du site maison (endpoints, format, auth) — à caler avec l'équipe web.
- Fournisseur de génération d'images IA et licences associées.
- Ahrefs seul vs Ahrefs + SEMrush.
- Workflow Git à 2 utilisateurs (branches vs commits séquentiels) — probablement non critique vu le volume.

---
**Statut** : cadrage validé (2026-07-01). Étape 1 en cours — **composeur livré (2026-08-19)** :
saisie assistée du `content.yaml` (wireframes + poids + aperçu live annotable, enregistrement
automatique), servie par le même `python -m app.cli serve` que l'enregistrement des retouches. **Pivot moteur (2026-07-08)** : abandon de `docxtpl`/Word au profit d'un moteur **HTML/CSS + WeasyPrint**, motivé par le plafond de mise en page de Word (séparateurs, liserés, labels, centrage). Le principe « le document est un build » est conservé ; le HTML devient l'artefact éditable (navigateur, `contenteditable`) en plus du PDF.
