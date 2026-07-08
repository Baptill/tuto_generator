# CLAUDE.md — Générateur de tutoriels & articles

> Référence unique du projet : direction, principes d'architecture, roadmap. À tenir à jour à chaque étape franchie (voir `Statut` en fin de fichier).

## 1. Vision

Outil interne qui transforme un **contenu structuré** (template + sections + images) en **livrables Word éditables + PDF** conformes à une charte graphique, avec montée en puissance progressive : rédaction assistée par IA → déploiement autonome sur le site → SEO et maillage interne.

**Objectifs :**
- Accélérer la production de tutoriels à chaque release du logiciel client, et d'articles de blog.
- Garantir une cohérence graphique totale, avec mise à jour globale en un clic quand la charte change.
- Réduire le temps de rédaction (IA), de publication (déploiement) et de référencement (SEO).

**Contexte confirmé :** 2 utilisateurs techniques · serveur Linux · dépôt GitHub pour le contenu · site maison pour la publication · volume cible de quelques centaines d'articles · français uniquement · publication toujours en brouillon + édition + validation humaine.

## 2. Principe directeur : le document n'est pas la source, c'est un build

La source de vérité = **contenu structuré** (`content.yaml`) + **template** (`.docx`) + **charte** (`charte.yaml`). Le Word et le PDF sont des **artefacts recompilés à la demande**, jamais édités directement.

Conséquence directe : régénérer 200 tutos après un changement de charte = relancer le build, pas éditer 200 fichiers Word. Ce principe conditionne toute l'architecture — toute nouvelle fonctionnalité **lit ou écrit `content.yaml`**, jamais le `.docx`.

```
content.yaml + template.docx + charte.yaml  →  [Moteur de rendu]  →  article.docx (éditable) + article.pdf
```

## 3. Stack technique

| Besoin | Choix | Raison |
|---|---|---|
| Génération Word depuis template | `docxtpl` (python-docx + Jinja2) | Fidélité de mise en page, template = vrai fichier Word éditable |
| Conversion Word → PDF | LibreOffice headless (`soffice --convert-to pdf`) | Pas d'Office sur serveur Linux |
| Backend / API | FastAPI | — |
| Tâches longues (synchro, IA) | Worker (RQ / Celery / arq) | Ne pas bloquer l'UI sur 200 articles |
| Stockage du contenu | Dépôt Git (GitHub) | Historique, diff, rollback, traçabilité gratuits |
| Index / recherche (Étape 5) | SQLite + embeddings légers (`sqlite-vec`) | Volume = centaines d'articles, pas besoin de plus lourd |

Dimensionnement volontairement léger (2 utilisateurs, quelques centaines d'articles) : pas d'infra distribuée, pas de base vectorielle managée, pas de queue complexe.

### Template Word : styles nommés, jamais de couleur en dur

Le template Word contient des balises Jinja2 (`{{ article.titre }}`, `{% for section in sections %}`) et utilise exclusivement des **styles nommés** (Titre 1, Corps, Légende…) et des **couleurs de thème** — jamais de valeurs codées en dur. La charte est injectée au moment du build en remplaçant le thème/les styles du docx généré. Une seule famille de templates, la charte varie par injection — pas un template par charte.

### Sections modulaires : grille de page en 4 hauteurs

Un template n'est plus un document figé avec des sections prédéfinies à l'avance : c'est une **bibliothèque de blocs de section** que l'utilisateur assemble librement pour construire chaque page. Une page est découpée en **4 unités de hauteur**. Chaque section déclare une hauteur de **1 à 4 unités** — une section de hauteur 4 occupe une page entière ; deux sections de hauteur 2, ou quatre de hauteur 1, se partagent une page ; toute combinaison dont la somme fait 4 est valide.

Le moteur de rendu empile les sections dans l'ordre du `content.yaml` et déclenche un **saut de page** dès que la section suivante ferait dépasser 4 unités sur la page courante. Intérêt : un catalogue de blocs réutilisables (« texte pleine page », « image + légende demi-page », « deux encadrés côte à côte »…) plutôt qu'un template monolithique par type d'article — la mise en page devient une composition pilotée par le contenu, pas un gabarit figé par le template.

- Chaque bloc de section du catalogue est conçu pour une ou plusieurs hauteurs compatibles (ex. un bloc « image + légende » pensé pour 1 ou 2 unités, pas pour 4).
- Contrainte à valider au rendu : la somme des hauteurs des sections d'une même page ne doit pas dépasser 4 (le moteur gère lui-même le passage à la page suivante, l'utilisateur n'a pas à la calculer).

## 4. Modèle de données (colonne vertébrale)

Tout le monde (utilisateur, moteur de rendu, IA, publication) parle le même schéma. À figer avant de coder quoi que ce soit.

- **`content.yaml`** (par article) — source de vérité : métadonnées + `sections[]`, chaque section déclarant une **`hauteur`** (1 à 4 unités, voir [Sections modulaires](#sections-modulaires--grille-de-page-en-4-hauteurs)) et une **liste ordonnée de `blocs`** (`paragraphe`, `encadre` (astuce/attention/info), `image`) plutôt qu'un simple titre+texte. Contient aussi `metadonnees_seo` et `liens_internes`, vides tant que les étapes 5-6 ne sont pas actives (évite une migration de schéma plus tard).
- **`config.yaml`** (par template) — ce que le template attend : catalogue des blocs de section disponibles et leurs hauteurs compatibles (1-4), sections min/max, contraintes de longueur, formats d'image acceptés.
- **`charte.yaml`** — couleurs, polices, logo, espacements. Versionné (`version`, archives dans `charte/versions/`).
- **`meta.yaml`** (par article) — `template_id`/version, `charte_version` (clé de la synchro), `hash_contenu`, `statut` (brouillon/validé/publié), `url_publiee`, dates.

### Arborescence `vault-articles/` (dépôt Git dédié)

```
vault-articles/
├── templates/<template_id>/{template.docx, config.yaml}
├── charte/{charte.yaml, logo.png, theme.xml, versions/}
├── articles/<id>/{content.yaml, assets/, output/{article.docx, article.pdf}, meta.yaml}
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
Template + sections saisies manuellement → docx + pdf conformes à la charte, rangés et tracés. Zéro IA, 100% déterministe.
- Figer le schéma `content.yaml`, dont le champ `hauteur` par section (bloquant pour tout le reste).
- Créer les catalogues de blocs de section pilotes `tuto-release` et `blog-standard` (styles nommés, balises Jinja, un bloc par hauteur/usage compatible).
- Moteur de rendu `docxtpl` : boucle sections → blocs, gestion Markdown léger → runs Word (gras/listes), images (`InlineImage`), encadrés (styles nommés), **logique de pagination sur la grille 4 hauteurs** (saut de page dès que la somme dépasse 4 sur la page courante).
- Conversion PDF via LibreOffice headless, vérifier fidélité (polices installées, sauts de page).
- Rangement + `meta.yaml` + `hash_contenu`.
- UI MVP : saisie, upload images, bouton Générer.
- **DoD** : tuto 5 sections + 3 images → docx éditable propre + PDF fidèle ; template créé par un non-développeur fonctionne ; des sections de hauteurs variées (ex. 1+1+2, ou 4 seule) se composent correctement sur la page sans intervention manuelle.

### Étape 2 — Synchronisation charte
Bouton « Synchroniser la charte » qui recompile tous les articles obsolètes après un changement de charte — pas de ré-édition manuelle.
- Écran d'édition de charte → incrémente `charte.version`, archive l'ancienne.
- Job de re-build asynchrone (worker), sélectif (`charte_version < version actuelle`), avec rapport (succès/échecs/ignorés).
- Portée : tous les articles, sans filtre (simplicité, 2 utilisateurs).
- Un article déjà publié dont le rendu est régénéré n'est **jamais republié automatiquement** — statut « rendu mis à jour, publication en attente ».
- Risque connu : retouches manuelles du `.docx` écrasées à la synchro → politique « on édite dans l'outil » + détection de modif.

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

- **Fidélité PDF** : polices manquantes ou moteur différent → installer les polices de la charte sur la machine de génération, tester tôt, moteur figé (LibreOffice headless).
- **Licences de polices et d'images** : usage serveur automatisé ≠ usage bureautique classique — à vérifier explicitement.
- **Retouches manuelles écrasées** par une re-synchro — politique claire + détection de modification.
- **Exactitude des tutos générés par IA** — relecture par un référent produit obligatoire avant publication.
- **Adaptateur site maison** = zéro réutilisation externe, dépendance de planning avec l'équipe web — ne bloque pas les Étapes 1-2, indépendantes.
- **Coûts API** (IA, images, SEO) — cache et quotas dès le départ.
- **Secrets** (clés CMS/IA/SEO) — jamais en clair dans le dépôt.

## 7. Points ouverts non bloquants

- Liste exacte des types d'encadrés (astuce, attention…) et leur charte visuelle précise.
- Catalogue exact des blocs de section par hauteur (1/2/3/4 unités) et comportement si une section ne correspond à aucune hauteur compatible dans le template.
- Spécification de l'API du site maison (endpoints, format, auth) — à caler avec l'équipe web.
- Fournisseur de génération d'images IA et licences associées.
- Ahrefs seul vs Ahrefs + SEMrush.
- Workflow Git à 2 utilisateurs (branches vs commits séquentiels) — probablement non critique vu le volume.

---
**Statut** : cadrage validé (2026-07-01). Prochaine étape : figer le schéma `content.yaml` et démarrer l'Étape 1.
