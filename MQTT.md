# MQTT → Home Assistant

Publikator `src/piec_mqtt.py` (usługa `piec-mqtt`) wysyła dane pieca do brokera
MQTT (dodatek Mosquitto w HA). Encje w HA tworzą się same (MQTT Discovery).

## Jak to jest zbudowane

```
RS-485 ─▶ start.py (usługa piec) ─▶ /data/odczyty.json, /data/diag.json (RAM)
                                    /home/pi/piec_dane/... (karta SD)
                                            │  tylko odczyt plików
                                            ▼
                                 piec_mqtt.py (usługa piec-mqtt)
                                            │  VPN
                                            ▼
                                  Mosquitto w Home Assistant
```

- **Parser nie wie nic o sieci.** Zerwany tunel, wolny albo wyłączony broker
  dotyczą tylko publikatora, a łapanie ramek działa bez zmian.
- Publikator to osobny proces o niższym priorytecie (`Nice=10`). Gdy padnie,
  systemd uruchomi go ponownie po 10 s.
- **Tylko publikacja.** Publikator nie subskrybuje żadnych tematów, więc z HA
  nie da się niczego wysłać do pieca.
- `all.php` działa dalej równolegle, więc można przechodzić stopniowo.

## Uruchomienie

1. Wgraj zmiany (commit i push), potem na Pi uruchom **bez** `--skip-deps`
   (doinstaluje `python3-paho-mqtt`):
   ```bash
   sudo ./install.sh
   ```
   Przy pierwszym uruchomieniu powstanie `/home/pi/mqtt.ini` z `wlaczone = nie`.
2. Uzupełnij konfigurację:
   ```bash
   nano /home/pi/mqtt.ini
   ```
   Ustaw `host` (adres HA przez VPN), `uzytkownik`, `haslo`, `wlaczone = tak`.
   Użytkownika MQTT najlepiej założyć osobnego (HA → Ustawienia → Osoby →
   Użytkownicy, albo w konfiguracji dodatku Mosquitto). Plik należy do `pi`
   i ma prawa 600, bo jest w nim hasło. Nie kopiuj go do katalogu repo.
3. Uruchom ponownie:
   ```bash
   sudo ./install.sh --skip-deps
   ```
4. Sprawdź:
   ```bash
   systemctl status piec-mqtt
   journalctl -u piec-mqtt -f
   ```
   W HA: Ustawienia → Urządzenia → MQTT → **Piec Kpol**.

Wyłączenie: `wlaczone = nie` w `/home/pi/mqtt.ini` i ponownie
`sudo ./install.sh --skip-deps`.

## Tematy

| temat | treść | retain | kiedy |
|---|---|---|---|
| `piec/polaczenie` | `online` / `offline` | tak | publikator ↔ broker; `offline` ustawia sam broker (LWT), gdy publikator zniknie albo tunel padnie (po ok. 45 s przy `keepalive = 30`) |
| `piec/status` | `online` / `offline` | tak | świeżość danych: `offline`, gdy ostatnia ramka z pieca jest starsza niż 120 s (np. parser stoi, odłączony kabel RS-485) |
| `piec/stan` | JSON, te same pola co `all.php` | tak | przy każdej zmianie wartości, najrzadziej co 30 s |
| `piec/alarm` | `{"alarm", "alarm_kod", "alarm_opis"}` | tak | przy zmianie |
| `piec/parametry` | tabela nastaw `{nr: {nazwa, wartosc, min, max}}` | tak | gdy panel odczyta nową tabelę |
| `piec/diag` | ramki/min, odrzucone/min, wiek odczytu, zaległe zdarzenia | tak | co 10 s |
| `piec/zdarzenia/alarm` | `zdarzenie: start/koniec`, kod, opis, sposób zakończenia | nie (QoS 1) | start i koniec każdego alarmu |
| `piec/zdarzenia/polecenie` | każda linia z `polecenia.jsonl` (kasowanie alarmu, zmiana parametru, odczyt tabeli…) | nie (QoS 1) | gdy panel coś wyśle |

`piec/stan` zawiera wszystkie pola z `all.php` poza `timestamp` (to czas
zapytania HTTP, w MQTT bez znaczenia). Czas ramki jest w polu `odczyt`.

### Zdarzenia po przerwie w łączności

Zdarzenia (`zdarzenia/*`) nie giną, gdy tunel padnie. Publikator zapamiętuje
w `/home/pi/piec_dane/mqtt_pozycja.json`, dokąd doszedł w `polecenia.jsonl`
i katalogu `alarmy/`. Po powrocie łączności wysyła zaległe po kolei, każde
z potwierdzeniem brokera (QoS 1). Pozycja przesuwa się dopiero po potwierdzeniu.
Wyjątkowo zdarzenie może przyjść dwa razy (gdy tunel padnie dokładnie
w chwili potwierdzania), ale nigdy nie zginie.

Przy **pierwszym** uruchomieniu publikator nie wysyła starej historii, tylko
to, co pojawi się od tej chwili. Wyjątek: trwający właśnie alarm.

Bieżących odczytów (`piec/stan`) nie kolejkujemy. Po przerwie liczy się
ostatnia wartość, którą publikator wysyła od razu po połączeniu.

## Encje w HA

Wszystkie pod urządzeniem **Piec Kpol**. Identyfikatory HA nada sam, np.
`sensor.piec_kpol_temperatura_cwu`, `binary_sensor.piec_kpol_alarm`.

- **Sensory:** temperatury (CWU, CO, zewnętrzna, palnik, mieszacz), zadane (CO, CWU,
  mieszacza), nadmuch, otwarcie mieszacza, płomień, moc, strumień paliwa,
  godziny pracy (100/50/30%, podajnik), liczba rozpaleń, stan, status mieszacza,
  kod i opis alarmu, ostatni odczyt.
- **Binarne:** alarm (`problem`), pompy CO/CWU/mieszacza, zapalarka, wentylator,
  podajnik, podajnik 2, siłownik czyszczący.
- **Diagnostyczne:** ramki/min, odrzucone ramki/min, wiek odczytu,
  zaległe zdarzenia MQTT, bajt 198, wyjścia (bajt 29).

Dostępność:
- odczyty są **niedostępne**, gdy `piec/polaczenie` albo `piec/status` = `offline`,
- diagnostyka zależy tylko od `piec/polaczenie`, więc gdy parser stoi, dalej
  widać „Wiek odczytu” i liczniki ramek, czyli *dlaczego* dane są nieaktualne.

### Jak czytać diagnostykę

- **Ramki na minutę:** normalnie ok. 440–460. W logu z 27.12.2024 było 1097
  ramek w ok. 150 s: ok. 1,2 cyklu na sekundę, w każdym ramka stanu 0x08,
  odpowiedź panelu i 4–6 zapytań pieca. Nagły spadek = problem z kablem lub przejściówką.
- **Odrzucone ramki na minutę:** powinno być 0. Pojedyncze sztuki się zdarzają
  (zakłócenia). Stała wartość > 0 = do sprawdzenia, a szczegóły rodzaju błędu
  (`krotsza` / `dluzsza` / `crc`) są w `/data/diag.json`.

## Przejście z REST na MQTT

Encje MQTT mają inne `unique_id` (`piec_kpol_*`) niż te z REST (`pieckpol_*`),
więc przez jakiś czas mogą działać obie wersje obok siebie. Gdy MQTT działa:

1. przepnij dashboardy i automatyzacje na nowe encje,
2. usuń sekcję `rest:` z YAML i automatyzację „brak świeżych danych”: zastępuje
   ją dostępność encji (zrobi się *niedostępna*, gdy danych brak).

## Przykładowe automatyzacje

```yaml
automation:
  # Alarm: od razu z tematu zdarzeń (bez czekania na odpytywanie)
  - id: piec_mqtt_alarm
    alias: "Piec – alarm (MQTT)"
    triggers:
      - trigger: mqtt
        topic: piec/zdarzenia/alarm
    actions:
      - if: "{{ trigger.payload_json.zdarzenie == 'start' }}"
        then:
          - action: persistent_notification.create
            data:
              notification_id: piec_alarm
              title: "Piec – ALARM"
              message: >
                {{ trigger.payload_json.opis }} (kod {{ trigger.payload_json.kod }}),
                od {{ trigger.payload_json.poczatek }}
        else:
          - action: persistent_notification.dismiss
            data:
              notification_id: piec_alarm
          - action: persistent_notification.create
            data:
              title: "Piec – koniec alarmu"
              message: >
                {{ trigger.payload_json.opis }}: {{ trigger.payload_json.sposob_zakonczenia }},
                stan po: {{ trigger.payload_json.stan_po_alarmie }}

  # Każde polecenie z panelu (zmiana nastawy, kasowanie alarmu...)
  - id: piec_mqtt_polecenie
    alias: "Piec – polecenie z panelu (MQTT)"
    triggers:
      - trigger: mqtt
        topic: piec/zdarzenia/polecenie
    conditions:
      - "{{ trigger.payload_json.rodzaj in ['zmiana_parametru', 'kasowanie_alarmu'] }}"
    actions:
      - action: logbook.log
        data:
          name: "Piec"
          message: "{{ trigger.payload_json.opis }}"

  # Brak połączenia z Pi albo parser stoi
  - id: piec_mqtt_niedostepny
    alias: "Piec – brak danych (MQTT)"
    triggers:
      - trigger: state
        entity_id: sensor.piec_kpol_temperatura_co
        to: "unavailable"
        for: "00:05:00"
    actions:
      - action: persistent_notification.create
        data:
          title: "Piec"
          message: >
            Brak danych z pieca od 5 minut.
            Wiek odczytu: {{ states('sensor.piec_kpol_wiek_odczytu') }} s
            (jeśli też niedostępny, to brak połączenia z Pi / VPN).
```

Identyfikatory encji w przykładach mogą się u Ciebie różnić (zależą od
nazw nadanych przez HA). Sprawdź je w Ustawienia → Encje → filtr „piec_kpol”.

## Dane techniczne

- Biblioteka `paho-mqtt` 1.6 (Raspberry Pi OS Bookworm) i 2.x (nowsze). Kod
  obsługuje obie i obie były testowane.
- Ponowne łączenie: co 1 s, potem coraz rzadziej, najwyżej co 60 s.
- Konfiguracja: `/home/pi/mqtt.ini` (szablon `config/mqtt.ini.example`),
  usługa: `config/piec-mqtt.service`.
