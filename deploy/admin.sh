#!/bin/sh
# Commandes d'administration dans le conteneur, toujours exécutées sous
# l'utilisateur de l'application (sinon un fichier créé en root, comme
# comptes.yaml, deviendrait illisible pour le serveur).
#
#   docker compose exec app admin compte-ajouter baptiste --nom "Baptiste Lemoine"
#   docker compose exec app admin comptes
#   docker compose exec app admin generer-tout
set -e
if [ "$(id -u)" = "0" ]; then
  exec setpriv --reuid=tuto --regid=tuto --init-groups "$0" "$@"
fi
exec python -m app.cli "$@"
