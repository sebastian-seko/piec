#!/bin/bash
set -e

REPO_URL=https://github.com/sebastian-seko/piec
INSTALL_DIR=/home/pi/piec
SERVICE_FILE=/etc/systemd/system/piec.service
DATA_DIR=/data
FSTAB_ENTRY="tmpfs ${DATA_DIR} tmpfs defaults,size=1m,noatime 0 0"
SKIP_DEPS=0

# Parsowanie argumentów
for arg in "$@"; do
    case $arg in
        --skip-deps|-s) SKIP_DEPS=1 ;;
        *) echo "Nieznany argument: $arg"; echo "Użycie: $0 [--skip-deps|-s]"; exit 1 ;;
    esac
done

# Sprawdzenie uprawnień root
if [ "$(id -u)" -ne 0 ]; then
    echo "BŁĄD: Skrypt musi być uruchomiony jako root (sudo)." >&2
    exit 1
fi

# Instalacja wymaganych pakietów systemowych
if [ "$SKIP_DEPS" -eq 1 ]; then
    echo "==> Pomijanie instalacji zależności (--skip-deps)"
else
    echo "==> Instalacja zależności systemowych..."
    apt-get update -qq
    apt-get install -y git python3 python3-serial python3-paho-mqtt apache2 libapache2-mod-php
fi

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

# Katalog na dane trwale (karta SD, przetrwa restart) - np. historia alarmow
PERSIST_DIR=/home/pi/piec_dane
echo "==> Katalog danych trwałych: $PERSIST_DIR"
mkdir -p "$PERSIST_DIR"

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

# --- Publikator MQTT (osobna usługa, tylko czyta pliki parsera) ---
echo "==> Usługa MQTT (piec-mqtt)..."
MQTT_CONF=/home/pi/mqtt.ini
# przeniesienie ze starej lokalizacji, jesli ktos ja juz mial
if [ ! -f "$MQTT_CONF" ] && [ -f /etc/piec/mqtt.ini ]; then
    mv /etc/piec/mqtt.ini "$MQTT_CONF"
    rmdir /etc/piec 2>/dev/null || true
    echo "    Przeniesiono /etc/piec/mqtt.ini -> $MQTT_CONF"
fi
if [ ! -f "$MQTT_CONF" ]; then
    cp "$INSTALL_DIR/config/mqtt.ini.example" "$MQTT_CONF"
    echo "    Utworzono $MQTT_CONF z szablonu (wlaczone = nie)."
    echo "    Uzupełnij host/uzytkownik/haslo, ustaw wlaczone = tak i uruchom ponownie install.sh."
fi
# wlasciciel pi (edycja bez sudo), prawa 600: nikt inny (np. Apache) nie przeczyta hasla;
# usluga dziala jako root, wiec i tak go odczyta
chown pi:pi "$MQTT_CONF"
chmod 600 "$MQTT_CONF"
cp "$INSTALL_DIR/config/piec-mqtt.service" /etc/systemd/system/piec-mqtt.service
systemctl daemon-reload
if grep -Eiq '^[[:space:]]*wlaczone[[:space:]]*=[[:space:]]*(tak|yes|true|1)[[:space:]]*$' "$MQTT_CONF"; then
    if python3 -c "import paho.mqtt.client" 2>/dev/null; then
        systemctl enable piec-mqtt
        systemctl restart piec-mqtt
        echo "    piec-mqtt włączona."
    else
        echo "    BRAK biblioteki paho-mqtt - uruchom install.sh bez --skip-deps"
        echo "    (albo: sudo apt-get install -y python3-paho-mqtt)"
    fi
else
    systemctl disable --now piec-mqtt 2>/dev/null || true
    echo "    MQTT wyłączone w $MQTT_CONF (wlaczone = nie) - usługa nieaktywna."
fi

echo ""
echo "==> Gotowe. Status usługi:"
systemctl status piec --no-pager
