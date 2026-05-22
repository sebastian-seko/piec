#!/bin/bash
set -e

REPO_URL=https://github.com/sebastian-seko/piec
INSTALL_DIR=/home/pi/piec
SERVICE_FILE=/etc/systemd/system/piec.service
DATA_DIR=/data
FSTAB_ENTRY="tmpfs ${DATA_DIR} tmpfs defaults,size=1m,noatime 0 0"

# Sprawdzenie uprawnień root
if [ "$(id -u)" -ne 0 ]; then
    echo "BŁĄD: Skrypt musi być uruchomiony jako root (sudo)." >&2
    exit 1
fi

# Instalacja wymaganych pakietów systemowych
echo "==> Instalacja zależności systemowych..."
apt-get update -qq
apt-get install -y git python3 python3-serial apache2 libapache2-mod-php

# Konfiguracja /data/ jako tmpfs (1 MB w RAM)
echo "==> Konfiguracja /data/ jako tmpfs (1 MB)..."
mkdir -p "$DATA_DIR"
if ! grep -qF "$DATA_DIR" /etc/fstab; then
    echo "$FSTAB_ENTRY" >> /etc/fstab
    echo "    Dodano wpis tmpfs do /etc/fstab"
fi
if ! mountpoint -q "$DATA_DIR"; then
    mount "$DATA_DIR"
    echo "    Zamontowano /data/"
else
    echo "    /data/ jest już zamontowany"
fi

# Klonowanie lub aktualizacja repozytorium
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Aktualizacja repozytorium w $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" reset --hard origin/main
else
    echo "==> Klonowanie repozytorium z $REPO_URL..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

echo "==> Instalacja pliku usługi systemd..."
cp "$INSTALL_DIR/config/piec.service" "$SERVICE_FILE"

echo "==> Kopiowanie plików web do /var/www/html..."
cp -r "$INSTALL_DIR/web/." /var/www/html/

echo "==> Restart Apache..."
systemctl enable apache2
systemctl restart apache2

echo "==> Przeładowanie konfiguracji systemd..."
systemctl daemon-reload

echo "==> Włączanie usługi przy starcie systemu..."
systemctl enable piec

echo "==> Restart usługi..."
systemctl restart piec

echo ""
echo "==> Gotowe. Status usługi:"
systemctl status piec --no-pager
