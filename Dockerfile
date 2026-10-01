# Image de production du composeur de tutoriels (voir DEPLOIEMENT.md).
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# WeasyPrint s'appuie sur Pango/HarfBuzz pour la mise en page du texte.
# DejaVu sert de police de secours pour les glyphes absents d'Inter.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code, puis modèles livrés avec lui (templates + charte), recopiés dans le
# volume de données au démarrage par `init-vault`.
COPY app/ app/
COPY vault-articles/templates/ vault-articles/templates/
COPY vault-articles/charte/ vault-articles/charte/
COPY deploy/demarrer.sh /usr/local/bin/demarrer
COPY deploy/admin.sh /usr/local/bin/admin

# Utilisateur sans privilège ; /data est le volume (tutoriels + comptes).
# Le conteneur démarre en root le temps d'ajuster les droits du volume, puis
# `demarrer` bascule sur cet utilisateur (setpriv) avant de lancer le serveur.
RUN useradd --uid 1000 --create-home tuto \
 && mkdir -p /data \
 && chown tuto:tuto /data \
 && chmod +x /usr/local/bin/demarrer /usr/local/bin/admin

ENV TUTO_ENV=production \
    TUTO_VAULT_DIR=/data/vault \
    TUTO_COMPTES=/data/comptes.yaml \
    FORWARDED_ALLOW_IPS=*

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/sante', timeout=4)"

CMD ["demarrer"]
