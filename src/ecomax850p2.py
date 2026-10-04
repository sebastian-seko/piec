#ecoMAX 850 P2
import atexit
import struct
import json
import os
import time
from collections import deque
from datetime import datetime

print("Zaimportowano bibliotekę sterownika EcoMax850P2")
filename = "/data/odczyty.txt"

# --- Zrzut ramek przy alarmie -------------------------------------------------
# Gdy stan (bajt 27) = 7 (ALARM), zapisujemy ramke z alarmem oraz ostatnia ramke
# sprzed alarmu - z roznicy widac, gdzie siedza licznik i kody alarmow.
# Kazdy alarm to osobny plik na karcie SD (nie w /data = tmpfs), wiec historia
# przetrwa restart, a zapis nie przepisuje calej historii za kazdym razem.
# Zapis na SD: przy starcie i koncu alarmu oraz max co ALARM_ZAPIS_CO s w trakcie.
ALARM_KATALOG = "/home/pi/piec_dane/alarmy"
ALARM_STAN = 7
ALARM_MAX_PLIKOW = 5000     # ~kilkanascie KB na alarm -> max rzedu 100 MB
ALARM_MAX_ROZNIC = 300
ALARM_ZAPIS_CO = 60         # sekund miedzy zapisami w trakcie trwania alarmu

# Inne ramki (dowolny typ/nadawca, nieobslugiwane przez parsery) wokol alarmu:
ALARM_PRZED_S = 120         # ile sekund przed alarmem dolaczyc z bufora
ALARM_PO_S = 120            # ile sekund po koncu alarmu jeszcze zbierac
ALARM_BUFOR = 200           # ile ostatnich innych ramek trzymac w pamieci
ALARM_MAX_INNYCH = 500      # max roznych (unikalna tresc) innych ramek w pliku

# --- Kody alarmow (bajt 196 ramki 0x08) ---------------------------------------
# "potwierdzony": False = opis to wniosek z danych, nie tekst odczytany z panelu.
# Po potwierdzeniu z panelu zmien na True. Nowe kody dopisuj tutaj.
ALARM_KOD_BAJT = 196
ALARM_KODY = {
    32: {"opis": "Nieudane rozpalenie", "potwierdzony": False},
}


def opis_alarmu(kod):
    if kod is None or kod == 0:
        return None
    k = ALARM_KODY.get(kod)
    if k is None:
        return f"Nieznany alarm (kod {kod})"
    return k["opis"] if k["potwierdzony"] else f"{k['opis']} (niepotwierdzone)"


# --- Polecenia i odpowiedzi (wszystko poza cyklicznym odpytywaniem) -----------
# Piec (0x45) co ~0,85 s odpytuje adresy 0x50/0x51/0x55/0x56 (+0x57/0x58 co 4. cykl)
# jednobajtowymi ramkami (typ < 0x80). Wszystko INNE jest ciekawe i trafia do
# polecenia.jsonl: ramki od innych nadawcow do pieca oraz odpowiedzi pieca
# (typ = typ polecenia + 0x80). Zaobserwowane pary:
#   0x70 -> 0xF0  zmiana parametru, np. [1, 49, 65] = parametr 49 (zadana CO) na 65
#   0x61 -> 0xE1  odczyt tabeli parametrow: [255, 0] -> [ile, od_nr, (wart, min, max) * ile]
#   0x71 -> 0xF1  polecenie, np. [3, 32, 0] = kasowanie alarmu 32; [2] = nieznane
ADRES_PIECA = 0x45
POLECENIA_PLIK = "/home/pi/piec_dane/polecenia.jsonl"   # karta SD, przetrwa restart
POLECENIE_STAN_PO_S = 10    # po ilu sekundach zapisac stan pieca "po" poleceniu
KASOWANIE_OKNO_S = 30       # kasowanie max tyle s przed koncem alarmu => "skasowany"

# --- Tabela parametrow (ramka 0xE1) ----------------------------------------------
PARAMETRY_KATALOG = "/home/pi/piec_dane"
PARAMETRY_PLIK = PARAMETRY_KATALOG + "/parametry.json"            # ostatnia tabela
PARAMETRY_ZMIANY = PARAMETRY_KATALOG + "/parametry_zmiany.jsonl"  # co sie zmienilo
PARAMETRY_MIGAWKI = PARAMETRY_KATALOG + "/parametry"              # kazda odebrana tabela
PARAMETRY_MAX_MIGAWEK = 1000

# Nazwy parametrow. "zrodlo" mowi, skad wiemy - dopisuj kolejne, gdy zmienisz cos
# w menu panelu i zobaczysz, ktory numer zmienil sie w parametry_zmiany.jsonl.
PARAMETRY_NAZWY = {
    49: {"nazwa": "Temperatura zadana CO", "zrodlo": "zgodna z bajtem 154 ramki 0x08 (65)"},
    52: {"nazwa": "Temperatura zadana CWU", "zrodlo": "zgodna z bajtem 153 ramki 0x08 (45)"},
}


def nazwa_parametru(nr):
    p = PARAMETRY_NAZWY.get(nr)
    return p["nazwa"] if p else None


def czy_polecenie(nadawca, typ):
    """Ramka spoza cyklicznego odpytywania: od kogos innego niz piec albo odpowiedz pieca."""
    return nadawca != ADRES_PIECA or typ >= 0x80


_ostatni_stan = None        # bajt 27 z ostatniej ramki 0x08
_ostatni_kod = None         # bajt 196 z ostatniej ramki 0x08
_oczekujace = []            # polecenia czekajace na "stan_po": (monotonic, rekord, epizod)
_ostatnie_kasowanie = None  # (monotonic, rekord) ostatniego polecenia kasowania
_start_mono = 0.0           # monotonic() poczatku biezacego epizodu
_parametry = None           # ostatnia tabela parametrow {nr: (wart, min, max)}


def _opis_param(nr):
    n = nazwa_parametru(nr)
    return f"parametr {nr} ({n})" if n else f"parametr {nr}"


def dekoduj_polecenie(typ, message):
    """Zwraca (opis, rodzaj). message[0] to typ ramki."""
    dane = list(message[1:])
    if typ == 0x71:
        if len(dane) >= 2 and dane[0] == 3:
            return f"kasowanie alarmu {dane[1]} ({opis_alarmu(dane[1])})", "kasowanie_alarmu"
        if dane[:1] == [2]:
            return "polecenie 0x71 [2] - nieznane (panel wysyła je po kasowaniu alarmu)", "nieznane"
        return f"polecenie 0x71 {dane} - nieznane", "nieznane"
    if typ == 0xF1:
        return f"odpowiedź pieca na polecenie 0x71 {dane}", "odpowiedz"
    if typ == 0x70:
        # [ile, nr, wartosc, nr, wartosc, ...] - przy 1 parametrze: [1, 49, 65]
        if dane and len(dane) == 1 + 2 * dane[0]:
            zmiany = []
            for i in range(dane[0]):
                nr, w = dane[1 + 2 * i], dane[2 + 2 * i]
                stara = _parametry.get(nr) if _parametry else None
                z = f"{_opis_param(nr)} -> {w}"
                if stara is not None:
                    z += f" (było {stara[0]}, zakres {stara[1]}-{stara[2]})"
                zmiany.append(z)
            return "zmiana: " + "; ".join(zmiany), "zmiana_parametru"
        return f"zmiana parametru 0x70 {dane} - nieznany układ", "zmiana_parametru"
    if typ == 0xF0:
        return f"odpowiedź pieca na zmianę parametru {dane}", "odpowiedz"
    if typ == 0x61:
        return f"odczyt tabeli parametrów {dane}", "odczyt_parametrow"
    if typ == 0xE1:
        if len(dane) >= 2 and len(dane) == 2 + 3 * dane[0]:
            return f"tabela parametrów: {dane[0]} pozycji od nr {dane[1]}", "tabela_parametrow"
        return f"tabela parametrów 0xE1 - nieznany układ ({len(dane)} B)", "tabela_parametrow"
    if typ >= 0x80:
        return f"odpowiedź pieca typ 0x{typ:02X} (na 0x{typ - 0x80:02X}) {dane[:20]}", "odpowiedz"
    return f"typ 0x{typ:02X} {dane[:20]}", "nieznane"


def _zapisz_json(sciezka, dane):
    tmp = sciezka + ".tmp"
    os.makedirs(os.path.dirname(sciezka), exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)
    os.replace(tmp, sciezka)


def _wczytaj_parametry():
    """Przy starcie: ostatnia znana tabela, zeby porownywac z nastepna."""
    global _parametry
    try:
        with open(PARAMETRY_PLIK, encoding='utf-8') as f:
            d = json.load(f)
        _parametry = {p["nr"]: (p["wartosc"], p["min"], p["max"]) for p in d["parametry"]}
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"Nie można wczytać {PARAMETRY_PLIK}: {e}")


def _zapisz_parametry(wpis, message):
    """Ramka 0xE1: zapis tabeli, migawki i listy zmian wzgledem poprzedniej."""
    global _parametry
    dane = list(message[1:])
    if len(dane) < 2 or len(dane) != 2 + 3 * dane[0]:
        print(f"Tabela parametrów o nieznanym układzie ({len(dane)} B) - pomijam dekodowanie")
        return
    ile, od = dane[0], dane[1]
    nowe = {od + i: tuple(dane[2 + 3 * i: 5 + 3 * i]) for i in range(ile)}
    ts = wpis["timestamp"]
    tabela = {
        "timestamp": ts,
        "liczba": ile,
        "od_nr": od,
        "parametry": [
            {"nr": nr, "nazwa": nazwa_parametru(nr), "wartosc": w, "min": mn, "max": mx,
             "poza_zakresem": not (mn <= w <= mx)}
            for nr, (w, mn, mx) in sorted(nowe.items())
        ],
        "ramka_pelna": wpis.get("ramka_pelna"),
    }
    try:
        _zapisz_json(PARAMETRY_PLIK, tabela)
        baza = "parametry_" + ts.replace(":", "-").replace("T", "_")
        nazwa, n = baza + ".json", 1
        while os.path.exists(os.path.join(PARAMETRY_MIGAWKI, nazwa)):
            n += 1
            nazwa = f"{baza}_{n}.json"
        _zapisz_json(os.path.join(PARAMETRY_MIGAWKI, nazwa), tabela)
        migawki = sorted(os.listdir(PARAMETRY_MIGAWKI))
        for f in migawki[:-PARAMETRY_MAX_MIGAWEK]:
            os.remove(os.path.join(PARAMETRY_MIGAWKI, f))
    except (OSError, TypeError, ValueError) as e:
        print(f"Błąd zapisu tabeli parametrów: {e}")

    if _parametry is not None:
        zmiany = []
        for nr in sorted(set(nowe) | set(_parametry)):
            a, b = _parametry.get(nr), nowe.get(nr)
            if a != b:
                zmiany.append({
                    "timestamp": ts, "nr": nr, "nazwa": nazwa_parametru(nr),
                    "bylo": None if a is None else {"wartosc": a[0], "min": a[1], "max": a[2]},
                    "jest": None if b is None else {"wartosc": b[0], "min": b[1], "max": b[2]},
                })
        if zmiany:
            try:
                os.makedirs(PARAMETRY_KATALOG, exist_ok=True)
                with open(PARAMETRY_ZMIANY, 'a', encoding='utf-8') as f:
                    for z in zmiany:
                        f.write(json.dumps(z, ensure_ascii=False) + "\n")
            except OSError as e:
                print(f"Błąd zapisu {PARAMETRY_ZMIANY}: {e}")
            print(f"PARAMETRY: zmieniło się {len(zmiany)}: " +
                  ", ".join(f"{z['nr']}: {z['bylo'] and z['bylo']['wartosc']} -> {z['jest'] and z['jest']['wartosc']}"
                            for z in zmiany[:10]))
    _parametry = nowe


def _nazwa_stanu(st):
    return {0: 'WYŁĄCZONY', 1: 'ROZPALANIE', 2: 'PRACA', 4: 'WYGASZANIE', 5: 'POSTÓJ',
            6: 'PRACA RĘCZNA', 7: 'ALARM', 8: 'CZYSZCZENIE'}.get(st, None if st is None else str(st))


def _dopisz_polecenie(rekord):
    try:
        os.makedirs(os.path.dirname(POLECENIA_PLIK), exist_ok=True)
        with open(POLECENIA_PLIK, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rekord, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as e:
        print(f"Błąd zapisu pliku {POLECENIA_PLIK}: {e}")


def _obsluz_oczekujace(wymus=False):
    """Uzupelnia stan_po polecen sprzed >= POLECENIE_STAN_PO_S s i zapisuje je."""
    global _brudny
    teraz = time.monotonic()
    zostaja = []
    for t, rek, ep in _oczekujace:
        if wymus or teraz - t >= POLECENIE_STAN_PO_S:
            rek["stan_po"] = _nazwa_stanu(_ostatni_stan)
            rek["alarm_kod_po"] = _ostatni_kod
            _dopisz_polecenie(rek)
            if ep is not None:
                if ep is _epizod:
                    _brudny = True
                else:
                    _zapisz_epizod(ep)       # epizod juz zamkniety - zapisz od razu
        else:
            zostaja.append((t, rek, ep))
    _oczekujace[:] = zostaja


def _zglos_polecenie(wpis, typ, message):
    global _ostatnie_kasowanie, _brudny
    opis, rodzaj = dekoduj_polecenie(typ, message)
    rek = {
        "timestamp": wpis["timestamp"],
        "nadawca": wpis["nadawca"],
        "odbiorca": wpis["odbiorca"],
        "typ": wpis["typ"],
        "rodzaj": rodzaj,
        "opis": opis,
        "stan_przed": _nazwa_stanu(_ostatni_stan),
        "alarm_kod_przed": _ostatni_kod,
        "stan_po": None,
        "alarm_kod_po": None,
        "ramka": wpis["ramka"],
        "ramka_pelna": wpis.get("ramka_pelna"),
    }
    print(f"POLECENIE: {opis} (od {wpis['nadawca']})")
    teraz = time.monotonic()
    if rodzaj == "kasowanie_alarmu":
        _ostatnie_kasowanie = (teraz, rek)
    ep = None
    if _epizod is not None and (_w_alarmie or (_koniec_mono is not None and teraz - _koniec_mono <= ALARM_PO_S)):
        ep = _epizod
        ep.setdefault("polecenia", []).append(rek)
        _brudny = True
    _oczekujace.append((teraz, rek, ep))


_ostatnia_normalna = None   # (timestamp, ramka) ostatniej ramki bez alarmu
_epizod = None              # biezacy / ostatni epizod alarmu (dict)
_w_alarmie = False
_ostatni_zapis = 0.0
_koniec_mono = None         # monotonic() konca alarmu (okno "po")
_brudny = False             # epizod zmieniony od ostatniego zapisu
_bufor = deque(maxlen=ALARM_BUFOR)   # (monotonic, dict ramki)


def _bajt(message, i):
    return message[i] if 0 <= i < len(message) else None


def _roznice(przed, teraz):
    out = []
    for i in range(min(len(przed), len(teraz))):
        if przed[i] != teraz[i]:
            out.append({"bajt": i, "przed": przed[i], "alarm": teraz[i]})
            if len(out) >= ALARM_MAX_ROZNIC:
                break
    return out


def _pliki_alarmow():
    try:
        return sorted(f for f in os.listdir(ALARM_KATALOG)
                      if f.startswith("alarm_") and f.endswith(".json"))
    except FileNotFoundError:
        return []


def _zapisz_epizod(ep):
    global _ostatni_zapis, _brudny
    _ostatni_zapis = time.monotonic()
    _brudny = False
    sciezka = os.path.join(ALARM_KATALOG, ep["plik"])
    tmp = sciezka + ".tmp"
    try:
        os.makedirs(ALARM_KATALOG, exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(ep, f, ensure_ascii=False, indent=2)
        os.replace(tmp, sciezka)
    except (OSError, TypeError, ValueError) as e:
        print(f"Błąd zapisu pliku {sciezka}: {e}")


def _sprzataj_stare():
    pliki = _pliki_alarmow()
    for f in pliki[:-ALARM_MAX_PLIKOW]:
        try:
            os.remove(os.path.join(ALARM_KATALOG, f))
        except OSError:
            pass


def _nazwa_pliku(ts):
    baza = "alarm_" + ts.replace(":", "-").replace("T", "_")
    nazwa, n = baza + ".json", 1
    while os.path.exists(os.path.join(ALARM_KATALOG, nazwa)):
        n += 1
        nazwa = f"{baza}_{n}.json"
    return nazwa


def _wczytaj_alarmy():
    """Przy starcie uslugi zamyka alarm, ktory trwal w chwili restartu."""
    pliki = _pliki_alarmow()
    if not pliki:
        return
    sciezka = os.path.join(ALARM_KATALOG, pliki[-1])
    try:
        with open(sciezka, encoding='utf-8') as f:
            ep = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Nie można wczytać {sciezka}: {e}")
        return
    if isinstance(ep, dict) and ep.get("koniec") is None:
        ep["koniec"] = "przerwany (restart usługi)"
        ep["sposob_zakonczenia"] = "nieznany - usługa zrestartowana w trakcie alarmu"
        ep["plik"] = pliki[-1]
        _zapisz_epizod(ep)


def _dodaj_inna(ep, wpis, faza):
    """Dopisuje inna ramke do epizodu; powtorki tej samej tresci tylko zlicza."""
    global _brudny
    lista = ep.setdefault("inne_ramki", [])
    for r in lista:
        if (r["nadawca"], r["odbiorca"], r["typ"], r["ramka"]) == \
           (wpis["nadawca"], wpis["odbiorca"], wpis["typ"], wpis["ramka"]):
            r["licznik"] += 1
            r["ostatnio"] = wpis["timestamp"]
            if faza not in r["fazy"]:
                r["fazy"].append(faza)
            _brudny = True
            return
    if len(lista) >= ALARM_MAX_INNYCH:
        ep["inne_ramki_pominiete"] = ep.get("inne_ramki_pominiete", 0) + 1
        _brudny = True
        return
    lista.append({
        "pierwszy_raz": wpis["timestamp"],
        "ostatnio": wpis["timestamp"],
        "licznik": 1,
        "fazy": [faza],
        "nadawca": wpis["nadawca"],
        "odbiorca": wpis["odbiorca"],
        "typ": wpis["typ"],
        "dlugosc": len(wpis["ramka"]),
        "ramka": wpis["ramka"],
        "ramka_pelna": wpis.get("ramka_pelna"),
    })
    _brudny = True


def _zapisz_jesli_trzeba():
    if _epizod is None or not _brudny:
        return
    teraz = time.monotonic()
    okno_po_minelo = (not _w_alarmie and _koniec_mono is not None
                      and teraz - _koniec_mono > ALARM_PO_S)
    if okno_po_minelo or teraz - _ostatni_zapis >= ALARM_ZAPIS_CO:
        _zapisz_epizod(_epizod)


def zglos_inna_ramke(nadawca, odbiorca, typ, message, ramka_pelna=None):
    """Wolane z start.py dla kazdej ramki, ktorej nie obsluguje zaden parser.
    ramka_pelna = cala ramka z naglowkiem, CRC i bajtem stopu (jesli dostepna)."""
    teraz = time.monotonic()
    wpis = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "nadawca": f"0x{nadawca:02X}",
        "odbiorca": f"0x{odbiorca:02X}",
        "typ": f"0x{typ:02X}",
        "ramka": list(message),
    }
    if ramka_pelna is not None:
        wpis["ramka_pelna"] = list(ramka_pelna)
    _bufor.append((teraz, wpis))
    if czy_polecenie(nadawca, typ):
        _zglos_polecenie(wpis, typ, message)
        if typ == 0xE1:
            _zapisz_parametry(wpis, message)
    if _epizod is not None:
        if _w_alarmie:
            _dodaj_inna(_epizod, wpis, "w_trakcie")
        elif _koniec_mono is not None and teraz - _koniec_mono <= ALARM_PO_S:
            _dodaj_inna(_epizod, wpis, "po")
    _zapisz_jesli_trzeba()


def sledz_alarm(message):
    global _ostatnia_normalna, _w_alarmie, _epizod, _koniec_mono, _brudny
    global _ostatni_stan, _ostatni_kod, _ostatnie_kasowanie, _start_mono
    if len(message) <= 27:
        return
    teraz = datetime.now().isoformat(timespec="seconds")
    ramka = list(message)
    _ostatni_stan = message[27]
    _ostatni_kod = _bajt(message, ALARM_KOD_BAJT)
    _obsluz_oczekujace()

    if message[27] != ALARM_STAN:
        if _w_alarmie and _epizod is not None:
            _epizod["koniec"] = teraz
            _koniec_mono = time.monotonic()
            kas = _ostatnie_kasowanie
            if (kas is not None and kas[0] >= _start_mono
                    and _koniec_mono - kas[0] <= KASOWANIE_OKNO_S):
                _epizod["sposob_zakonczenia"] = (
                    f"skasowany poleceniem od {kas[1]['nadawca']} o {kas[1]['timestamp']}")
            else:
                _epizod["sposob_zakonczenia"] = "samoistnie (brak polecenia kasowania)"
            _ostatnie_kasowanie = None
            _epizod["stan_po_alarmie"] = _nazwa_stanu(message[27])
            _zapisz_epizod(_epizod)
        _w_alarmie = False
        _ostatnia_normalna = (teraz, ramka)
        _zapisz_jesli_trzeba()
        return

    if not _w_alarmie:
        # poczatek nowego epizodu alarmu
        if _epizod is not None and _brudny:
            _zapisz_epizod(_epizod)          # domknij poprzedni (np. polecenia z okna "po")
        _w_alarmie = True
        _start_mono = time.monotonic()
        przed_ts, przed = _ostatnia_normalna if _ostatnia_normalna else (None, None)
        os.makedirs(ALARM_KATALOG, exist_ok=True)
        _epizod = {
            "plik": _nazwa_pliku(teraz),
            "poczatek": teraz,
            "koniec": None,
            "sposob_zakonczenia": None,
            "kod": _bajt(message, ALARM_KOD_BAJT),
            "opis": opis_alarmu(_bajt(message, ALARM_KOD_BAJT)),
            "licznik_ramek": 1,
            "roznica_dlugosci": (len(ramka) - len(przed)) if przed else None,
            "roznice": _roznice(przed, ramka) if przed else [],
            "ramka_przed": {"timestamp": przed_ts, "dlugosc": len(przed) if przed else None, "ramka": przed},
            "ramka_alarm_pierwsza": {"timestamp": teraz, "dlugosc": len(ramka), "ramka": ramka},
            "ramka_alarm_ostatnia": {"timestamp": teraz, "dlugosc": len(ramka), "ramka": ramka},
            "inne_ramki": [],
            "polecenia": [],
        }
        _koniec_mono = None
        # inne ramki z ostatnich ALARM_PRZED_S sekund przed alarmem
        granica = time.monotonic() - ALARM_PRZED_S
        for t, wpis in _bufor:
            if t >= granica:
                _dodaj_inna(_epizod, wpis, "przed")
        _zapisz_epizod(_epizod)
        _sprzataj_stare()
        print(f"ALARM - zapisano {os.path.join(ALARM_KATALOG, _epizod['plik'])}")
        return

    # alarm trwa - aktualizacja w pamieci, zapis na SD co ALARM_ZAPIS_CO s
    _epizod["licznik_ramek"] += 1
    _epizod["ramka_alarm_ostatnia"] = {"timestamp": teraz, "dlugosc": len(ramka), "ramka": ramka}
    _brudny = True
    _zapisz_jesli_trzeba()

def zamknij():
    """Przy zatrzymaniu uslugi: zapisz oczekujace polecenia i niezapisany epizod."""
    try:
        _obsluz_oczekujace(wymus=True)
        if _epizod is not None and _brudny:
            _zapisz_epizod(_epizod)
    except Exception as e:
        print(f"Błąd przy zamykaniu: {e}")


_wczytaj_alarmy()
_wczytaj_parametry()
atexit.register(zamknij)


def parseFrame(message):
    if message[0] == 0x08:
        parseFrame08(message)
    else:
        print(f"Parser EcoMax: Nieznany typ ramki 0x{message[0]:02X}")

def parseFrame08(message):
    OPERATING_STATUS_byte = 27
    TEMP_CWU_float = 76
    TEMP_TORCH_float = 84
    TEMP_CO_float = 80
    TEMP_WEATHER_float = 92
    TEMP_MIXER_float = 88
    TEMP_MIXER_SET_byte = 156
    MIXER_SET_percent_byte = 222
    FUEL_STREAM_float = 250
    TEMP_CWU_SET_byte = 153
    TEMP_CO_SET_byte = 154
    FLAME_float = 72
    BOILER_POWER_float = 246
    POWER100_TIME_short = 255
    POWER50_TIME_short = 257
    POWER30_TIME_short = 259
    FEEDER_TIME_short = 261
    IGNITIONS_short = 263
    AIRFLOW_percent_byte = 245
    OUTPUTS_byte = 28   # bitowa mapa stanow wyjsc (bit7..bit0)
    OUTPUTS2_byte = 29       # prawdopodobnie drugi bajt wyjsc (niepotwierdzone)
    ALARM_KOD_byte = 196     # kandydat na kod/flage alarmu (niepotwierdzone)
    ALARM_FLAGA_byte = 198   # zmienia sie przy alarmie (niepotwierdzone)
    MIXER_SET_STATUS_byte = 227
    MIXER_STATUSES = {0: "STOP", 1: "ZAMYKANIE", 2: "OTWIERANIE"}

    OPERATION_STATUSES = {0:'WYŁĄCZONY', 1:'ROZPALANIE', 2:'PRACA', 4:'WYGASZANIE', 5:'POSTÓJ', 6:'PRACA RĘCZNA', 7:'ALARM', 8:'CZYSZCZENIE'}
    print("")

    try:
        sledz_alarm(message)
    except Exception as e:
        print(f"Błąd śledzenia alarmu: {e}")

    try:
        OP = OPERATION_STATUSES[message[OPERATING_STATUS_byte]] if message[OPERATING_STATUS_byte] in OPERATION_STATUSES else str(message[OPERATING_STATUS_byte])
        tempCWU = struct.unpack("f", bytes(message[TEMP_CWU_float:TEMP_CWU_float+4]))[0]
        print(f"Temperatura CWU: {tempCWU:.1f}")
        tempCO = struct.unpack("f", bytes(message[TEMP_CO_float:TEMP_CO_float+4]))[0]
        print(f"Temperatura CO: {tempCO:.1f}")
        TEMP_CO_SET_byte_val = message[TEMP_CO_SET_byte]
        print(f"Temperatura SET CO: {TEMP_CO_SET_byte_val}")
        TEMP_CWU_SET_byte_val = message[TEMP_CWU_SET_byte]
        print(f"Temperatura SET CWU: {TEMP_CWU_SET_byte_val}")
        tempPogodowa = struct.unpack("f", bytes(message[TEMP_WEATHER_float:TEMP_WEATHER_float+4]))[0]
        print(f"Temperatura pogodowa: {tempPogodowa:.1f}")
        fuelStream = struct.unpack("f", bytes(message[FUEL_STREAM_float:FUEL_STREAM_float+4]))[0]
        print(f"Strumien paliwa: {fuelStream:.1f}")
        tempPodajnika = struct.unpack("f", bytes(message[TEMP_TORCH_float:TEMP_TORCH_float+4]))[0]
        print(f"Temperatura palnika: {tempPodajnika:.1f}")
        tempMieszacza = struct.unpack("f", bytes(message[TEMP_MIXER_float:TEMP_MIXER_float+4]))[0]
        print(f"Temperatura mieszacza: {tempMieszacza:.1f}")
        TEMP_MIXER_SET_byte_val = message[TEMP_MIXER_SET_byte]
        print(f"Temperatura ust mieszacza: {TEMP_MIXER_SET_byte_val}")
        AIRFLOW_percent_byte_val = message[AIRFLOW_percent_byte]
        print(f"Nadmuch: {AIRFLOW_percent_byte_val} %")
        MIXER_SET_percent_byte_val = message[MIXER_SET_percent_byte]
        print(f"Ustawienie mieszacza procent: {MIXER_SET_percent_byte_val} %")
        status_mixer_set = MIXER_STATUSES.get(message[MIXER_SET_STATUS_byte], str(message[MIXER_SET_STATUS_byte]))
        print(f"Status mieszacza: {status_mixer_set}")
        BOILER_POWER_float_val = struct.unpack("f", bytes(message[BOILER_POWER_float:BOILER_POWER_float+4]))[0]
        print(f"Moc kotła: {BOILER_POWER_float_val:.1f}")
        flame = struct.unpack("f", bytes(message[FLAME_float:FLAME_float+4]))[0]
        print(f"flame: {flame:.1f}%")
        # Stany wyjsc - jeden bajt, bity 7..0
        outputs = message[OUTPUTS_byte]
        fan               = "ON" if (outputs >> 0) & 1 else "OFF"
        feeder            = "ON" if (outputs >> 1) & 1 else "OFF"
        feeder2           = "ON" if (outputs >> 2) & 1 else "OFF"
        cleaning_actuator = "ON" if (outputs >> 3) & 1 else "OFF"
        ignition          = "ON" if (outputs >> 4) & 1 else "OFF"
        boiler_pump       = "ON" if (outputs >> 5) & 1 else "OFF"
        cwu_pump          = "ON" if (outputs >> 6) & 1 else "OFF"
        mixer_pump        = "ON" if (outputs >> 7) & 1 else "OFF"
        print(f"Wyjścia [{outputs:08b}]: went={fan} podajnik={feeder} podajnik2={feeder2} "
              f"czyszczak={cleaning_actuator} zapalarka={ignition} "
              f"p.piec={boiler_pump} p.cwu={cwu_pump} p.miesz={mixer_pump}")
        print("ustawienia serwisowe")
        # Blok serwisowy = 5 licznikow (short LE, kolejno: praca 100%, 50%, 30%,
        # podajnik, rozpalenia). Jego pozycja potrafi przesunac sie nawet o
        # kilkanascie bajtow wzgledem POWER100_TIME_short (zmiennej dlugosci
        # sekcje czujnikow/alarmow przed nim). Ramka jest na koncu wypelniona
        # zerami, a blok to OSTATNI zwarty ciag niezerowych bajtow - namierzamy
        # go skanujac od konca. Gdy nie znaleziono sensownego ciagu (>=10 B) -
        # fallback do statycznego offsetu.
        svc_end = len(message) - 1
        while svc_end > 0 and message[svc_end] == 0:
            svc_end -= 1
        svc_base = svc_end
        while svc_base > 0 and message[svc_base - 1] != 0:
            svc_base -= 1
        if svc_end - svc_base + 1 < 10:
            svc_base = POWER100_TIME_short  # fallback: statyczne offsety
        POWER100_TIME_short_val = struct.unpack("h", bytes(message[svc_base:svc_base+2]))[0]
        POWER50_TIME_short_val  = struct.unpack("h", bytes(message[svc_base+2:svc_base+4]))[0]
        POWER30_TIME_short_val  = struct.unpack("h", bytes(message[svc_base+4:svc_base+6]))[0]
        FEEDER_TIME_short_val   = struct.unpack("h", bytes(message[svc_base+6:svc_base+8]))[0]
        IGNITIONS_short_val     = struct.unpack("h", bytes(message[svc_base+8:svc_base+10]))[0]
        print(f"Blok serwisowy @ bajt {svc_base}")
        print(f"Praca MAX: {POWER100_TIME_short_val}h")
        print(f"Praca ŚRED: {POWER50_TIME_short_val}h")
        print(f"Praca MIN: {POWER30_TIME_short_val}h")
        print(f"Rozpalen: {IGNITIONS_short_val}")
        print(f"Praca podajnika: {FEEDER_TIME_short_val}h")
        print(" ")
    except (IndexError, struct.error) as e:
        print(f"Błąd parsowania ramki EcoMax08 (zbyt krótka ramka lub błędne dane): {e}")
        return
    except Exception as e:
        print(f"Nieoczekiwany błąd parsowania EcoMax08: {e}")
        return

    results = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s" % (
        tempCWU, tempCO, tempPogodowa, tempPodajnika, tempMieszacza,
        OP, TEMP_CO_SET_byte_val, TEMP_CWU_SET_byte_val,
        TEMP_MIXER_SET_byte_val, AIRFLOW_percent_byte_val,
        MIXER_SET_percent_byte_val, fuelStream, BOILER_POWER_float_val, flame,
        POWER100_TIME_short_val, POWER50_TIME_short_val, POWER30_TIME_short_val,
        IGNITIONS_short_val, FEEDER_TIME_short_val,
        mixer_pump, cwu_pump, boiler_pump, ignition,
        cleaning_actuator, feeder2, feeder, fan,
        status_mixer_set
    )
    try:
        with open(filename, 'w') as outfile:
            outfile.write(results)
    except OSError as e:
        print(f"Błąd zapisu pliku {filename}: {e}")

    # Surowa ramka (format listy) - uzywana przez narzedzia w test/ (compare.py, main.py)
    try:
        with open("/data/message.txt", 'w') as file_message:
            file_message.write("%s" % (message,))
    except OSError as e:
        print(f"Błąd zapisu pliku /data/message.txt: {e}")

    timestamp = datetime.now().isoformat(timespec="seconds")

    # Surowe dane: sama ramka + metadane
    raw = {
        "timestamp": timestamp,
        "typ_ramki": f"0x{message[0]:02X}",
        "dlugosc": len(message),
        "ramka": list(message),
    }

    # Dane przetworzone: nazwane, gotowe do uzycia
    data = {
        "timestamp": timestamp,
        "odczyty": {
            "stan": OP,
            "cwu": round(tempCWU, 2),
            "co": round(tempCO, 2),
            "dwor": round(tempPogodowa, 2),
            "palnik": round(tempPodajnika, 2),
            "mieszacz": round(tempMieszacza, 2),
            "zadana_co": TEMP_CO_SET_byte_val,
            "zadana_cwu": TEMP_CWU_SET_byte_val,
            "zadana_mieszacz": TEMP_MIXER_SET_byte_val,
            "nadmuch": AIRFLOW_percent_byte_val,
            "mieszacz_otwarcie": MIXER_SET_percent_byte_val,
            "mieszacz_status": status_mixer_set,
            "strumien_paliwa": round(fuelStream, 2),
            "moc": round(BOILER_POWER_float_val, 2),
            "plomien": round(flame, 2),
        },
        "serwis": {
            "blok_offset": svc_base,
            "praca_max_h": POWER100_TIME_short_val,
            "praca_sred_h": POWER50_TIME_short_val,
            "praca_min_h": POWER30_TIME_short_val,
            "zaplony": IGNITIONS_short_val,
            "podajnik_czas_h": FEEDER_TIME_short_val,
        },
        "wyjscia": {
            "bajt": message[OUTPUTS_byte],
            "bity": f"{message[OUTPUTS_byte]:08b}",
            "pompa_mieszacz": mixer_pump == "ON",
            "pompa_cwu": cwu_pump == "ON",
            "pompa_piec": boiler_pump == "ON",
            "zapalarka": ignition == "ON",
            "silownik_czyszczacy": cleaning_actuator == "ON",
            "podajnik_2": feeder2 == "ON",
            "podajnik": feeder == "ON",
            "wentylator": fan == "ON",
        },
        # Surowe bajty zwiazane z alarmem (znaczenie jeszcze nie potwierdzone).
        # Z logu 27.12.2024: przy alarmie po nieudanym rozpaleniu b196: 0->32,
        # b198: 2->0, b29: 4->2. Zbieramy, zeby zbudowac mape kod -> opis.
        "alarm": {
            "aktywny": message[OPERATING_STATUS_byte] == ALARM_STAN,
            "kod": _bajt(message, ALARM_KOD_byte),
            "opis": opis_alarmu(_bajt(message, ALARM_KOD_byte)),
            "opis_potwierdzony": (ALARM_KODY.get(_bajt(message, ALARM_KOD_byte), {}).get("potwierdzony")
                                  if _bajt(message, ALARM_KOD_byte) else None),
            "bajt_198": _bajt(message, ALARM_FLAGA_byte),
            "wyjscia2": _bajt(message, OUTPUTS2_byte),
            "wyjscia2_bity": f"{_bajt(message, OUTPUTS2_byte):08b}" if _bajt(message, OUTPUTS2_byte) is not None else None,
        },
    }

    for path, payload in (("/data/message.json", raw), ("/data/odczyty.json", data)):
        try:
            with open(path, 'w', encoding='utf-8') as fj:
                json.dump(payload, fj, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as e:
            print(f"Błąd zapisu pliku {path}: {e}")
