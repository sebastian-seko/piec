#!/usr/bin/env python3
"""
Publikator MQTT dla Home Assistant - osobna usluga (piec-mqtt).

Czyta WYLACZNIE pliki zapisywane przez parser (start.py) i publikuje je do brokera.
Nie dotyka portu szeregowego, wiec zerwany tunel VPN / wolny broker nie moze
spowolnic ani zablokowac lapania ramek. Gdy ten proces padnie, parser dziala dalej.

Tylko publikacja: nie subskrybuje zadnych tematow, z HA nie da sie nic wyslac do pieca.

Konfiguracja: /home/pi/mqtt.ini (szablon: config/mqtt.ini.example)
"""

import configparser
import json
import os
import signal
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt

KONFIG = os.environ.get("PIEC_MQTT_KONFIG", "/home/pi/mqtt.ini")

# --- pliki zapisywane przez parser -------------------------------------------
ODCZYTY = "/data/odczyty.json"
DIAG = "/data/diag.json"
DANE = "/home/pi/piec_dane"
POLECENIA = DANE + "/polecenia.jsonl"
ALARMY = DANE + "/alarmy"
PARAMETRY = DANE + "/parametry.json"
POZYCJA = DANE + "/mqtt_pozycja.json"     # dokad doszlismy z wysylaniem zdarzen

DANE_NIEAKTUALNE_S = 120     # starszy odczyt => status "offline" w HA
STAN_CO_S = 30               # stan publikowany przy zmianie, ale nie rzadziej niz co tyle s
DIAG_CO_S = 10
ZDARZEN_NA_PETLE = 50        # limit wysylki zaleglych zdarzen w jednym obiegu


def teraz_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log(t):
    print(f"{teraz_iso()} {t}", flush=True)


def czytaj_json(sciezka):
    try:
        with open(sciezka, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def zapisz_json(sciezka, dane):
    tmp = sciezka + ".tmp"
    os.makedirs(os.path.dirname(sciezka), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)
    os.replace(tmp, sciezka)


def mtime(sciezka):
    try:
        return os.stat(sciezka).st_mtime
    except OSError:
        return None


# --- stan w plaskiej postaci (te same klucze co all.php) ------------------------
def plaski_stan(d):
    o, s, w = d["odczyty"], d["serwis"], d["wyjscia"]
    a = d.get("alarm") or {}
    pz = d.get("panel") or {}
    return {
        "cwu": o["cwu"], "co": o["co"], "dwor": o["dwor"], "palnik": o["palnik"],
        "mieszacz": o["mieszacz"], "stan": o["stan"],
        "zadana_co": o["zadana_co"], "zadana_cwu": o["zadana_cwu"],
        "zadana_mieszacz": o["zadana_mieszacz"],
        "nadmuch": o["nadmuch"], "mieszacz_otwarcie": o["mieszacz_otwarcie"],
        "mieszacz_status": o.get("mieszacz_status"),
        "strumien_paliwa": o["strumien_paliwa"], "moc": o["moc"], "plomien": o["plomien"],
        "praca_max_h": s["praca_max_h"], "praca_sred_h": s["praca_sred_h"],
        "praca_min_h": s["praca_min_h"], "zaplony": s["zaplony"],
        "podajnik_czas_h": s["podajnik_czas_h"],
        "pompa_mieszacz": w["pompa_mieszacz"], "pompa_cwu": w["pompa_cwu"],
        "pompa_piec": w["pompa_piec"], "zapalarka": w["zapalarka"],
        "silownik_czyszczacy": w["silownik_czyszczacy"], "podajnik_2": w["podajnik_2"],
        "podajnik": w["podajnik"], "wentylator": w["wentylator"],
        "alarm": bool(a.get("aktywny")), "alarm_kod": a.get("kod"),
        "alarm_opis": a.get("opis"), "alarm_bajt_198": a.get("bajt_198"),
        "nieudane_proby_rozpalenia": a.get("nieudane_proby_rozpalenia", a.get("bajt_198")),
        "wyjscia2": a.get("wyjscia2"),
        "zegar_panelu": pz.get("zegar"),
        "odchylka_zegara_s": pz.get("odchylka_s"),
        "odczyt": d.get("timestamp"),
    }


# Temperatury z parsera maja setne czesci stopnia, wiec drgaja przy kazdej ramce
# i HA zapisuje do historii nowy wiersz prawie co sekunde. Zaokraglamy je TYLKO
# w kopii wysylanej do MQTT - pliki parsera (odczyty.json, all.php) zostaja dokladne.
TEMPERATURY = ("cwu", "co", "dwor", "palnik", "mieszacz")


def zaokraglij_temperatury(stan, miejsca):
    if miejsca is None or miejsca < 0:
        return stan
    wynik = dict(stan)
    for k in TEMPERATURY:
        v = wynik.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            wynik[k] = round(v, miejsca)
    return wynik


def czekaj_na_publikacje(info, timeout):
    """Czeka na potwierdzenie brokera (QoS 1), maks. timeout s. Dziala z paho 1.5 / 1.6 / 2.x.
    paho < 1.6 nie ma parametru timeout w wait_for_publish() (a bez niego czeka w nieskonczonosc),
    wiec tam sprawdzamy is_published() w petli."""
    if getattr(info, "rc", 0) != 0:
        return False
    try:
        info.wait_for_publish(timeout)
    except TypeError:
        koniec = time.monotonic() + timeout
        while not info.is_published() and time.monotonic() < koniec:
            time.sleep(0.05)
    except (RuntimeError, ValueError):
        return False
    return info.is_published()


def wiek_s(iso):
    try:
        return round(time.time() - datetime.fromisoformat(iso).timestamp())
    except (TypeError, ValueError):
        return None


# --- Home Assistant MQTT Discovery ---------------------------------------------
# (klucz w piec/stan, nazwa, dodatkowe pola)
TEMP = {"unit_of_measurement": "°C", "device_class": "temperature", "state_class": "measurement"}
ZADANA = {"unit_of_measurement": "°C", "device_class": "temperature"}
PROC = {"unit_of_measurement": "%", "state_class": "measurement"}
GODZ = {"unit_of_measurement": "h", "device_class": "duration", "state_class": "total_increasing"}
DIAGN = {"entity_category": "diagnostic"}

SENSORY = [
    ("cwu", "Temperatura CWU", TEMP),
    ("co", "Temperatura CO", TEMP),
    ("dwor", "Temperatura zewnętrzna", TEMP),
    ("palnik", "Temperatura palnika", TEMP),
    ("mieszacz", "Temperatura mieszacza", TEMP),
    ("zadana_co", "Zadana CO", ZADANA),
    ("zadana_cwu", "Zadana CWU", ZADANA),
    ("zadana_mieszacz", "Zadana mieszacza", ZADANA),
    ("nadmuch", "Nadmuch", PROC),
    ("mieszacz_otwarcie", "Otwarcie mieszacza", PROC),
    ("plomien", "Płomień", PROC),
    ("moc", "Moc kotła", {"unit_of_measurement": "kW", "device_class": "power", "state_class": "measurement"}),
    ("strumien_paliwa", "Strumień paliwa", {"unit_of_measurement": "kg/h", "state_class": "measurement"}),
    ("praca_max_h", "Praca na mocy 100%", GODZ),
    ("praca_sred_h", "Praca na mocy 50%", GODZ),
    ("praca_min_h", "Praca na mocy 30%", GODZ),
    ("podajnik_czas_h", "Praca podajnika", GODZ),
    ("zaplony", "Liczba rozpaleń", {"state_class": "total_increasing", "icon": "mdi:fire"}),
    ("stan", "Stan", {"icon": "mdi:information-outline"}),
    ("mieszacz_status", "Status mieszacza", {"icon": "mdi:valve"}),
    ("alarm_kod", "Kod alarmu", {"icon": "mdi:alert-circle-outline"}),
    ("alarm_opis", "Opis alarmu", {"icon": "mdi:alert-circle-outline"}),
    ("odczyt", "Ostatni odczyt", {"device_class": "timestamp"}),
    ("odchylka_zegara_s", "Odchyłka zegara panelu", {"unit_of_measurement": "s", "state_class": "measurement",
                                                     "icon": "mdi:clock-alert-outline"}),
    ("nieudane_proby_rozpalenia", "Nieudane próby rozpalenia", {"state_class": "measurement", "icon": "mdi:fire-alert"}),
    # bajt 29: bit0 mieszacz otwiera, bit1 zamyka, bit2 = wlaczony poza alarmem (nieznane)
    ("wyjscia2", "Wyjścia (bajt 29)", {**DIAGN, "icon": "mdi:bug-outline"}),
]
# Encje kiedys ogloszone, a dzis niepotrzebne - przy kazdym polaczeniu wysylamy pusta
# konfiguracje, zeby HA je usunal (gdyby zdazyly powstac).
# zegar_panelu: zmienia sie co sekunde, zasmiecalby baze HA; wystarczy odchylka.
# Sam zegar zostaje w piec/stan (JSON), all.php i odczyty.json.
# alarm_bajt_198: zastapiony encja "Nieudane próby rozpalenia" (to samo pole, wlasciwa nazwa)
USUNIETE = [("sensor", "zegar_panelu"), ("sensor", "alarm_bajt_198")]

BINARNE = [
    ("alarm", "Alarm", {"device_class": "problem"}),
    ("pompa_piec", "Pompa CO", {"device_class": "running"}),
    ("pompa_cwu", "Pompa CWU", {"device_class": "running"}),
    ("pompa_mieszacz", "Pompa mieszacza", {"device_class": "running"}),
    ("zapalarka", "Zapalarka", {"device_class": "running"}),
    ("wentylator", "Wentylator", {"device_class": "running"}),
    ("podajnik", "Podajnik", {"device_class": "running"}),
    ("podajnik_2", "Podajnik 2", {"device_class": "running"}),
    ("silownik_czyszczacy", "Siłownik czyszczący", {"device_class": "running"}),
]
# (klucz w piec/diag, nazwa, dodatkowe pola)
DIAG_SENSORY = [
    ("ramki_min", "Ramki na minutę", {**DIAGN, "state_class": "measurement", "icon": "mdi:swap-horizontal"}),
    ("odrzucone_min", "Odrzucone ramki na minutę", {**DIAGN, "state_class": "measurement", "icon": "mdi:alert-outline"}),
    ("wiek_odczytu_s", "Wiek odczytu", {**DIAGN, "unit_of_measurement": "s", "device_class": "duration",
                                        "state_class": "measurement"}),
    ("zalegle_zdarzenia", "Zaległe zdarzenia MQTT", {**DIAGN, "icon": "mdi:tray-full"}),
]


class Publikator:
    def __init__(self, cfg):
        m = cfg["mqtt"]
        self.prefiks = m.get("prefiks", "piec").strip("/")
        self.disc = m.get("discovery_prefiks", "homeassistant").strip("/")
        self.uid = m.get("client_id", "piec-kpol")
        self.t_status = f"{self.prefiks}/status"          # swiezosc danych z parsera
        self.t_polaczenie = f"{self.prefiks}/polaczenie"  # LWT: publikator <-> broker
        self.polaczony = False
        self.nowe_polaczenie = False
        self.rozlaczenia = 0
        self.ostatni_stan = None
        self.ostatni_stan_t = 0.0
        self.ostatni_alarm = None
        self.ostatni_status = None
        self.ostatnia_diag_t = 0.0
        self.parametry_mtime = None
        self.alarmy_mtime = {}
        self.zalegle = 0
        self._bledy = {}          # ostatnie zgloszenie danego bledu (ograniczenie logow)

        try:   # paho 2.x
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.uid)
        except AttributeError:   # paho 1.x
            self.c = mqtt.Client(client_id=self.uid)
        if m.get("uzytkownik"):
            self.c.username_pw_set(m.get("uzytkownik"), m.get("haslo") or None)
        if m.getboolean("tls", fallback=False):
            self.c.tls_set()
        self.c.will_set(self.t_polaczenie, "offline", qos=1, retain=True)
        self.c.reconnect_delay_set(min_delay=1, max_delay=60)
        self.c.on_connect = self._on_connect
        self.c.on_disconnect = self._on_disconnect
        self.host = m.get("host")
        self.port = m.getint("port", fallback=1883)
        self.keepalive = m.getint("keepalive", fallback=30)
        # miejsca po przecinku dla temperatur w MQTT; -1 = bez zaokraglania
        self.miejsca_temp = m.getint("zaokraglenie_temp", fallback=1)
        self.poz = czytaj_json(POZYCJA) or {}

    # --- polaczenie (callbacki dzialaja w watku paho) ---
    def _on_connect(self, client, userdata, flags, rc, *args):
        kod = getattr(rc, "value", rc)
        if kod == 0:
            self.polaczony = True
            self.nowe_polaczenie = True
            log(f"Połączono z brokerem {self.host}:{self.port}")
        else:
            log(f"Broker odrzucił połączenie: {rc}")

    def _on_disconnect(self, client, userdata, *args):
        if self.polaczony:
            self.rozlaczenia += 1
            log(f"Rozłączono z brokerem ({args[-2] if len(args) >= 2 else args})")
        self.polaczony = False

    def _blad(self, gdzie, e):
        klucz = f"{gdzie}: {e!r}"
        teraz = time.monotonic()
        if teraz - self._bledy.get(klucz, -1e9) >= 600:
            self._bledy[klucz] = teraz
            log(f"Błąd ({gdzie}): {e!r}")

    def start(self):
        self.c.connect_async(self.host, self.port, keepalive=self.keepalive)
        self.c.loop_start()

    def stop(self):
        try:
            if self.polaczony:
                czekaj_na_publikacje(self.c.publish(self.t_polaczenie, "offline", qos=1, retain=True), 3)
        except Exception:
            pass
        self.c.disconnect()
        self.c.loop_stop()

    def pub(self, temat, dane, retain=False, qos=0):
        p = dane if isinstance(dane, str) else json.dumps(dane, ensure_ascii=False)
        return self.c.publish(f"{self.prefiks}/{temat}", p, qos=qos, retain=retain)

    def pub_pewnie(self, temat, dane):
        """QoS 1 i czekanie na potwierdzenie brokera; False = sprobuj pozniej."""
        if not self.polaczony:
            return False
        try:
            return czekaj_na_publikacje(self.pub(temat, dane, qos=1), 5)
        except Exception as e:     # nigdy nie blokuj reszty obiegu (stanu, diagnostyki)
            self._blad("wysyłka zdarzenia", e)
            return False

    # --- discovery ---
    def discovery(self):
        dev = {"identifiers": [self.uid], "name": "Piec Kpol",
               "manufacturer": "Plum", "model": "ecoMAX850P2-H, palnik DasPell GL 20 (odczyt RS-485)"}
        # odczyty: dostepne, gdy publikator polaczony I dane swieze;
        # diagnostyka: wystarczy polaczenie (ma pokazac, DLACZEGO dane sa stare)
        dost_polaczenie = {"topic": self.t_polaczenie}
        wspolne = {"availability": [dost_polaczenie, {"topic": self.t_status}],
                   "availability_mode": "all", "device": dev, "has_entity_name": True}
        wspolne_diag = {"availability": [dost_polaczenie], "device": dev, "has_entity_name": True}
        for klucz, nazwa, extra in SENSORY:
            self._disc("sensor", klucz, nazwa, f"{self.prefiks}/stan", "{{ value_json.%s }}" % klucz,
                       {**wspolne, **extra})
        for klucz, nazwa, extra in BINARNE:
            self._disc("binary_sensor", klucz, nazwa, f"{self.prefiks}/stan",
                       "{{ 'ON' if value_json.%s else 'OFF' }}" % klucz, {**wspolne, **extra})
        for komponent, klucz in USUNIETE:
            uid = f"{self.uid}_{klucz}".replace("-", "_")
            self.c.publish(f"{self.disc}/{komponent}/{uid}/config", "", qos=1, retain=True)
        for klucz, nazwa, extra in DIAG_SENSORY:
            self._disc("sensor", "diag_" + klucz, nazwa, f"{self.prefiks}/diag",
                       "{{ value_json.%s }}" % klucz, {**wspolne_diag, **extra})

    def _disc(self, komponent, klucz, nazwa, temat, szablon, extra):
        uid = f"{self.uid}_{klucz}".replace("-", "_")
        cfg = {"name": nazwa, "unique_id": uid, "state_topic": temat, "value_template": szablon, **extra}
        self.c.publish(f"{self.disc}/{komponent}/{uid}/config",
                       json.dumps(cfg, ensure_ascii=False), qos=1, retain=True)

    # --- jeden obieg petli glownej ---
    def obieg(self):
        teraz = time.monotonic()
        if self.nowe_polaczenie:
            self.nowe_polaczenie = False
            self.c.publish(self.t_polaczenie, "online", qos=1, retain=True)
            self.discovery()
            self.ostatni_stan = None          # wymus ponowna publikacje stanow
            self.ostatni_alarm = None
            self.ostatni_status = None
            self.parametry_mtime = None

        d = czytaj_json(ODCZYTY)
        if d is None and os.path.exists(ODCZYTY):
            return          # plik chwilowo nieczytelny - sprobuj w nastepnym obiegu
        stan = (zaokraglij_temperatury(plaski_stan(d), self.miejsca_temp)
                if d and "odczyty" in d else None)
        wiek = wiek_s(stan["odczyt"]) if stan else None
        status = "online" if (wiek is not None and wiek <= DANE_NIEAKTUALNE_S) else "offline"

        if not self.polaczony:
            return
        if status != self.ostatni_status:
            self.pub("status", status, retain=True, qos=1)
            if self.ostatni_status is not None:
                log(f"Status danych: {status} (wiek odczytu: {wiek} s)")
            self.ostatni_status = status

        if stan is not None:
            # pola zmieniajace sie co sekunde nie wymuszaja publikacji (i tak co STAN_CO_S)
            bez_czasu = {k: v for k, v in stan.items() if k not in ("odczyt", "zegar_panelu")}
            if bez_czasu != self.ostatni_stan or teraz - self.ostatni_stan_t >= STAN_CO_S:
                self.pub("stan", stan, retain=True)
                self.ostatni_stan, self.ostatni_stan_t = bez_czasu, teraz
            alarm = {k: stan[k] for k in ("alarm", "alarm_kod", "alarm_opis")}
            if alarm != self.ostatni_alarm:
                self.pub("alarm", alarm, retain=True, qos=1)
                self.ostatni_alarm = alarm

        mt = mtime(PARAMETRY)
        if mt is not None and mt != self.parametry_mtime:
            p = czytaj_json(PARAMETRY)
            if p:
                self.pub("parametry", {
                    "timestamp": p.get("timestamp"),
                    "parametry": {str(x["nr"]): {k: x[k] for k in ("nazwa", "wartosc", "min", "max")}
                                  for x in p.get("parametry", [])}}, retain=True, qos=1)
            self.parametry_mtime = mt

        # Zdarzenia w osobnym try: blad tutaj nie moze zatrzymac diagnostyki
        # (tak bylo 06.11.2026 na paho 1.5 - diagnostyka stala 2 dni).
        try:
            self.zalegle = self.wyslij_polecenia() + self.wyslij_alarmy()
        except Exception as e:
            self._blad("zdarzenia", e)

        if teraz - self.ostatnia_diag_t >= DIAG_CO_S:
            self.ostatnia_diag_t = teraz
            dg = czytaj_json(DIAG) or {}
            om = dg.get("ostatnia_minuta") or {}
            okres = om.get("okres_s") or 0
            na_min = (lambda n: round(n * 60 / okres, 1) if okres >= 10 and n is not None else None)
            self.pub("diag", {
                "ramki_min": na_min(om.get("poprawne")),
                "odrzucone_min": na_min(om.get("odrzucone")),
                "razem": dg.get("razem"),
                "start_parsera": dg.get("start_uslugi"),
                "wiek_odczytu_s": wiek,
                "zalegle_zdarzenia": self.zalegle,
                "rozlaczenia_mqtt": self.rozlaczenia,
                "timestamp": teraz_iso(),
            }, retain=True)

    # --- zdarzenia: polecenia z panelu (doczytywanie po przerwie) ---
    def wyslij_polecenia(self):
        try:
            st = os.stat(POLECENIA)
        except OSError:
            return 0
        poz = self.poz.get("polecenia")
        if poz is None or poz.get("inode") != st.st_ino or poz.get("offset", 0) > st.st_size:
            # pierwszy start albo nowy plik: nie wysylamy calej historii, tylko to, co przyjdzie
            nowy = poz is not None and poz.get("inode") != st.st_ino
            poz = {"inode": st.st_ino, "offset": 0 if nowy else st.st_size}
            self.poz["polecenia"] = poz
            self._zapisz_poz()
        if poz["offset"] >= st.st_size:
            return 0
        wyslane = 0
        with open(POLECENIA, "rb") as f:
            f.seek(poz["offset"])
            while wyslane < ZDARZEN_NA_PETLE:
                linia = f.readline()
                if not linia.endswith(b"\n"):
                    break                       # niedokonczona linia - poczekaj
                try:
                    rek = json.loads(linia)
                except ValueError:
                    rek = None
                if rek is not None:
                    rek.pop("ramka", None)      # pelna ramka wystarczy
                    if not self.pub_pewnie("zdarzenia/polecenie", rek):
                        break
                poz["offset"] += len(linia)
                wyslane += 1
        if wyslane:
            self._zapisz_poz()
        return self._ile_zostalo(st.st_size, poz["offset"])

    def _ile_zostalo(self, rozmiar, offset):
        if offset >= rozmiar:
            return 0
        try:
            with open(POLECENIA, "rb") as f:
                f.seek(offset)
                return f.read().count(b"\n")
        except OSError:
            return 0

    # --- zdarzenia: start / koniec alarmu ---
    def wyslij_alarmy(self):
        try:
            pliki = sorted(x for x in os.listdir(ALARMY) if x.startswith("alarm_") and x.endswith(".json"))
        except OSError:
            return 0
        znane = self.poz.get("alarmy")
        pierwszy_raz = znane is None
        if pierwszy_raz:
            znane = {}
            self.poz["alarmy"] = znane
        zalegle = 0
        zmiana = False
        for plik in pliki:
            sciezka = os.path.join(ALARMY, plik)
            mt = mtime(sciezka)
            if self.alarmy_mtime.get(plik) == mt:
                continue                        # bez zmian od ostatniego udanego obiegu
            ep = czytaj_json(sciezka)
            if not ep:
                continue
            wyslano = znane.get(plik)
            if pierwszy_raz:
                # historia sprzed pierwszego uruchomienia - oznacz jako wyslana
                # (tylko trwajacy alarm zglosimy jako "start")
                if ep.get("koniec") is not None:
                    znane[plik] = "koniec"
                    zmiana = True
                    self.alarmy_mtime[plik] = mt
                    continue
            do_wyslania = []
            if wyslano is None:
                do_wyslania.append("start")
            if ep.get("koniec") is not None and wyslano != "koniec":
                do_wyslania.append("koniec")
            ok = True
            for zdarzenie in do_wyslania:
                tresc = {
                    "zdarzenie": zdarzenie, "plik": plik,
                    "poczatek": ep.get("poczatek"), "koniec": ep.get("koniec"),
                    "kod": ep.get("kod"), "opis": ep.get("opis"),
                    "sposob_zakonczenia": ep.get("sposob_zakonczenia"),
                    "stan_po_alarmie": ep.get("stan_po_alarmie"),
                    "licznik_ramek": ep.get("licznik_ramek"),
                    "polecenia": [p.get("opis") for p in ep.get("polecenia", [])],
                }
                if not self.pub_pewnie("zdarzenia/alarm", tresc):
                    zalegle += 1
                    ok = False
                    break
                znane[plik] = zdarzenie
                zmiana = True
            if ok:
                self.alarmy_mtime[plik] = mt
        # nie trzymaj w pozycji plikow, ktore parser juz skasowal
        for plik in list(znane):
            if plik not in pliki:
                del znane[plik]
                zmiana = True
        if zmiana:
            self._zapisz_poz()
        return zalegle

    def _zapisz_poz(self):
        try:
            zapisz_json(POZYCJA, self.poz)
        except OSError as e:
            log(f"Błąd zapisu {POZYCJA}: {e}")


def wczytaj_konfig(sciezka):
    cfg = configparser.ConfigParser()
    cfg.BOOLEAN_STATES = {**cfg.BOOLEAN_STATES, "tak": True, "nie": False}
    if not cfg.read(sciezka, encoding="utf-8") or "mqtt" not in cfg:
        log(f"Brak konfiguracji {sciezka} (sekcja [mqtt]). Kończę.")
        sys.exit(2)
    if not cfg["mqtt"].getboolean("wlaczone", fallback=False):
        log(f"MQTT wyłączone (wlaczone = nie w {sciezka}). Kończę.")
        sys.exit(0)
    if not cfg["mqtt"].get("host"):
        log("Brak 'host' w konfiguracji. Kończę.")
        sys.exit(2)
    try:
        if os.stat(sciezka).st_mode & 0o077:
            log(f"UWAGA: {sciezka} jest czytelny dla innych - ustaw: sudo chmod 600 {sciezka}")
    except OSError:
        pass
    return cfg


def main():
    cfg = wczytaj_konfig(KONFIG)
    p = Publikator(cfg)
    dzialaj = [True]

    def koniec(*_):
        dzialaj[0] = False
    signal.signal(signal.SIGTERM, koniec)
    signal.signal(signal.SIGINT, koniec)

    log(f"Start publikatora MQTT -> {p.host}:{p.port}, prefiks '{p.prefiks}'")
    p.start()
    while dzialaj[0]:
        try:
            p.obieg()
        except Exception as e:      # pojedynczy blad nie zatrzymuje uslugi
            log(f"Błąd w obiegu: {e!r}")
        time.sleep(1)
    log("Zatrzymywanie...")
    p.stop()


if __name__ == "__main__":
    main()
