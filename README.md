# Piec — System Monitorowania Kotła

System do monitorowania stanu kotła grzewniczego (EcoMax 850 P2) i termostatów pokojowych (EcoSter/EcoTouch) podłączonych przez interfejs EcoNet (RS485).

## Wymagania

**Sprzęt:**
- Raspberry Pi (3B+ lub nowszy rekomendowany)
- Interfejs USB-RS485 (np. CH340, FTDI)
- Sieć LAN do nagrywania backupów (opcjonalnie)

**System operacyjny:**
- Raspberry Pi OS (Bullseye, Bookworm) - testowane

## Instalacja

### Pierwsza instalacja (pełna)

```bash
cd ~/piec
sudo ./install.sh
```

Skrypt:
- Instaluje zależności (`git`, `python3`, `apache2`, `php`)
- Tworzy partycję RAM `/data/` (1 MB tmpfs) 
- Klonuje/aktualizuje repozytorium
- Konfiguruje usługę systemd (`piec.service`)
- Udostępnia interfejs web przez Apache

### Aktualizacja (szybka, bez instalacji pakietów)

```bash
sudo ./install.sh --skip-deps
sudo ./install.sh -s
```

## Konfiguracja

### Katalog `/data/`

Partycja RAM o rozmiarze 1 MB, automatycznie montowana przy starcie:
- `/data/odczyty.txt` — aktualne odczyty (CSV)
- `/data/odczyty.json` — aktualne odczyty z nazwanymi polami (z tego czyta web)
- `/data/message.txt` / `/data/message.json` — surowa ostatnia ramka ecoMAX
- `/data/nieznane.json` — ostatnia ramka każdego nieobsługiwanego rodzaju
- `/data/raw.txt` — dane wejściowe (jeśli `SOURCE = 'FILE'`)

### Katalog `/home/pi/piec_dane/` (karta SD, przetrwa restart)

- `alarmy/alarm_*.json` — historia alarmów (ramki przed/w trakcie, inne ramki, polecenia, sposób zakończenia)
- `polecenia.jsonl` — każda ramka spoza cyklicznego odpytywania: polecenia z panelu
  (0x70 zmiana parametru, 0x61 odczyt tabeli, 0x71 kasowanie alarmu…) i odpowiedzi pieca
  (0xF0/0xE1/0xF1…), z opisem, pełną ramką i stanem pieca przed/po
- `parametry.json` — ostatnia tabela nastaw sterownika (191 parametrów: wartość, min, max)
- `parametry/parametry_*.json` — każda odebrana tabela (migawki, max 1000)
- `parametry_zmiany.jsonl` — które parametry zmieniły się między kolejnymi tabelami
- `kasowanie_alarmu.log` — dziennik ręcznego narzędzia `narzedzia/kasuj_alarm.py`

#### Jak nazwać kolejne parametry

Panel odczytuje tabelę nastaw (0x61 → 0xE1) po każdej zmianie w menu. Żeby ustalić,
co oznacza dany numer:

1. zmień w menu panelu jedno ustawienie (zapamiętaj starą i nową wartość),
2. sprawdź `tail /home/pi/piec_dane/parametry_zmiany.jsonl` — pojawi się numer parametru
   z wartościami `bylo` → `jest` (oraz w `polecenia.jsonl` ramka 0x70 z tym numerem),
3. dopisz nazwę w `src/ecomax850p2.py` → `PARAMETRY_NAZWY`.

Znane dziś: 49 = temperatura zadana CO, 52 = temperatura zadana CWU.

### Narzędzia ręczne

`narzedzia/kasuj_alarm.py` — eksperymentalne ręczne kasowanie alarmu przez RS-485.
Nie uruchamia się automatycznie. Opis, ryzyka i procedura: [narzedzia/README.md](narzedzia/README.md).

### Port szeregowy

Domyślnie `/dev/ttyUSB0` (szybkość 115200 baud), konfigurowalny w `src/start.py`:

```python
SOURCE = 'SERIAL'
serialPORT = '/dev/ttyUSB0'
serialBAUDRATE = 115200
```

## Interfejs Web

### `/index.php` — tekstowy (oryginał)

Prosty, wierny format tekstowy — działa na wszystkim. Edytuj bezpośrednio w pliku.

```
Stan = PRACA
Dwór = 15.2 °C
CWU = 52.3 °C | Zadana = 55 °C
CO = 65.1 °C | Zadana = 70 °C
...
```

### `/piec.php` — graficzny dashboard

Nowoczesny interfejs z kartami, paskami postępu i kolorowaniem statusu.  
**Kompatybilny z iPad 2 (iOS 9.3.5) i Safari.**

**Adresy:**
- `http://<ip-raspberry>/index.php` — tekstowy
- `http://<ip-raspberry>/piec.php` — graficzny

## Backup

### Tworzenie kopii zapasowej

```bash
sudo ./backup.sh
```

Skrypt:
- Sprawdza czy `image-backup` jest zainstalowany
- Montuje udział sieciowy `\\192.168.2.150\Backup` (jeśli nie zmontowany)
- Tworzy obraz SD karty Raspberry Pi (datowany: `YYYY-MM-DD_HHMMSS.img`)
- Zapisuje do `/mnt/backup/`

### Konfiguracja poświadczeń SMB

Poświadczenia przechowywane w `/etc/backup-credentials` (tylko root może czytać):

```
username=PiecKpol
password=pass
```

Plik tworzony automatycznie przy pierwszym uruchomieniu. Edytuj:

```bash
sudo nano /etc/backup-credentials
```

### Harmonogram backupu (cron)

Automatyczny backup co 3 miesiące o 3:00 rano:

```bash
sudo crontab -e
```

Dodaj linię:

```cron
0 3 1 */3 * /home/pi/piec/backup.sh >> /var/log/piec-backup.log 2>&1
```

**Inne opcje:**
- `0 3 * * *` — codziennie
- `0 3 * * 0` — raz w tygodniu (niedziela)
- `0 3 1 * *` — raz w miesiącu

Sprawdzenie logów:

```bash
tail -f /var/log/piec-backup.log
```

## Struktura projektu

```
piec/
├── README.md              # Ten plik
├── install.sh             # Skrypt instalacji
├── backup.sh              # Skrypt backupu
├── src/
│   ├── start.py          # Główny program (słucha portu szeregowego)
│   ├── ecomax850p2.py    # Parser komunikatów kotła
│   ├── ecoster.py        # Parser komunikatów termostatów
│   └── entrypoint.sh     # Restarter (legacy)
├── config/
│   └── piec.service      # Usługa systemd
└── web/
    ├── index.php         # Interfejs tekstowy
    └── piec.php          # Interfejs graficzny
```

## Rozwiązywanie problemów

### Błąd: SMB — "Server abruptly closed the connection"

Serwer NAS używa SMBv1 (przestarzały). Skrypt automatycznie dodaje `vers=1.0`.  
Jeśli nadal nie działa, sprawdź kernel:

```bash
dmesg | grep -i smb
```

Jeśli SMBv1 wyłączony, włącz:

```bash
echo "options cifs enable_legacy_dialects=1" | sudo tee /etc/modprobe.d/cifs.conf
sudo modprobe -r cifs && sudo modprobe cifs
```

### Usługa nie startuje

Sprawdź status:

```bash
sudo systemctl status piec
sudo journalctl -u piec -n 50
```

Uruchomienie ręczne (debug):

```bash
cd ~/piec/src
python3 start.py
```

### Interfejs web nie odświeża się

Sprawdzenie czy `/data/` jest zamontowany:

```bash
mount | grep /data
```

Jeśli brakuje, zamontuj ręcznie:

```bash
sudo mount /data
```

### Brak danych w `odczyty.txt`

Port szeregowy nie odpowiada. Sprawdź:

```bash
ls -la /dev/ttyUSB*
sudo dmesg | tail -20
```

## API — format danych (`odczyty.txt`)

CSV, jeden wiersz:

```
tempCWU, tempCO, tempDwor, tempPalnik, tempMieszacz, stan, setCO, setCWU, setMieszacz, nadmuch%, mieszaczProc%, fuelStream, mocKotla
```

**Przykład:**
```
52.3,65.1,15.2,45.0,40.5,PRACA,70,55,50,75,60,2.1,18.5
```

## Licencja

EcoNet parser — (C) 2020 Tomasz Król (https://github.com/twkrol/econetanalyze)  
Dodatkowy kod — właściciel projektu

---

**Ostatnia aktualizacja:** 2026-06-03
