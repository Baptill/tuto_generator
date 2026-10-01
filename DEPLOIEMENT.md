# Déploiement sur le VPS

Mise en ligne du composeur pour l'équipe : un conteneur Docker, derrière
Envoy (HTTPS), sur un sous-domaine. Dimensionné pour un usage interne
(quelques utilisateurs), pas pour de la montée en charge.

```
navigateur ──HTTPS──▶ Envoy (TLS, sous-domaine) ──HTTP──▶ conteneur :8000 ──▶ ./data (volume)
```

## Ce qui tourne

| Élément | Où | Rôle |
|---|---|---|
| `Dockerfile` | image `tuto-generator` | Python 3.13 + WeasyPrint (Pango/HarfBuzz), serveur non-root |
| `docker-compose.yml` | le service `app` | port `127.0.0.1:8000`, volume `./data`, rotation des logs |
| `./data/vault/` | volume | les tutoriels (`articles/`), plus `templates/` et `charte/` recopiés depuis l'image à chaque démarrage |
| `./data/comptes.yaml` | volume | les comptes (mots de passe hachés, jamais en clair) |
| `.env` | serveur uniquement | clé de session et réglages (modèle : `.env.exemple`) |

En production (`TUTO_ENV=production`, posé par l'image) : connexion
obligatoire sur toutes les pages et tous les fichiers, pas de documentation
`/docs`, et le HTML produit n'embarque plus la barre d'édition — on annote dans
le composeur. Seuls `/connexion` et `/sante` sont publics.

## Préparer le VPS (une fois)

À vérifier ou faire sur l'infrastructure :

1. **Docker et Docker Compose** installés (`docker compose version`).
2. **DNS** : un enregistrement A (ou AAAA) du sous-domaine vers l'IP du VPS.
3. **Envoy** : ajouter le virtual host et le cluster — modèle commenté dans
   [`deploy/envoy-exemple.yaml`](deploy/envoy-exemple.yaml). Deux points
   d'attention :
   - **délai de route à 120 s** : « Enregistrer & générer » produit le PDF dans
     la requête, et le défaut d'Envoy (15 s) peut couper un long tutoriel ;
   - **adresse du service** : `127.0.0.1:8000` si Envoy tourne sur l'hôte. Si
     Envoy tourne *dans un conteneur*, le raccorder au réseau Docker du projet et
     viser `app:8000` — et retirer alors la section `ports` du compose.
4. **Certificat TLS** du sous-domaine, géré par Envoy (comme les autres sites).

## Première installation

```bash
git clone <dépôt> /opt/tuto-generator
cd /opt/tuto-generator

mkdir -p data sauvegardes
cp .env.exemple .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # → TUTO_SECRET_KEY dans .env
chmod 600 .env

docker compose up -d --build
docker compose logs -f          # attendre « Uvicorn running », puis Ctrl+C
```

Créer un compte par personne (le mot de passe est demandé, 10 caractères
minimum) :

```bash
docker compose exec app admin compte-ajouter baptiste --nom "Baptiste Lemoine"
docker compose exec app admin compte-ajouter prenom --nom "Prénom Nom"
docker compose exec app admin comptes
```

Le nom sert d'auteur par défaut des nouveaux tutoriels. Relancer
`compte-ajouter` sur un identifiant existant change son mot de passe ;
`compte-supprimer` coupe aussitôt ses sessions.

Le volume démarre **vide** : les tutoriels de `vault-articles/articles/` du
dépôt (essais de développement) ne sont pas embarqués dans l'image. Pour en
reprendre un : `cp -r vault-articles/articles/<id> data/vault/articles/`.

## Sauvegardes

Le dossier `./data` est la seule chose à sauvegarder (les PDF et HTML sont
régénérables). Script fourni, à planifier par cron sur le VPS :

```bash
crontab -e
# chaque nuit à 3 h 15, 14 archives conservées
15 3 * * *  cd /opt/tuto-generator && ./deploy/sauvegarde.sh >> sauvegardes/journal.log 2>&1
```

Les archives vont dans `./sauvegardes/`, **sur le même disque** : elles
protègent d'une erreur de manipulation, pas d'une perte du VPS. Les copier
aussi ailleurs (rsync vers une autre machine, sauvegarde de l'hébergeur).

**Restaurer :**

```bash
docker compose down
mv data data.avant-restauration
tar -xzf sauvegardes/tuto-data-AAAA-MM-JJ-HHMM.tar.gz      # recrée ./data
docker compose up -d
docker compose exec app admin generer-tout                # reconstruit PDF et HTML
```

## Mettre à jour

```bash
cd /opt/tuto-generator
git pull
docker compose up -d --build
```

Le volume n'est pas touché. `templates/` et `charte/` sont recopiés depuis
l'image au démarrage : **modifier la charte ou un template, c'est modifier le
dépôt puis redéployer**. Après un tel changement, régénérer les documents :

```bash
docker compose exec app admin generer-tout
```

## Exploiter

```bash
docker compose ps                      # état et healthcheck
docker compose logs -f                 # activité en direct
docker compose logs --since 24h | grep tuto.
du -sh data sauvegardes                # place prise sur le disque
```

Une ligne par événement : connexions (réussies et refusées, avec l'IP),
enregistrements (qui, quel tutoriel, durée, PDF produit ou non),
téléversements, échecs de génération. Les logs Docker tournent sur
5 × 10 Mo. Niveau réglable par `TUTO_LOG_LEVEL` dans `.env`.

## Réglages (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `TUTO_SECRET_KEY` | — (obligatoire) | signe les sessions ; la changer déconnecte tout le monde |
| `TUTO_SESSION_HEURES` | `168` | durée d'une session (7 jours) |
| `TUTO_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `FORWARDED_ALLOW_IPS` | `*` | proxys de confiance pour `X-Forwarded-*` ; `*` tant que le port n'est joignable que par Envoy |

Posés par l'image, à ne changer qu'en connaissance de cause : `TUTO_ENV`,
`TUTO_VAULT_DIR`, `TUTO_COMPTES`, `TUTO_AUTH`, `TUTO_EDITEUR_AUTONOME`.

## Sécurité : ce qui est fait, ce qui ne l'est pas

Fait : connexion obligatoire (mots de passe hachés en scrypt, cookie signé
`HttpOnly` + `Secure` + `SameSite=Lax`, ce qui protège aussi des requêtes
forgées depuis un autre site), fichiers bruts protégés, pas de redirection vers
un site tiers après connexion, une seconde de pénalité par mot de passe erroné,
serveur non-root, pas de CORS ni de documentation d'API en production.

Volontairement laissé de côté pour cette version interne (voir CLAUDE.md §7) :
contrôle du contenu et de la taille des images téléversées, détection des
conflits si deux personnes modifient le même tutoriel au même moment (le
dernier enregistrement l'emporte), nettoyage renforcé du HTML des annotations.
Ces points deviennent nécessaires si l'outil s'ouvre au-delà de l'équipe.
