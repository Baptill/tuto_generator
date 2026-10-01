#!/bin/sh
# Sauvegarde quotidienne du volume de données (tutoriels, images, annotations,
# comptes). À lancer par cron sur le VPS, depuis le dossier du projet :
#
#   15 3 * * *  cd /opt/tuto-generator && ./deploy/sauvegarde.sh >> sauvegardes/journal.log 2>&1
#
# Garde les N dernières archives (défaut 14). Une sauvegarde restée sur le même
# disque ne protège pas d'une perte du VPS : copier aussi DOSSIER ailleurs
# (rsync, stockage de l'hébergeur…).
set -eu

SOURCE="${SOURCE:-./data}"
DOSSIER="${DOSSIER:-./sauvegardes}"
GARDER="${GARDER:-14}"

mkdir -p "$DOSSIER"
archive="$DOSSIER/tuto-data-$(date +%Y-%m-%d-%H%M).tar.gz"
# Les sorties (HTML/PDF) sont un cache régénérable : inutile de les archiver.
tar --exclude='*/output' -czf "$archive" -C "$(dirname "$SOURCE")" "$(basename "$SOURCE")"
echo "$(date '+%F %T') sauvegarde $archive ($(du -h "$archive" | cut -f1))"

# Rotation : on supprime les plus anciennes au-delà de GARDER.
ls -1t "$DOSSIER"/tuto-data-*.tar.gz | tail -n +"$((GARDER + 1))" | while read -r vieille; do
  rm -f "$vieille"
  echo "$(date '+%F %T') supprimée $vieille"
done
