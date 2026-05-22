#!/bin/bash
set -e

SHARE="//192.168.2.150/Backup"
MOUNT_POINT="/mnt/backup"
CREDENTIALS_FILE="/etc/backup-credentials"

# Sprawdzenie uprawnień root
if [ "$(id -u)" -ne 0 ]; then
    echo "BŁĄD: Skrypt musi być uruchomiony jako root (sudo)." >&2
    exit 1
fi

# Sprawdzenie czy image-backup jest zainstalowany
if ! command -v image-backup >/dev/null 2>&1; then
    echo "BŁĄD: image-backup nie jest zainstalowany." >&2
    echo "      Zainstaluj: https://github.com/rpi-imager/image-backup" >&2
    exit 1
fi

# Sprawdzenie pliku credentials
if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo "==> Tworzenie pliku credentials: $CREDENTIALS_FILE"
    cat > "$CREDENTIALS_FILE" <<EOF
username=PiecKpol
password=pass
EOF
    chmod 600 "$CREDENTIALS_FILE"
    echo "    Plik utworzony. Edytuj $CREDENTIALS_FILE aby zmienić dane."
fi

# Montowanie udziału sieciowego jeśli nie jest zamontowany
mkdir -p "$MOUNT_POINT"
if ! mountpoint -q "$MOUNT_POINT"; then
    echo "==> Montowanie $SHARE..."
    if ! dpkg -s cifs-utils >/dev/null 2>&1; then
        echo "    Instalacja cifs-utils..."
        apt-get install -y cifs-utils
    fi
    mount -t cifs "$SHARE" "$MOUNT_POINT" \
        -o "credentials=${CREDENTIALS_FILE},uid=pi,gid=pi,iocharset=utf8,vers=1.0"
    echo "    Zamontowano $SHARE -> $MOUNT_POINT"
else
    echo "==> $MOUNT_POINT jest już zamontowany"
fi

# Wykonanie kopii zapasowej
now=$(printf "%(%F_%H%M%S)T")
echo "==> Tworzenie obrazu: ${MOUNT_POINT}/${now}.img"
image-backup --initial "${MOUNT_POINT}/${now}.img,,8000"

echo "==> Backup zakończony."
