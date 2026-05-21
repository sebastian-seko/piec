#!/bin/bash
set -e

REPO_URL=https://github.com/sebastian-seko/piec
INSTALL_DIR=/home/pi/piec
SERVICE_FILE=/etc/systemd/system/piec.service
DATA_DIR=/data

echo "==> Tworzenie katalogu danych..."
mkdir -p "$DATA_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Aktualizacja repozytorium w $INSTALL_DIR..."
    git -C "$INSTALL_DIR" pull
else
    echo "==> Klonowanie repozytorium z $REPO_URL..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

echo "==> Instalacja zależności Python..."
apt-get install -y python3-serial

echo "==> Instalacja pliku usługi systemd..."
cp "$INSTALL_DIR/config/piec.service" "$SERVICE_FILE"

echo "==> Kopiowanie plików web do /var/www/html..."
cp -r "$INSTALL_DIR/web/." /var/www/html/

echo "==> Restart Apache..."
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
