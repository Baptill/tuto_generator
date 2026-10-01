#!/bin/sh
# Démarrage du conteneur : prépare le volume de données, puis sert l'application.
set -e

# Le volume monté appartient à l'utilisateur de l'hôte. On le confie à
# l'utilisateur de l'application, puis on abandonne les droits root : le
# serveur ne tourne jamais en root.
if [ "$(id -u)" = "0" ]; then
  if [ "$(stat -c %u /data)" != "$(id -u tuto)" ]; then
    chown -R tuto:tuto /data
  fi
  exec setpriv --reuid=tuto --regid=tuto --init-groups "$0" "$@"
fi

python -m app.cli init-vault

# --proxy-headers : l'IP du visiteur et le schéma (https) viennent des en-têtes
# X-Forwarded-* posés par Envoy. FORWARDED_ALLOW_IPS restreint les proxys de
# confiance (« * » convient tant que le port n'est joignable que par Envoy).
exec uvicorn app.serveur:app \
  --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}" \
  --no-server-header
