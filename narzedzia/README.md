# Narzędzia ręczne — kasowanie alarmu

> **Narzędzie eksperymentalne.** Wysyła polecenie do sterownika kotła. Nic w tym
> katalogu nie uruchamia się samo: usługa `piec`, `install.sh` ani żaden cron
> go nie wywołują. Każde użycie to Twoja świadoma decyzja przy terminalu.

## Spis

- [Co robi `kasuj_alarm.py`](#co-robi-kasuj_alarmpy)
- [Zanim użyjesz — bezpieczeństwo](#zanim-użyjesz--bezpieczeństwo)
- [Procedura krok po kroku](#procedura-krok-po-kroku)
- [Opcje](#opcje)
- [Kody wyjścia](#kody-wyjścia)
- [Co wiemy o protokole, a co jest zgadnięte](#co-wiemy-o-protokole-a-co-jest-zgadnięte)
- [Gdy się nie uda](#gdy-się-nie-uda)
- [Pliki](#pliki)

## Co robi `kasuj_alarm.py`

Wysyła na magistralę RS-485 **jedną** ramkę „skasuj alarm” — taką samą, jaką
panel ecoSTER wysłał 04.10.2026 o 01:17:11, gdy alarm 32 został skasowany z
panelu. Potem przez 30 s obserwuje, czy piec odpowiedział i wyszedł z alarmu.

Bezpieczniki wbudowane w skrypt:

| bezpiecznik | zachowanie |
|---|---|
| tryb podglądu | bez `--wyslij` skrypt tylko słucha i mówi, co by zrobił |
| potwierdzenie | z `--wyslij` trzeba wpisać `TAK`; bez terminala (cron, skrypt) odmawia |
| stan pieca | wysyła tylko, gdy piec jest w ALARM **z kodem podanym w `--kod`**; sprawdza to dwa razy, drugi raz tuż przed nadaniem |
| lista kodów | kod musi być na liście `DOZWOLONE_KODY` w skrypcie (obecnie tylko `32`) |
| limit | najwyżej jedna wysyłka na 60 min (wg dziennika) |
| jedna próba | nigdy nie ponawia, nawet gdy się nie uda |
| port | odmawia, gdy działa usługa `piec` (oba procesy czytałyby ten sam port i psuły sobie dane) |

## Zanim użyjesz — bezpieczeństwo

Alarm 32 to najpewniej **nieudane rozpalenie** (wniosek z dwóch takich samych
zdarzeń: 27.12.2024 i 04.10.2026 — w obu palnik zimny, płomień 0, alarm prosto
z ROZPALANIA). Sterownik zatrzymuje się właśnie po to, żeby ktoś sprawdził palnik.

Skasowanie alarmu = **kolejna próba rozpalenia**, często z pelletem, który już
leży w palniku. W złym scenariuszu: dużo dymu albo zapłon nagromadzonych gazów
w komorze. Dlatego:

- kasuj zdalnie tylko, jeśli wiesz, dlaczego rozpalenie się nie udało (np. pusty zasobnik, który już uzupełniłeś),
- nie kasuj kilka razy z rzędu — po drugim nieudanym rozpaleniu idź do kotła,
- pierwszy test zrób, stojąc przy piecu.

## Procedura krok po kroku

Na Raspberry Pi, w `/home/pi/piec/narzedzia`:

```bash
# 1. Zatrzymaj usługę (zwalnia port /dev/ttyUSB0)
sudo systemctl stop piec

# 2. Podgląd — nic nie wysyła, sprawdza stan i kod alarmu
sudo python3 kasuj_alarm.py --kod 32

# 3. Wysyłka — pyta o TAK, wysyła jedną ramkę, obserwuje 30 s
sudo python3 kasuj_alarm.py --kod 32 --wyslij

# 4. ZAWSZE uruchom usługę z powrotem
sudo systemctl start piec
```

Same bajty ramki, bez otwierania portu:

```bash
python3 kasuj_alarm.py --kod 32 --tylko-ramka
```

## Opcje

| opcja | znaczenie |
|---|---|
| `--kod N` | wymagane; kod alarmu do skasowania (musi zgadzać się z bieżącym alarmem) |
| `--wyslij` | naprawdę wyślij (bez tego: podgląd) |
| `--jako panel` | domyślnie; nadaje jako panel ecoSTER (0x50) |
| `--jako econet` | nadaje jako moduł ecoNET (0x56) — patrz niżej |
| `--tylko-ramka` | wypisz bajty ramki i zakończ |
| `--obserwuj S` | ile sekund obserwować po wysłaniu (domyślnie 30) |
| `--port P` | port szeregowy (domyślnie `/dev/ttyUSB0`) |

## Kody wyjścia

| kod | znaczenie |
|---|---|
| 0 | podgląd OK albo alarm skasowany |
| 2 | kod spoza listy, działa usługa `piec` albo nie da się otworzyć portu |
| 3 | brak ramek od pieca albo piec nie jest w ALARM z tym kodem |
| 4 | limit — za wcześnie od poprzedniej wysyłki |
| 5 | nie wpisano `TAK` |
| 6 | nie znaleziono momentu nadania w 10 s |
| 7 | wysłano, ale piec nadal w alarmie |

## Co wiemy o protokole, a co jest zgadnięte

Budowa ramki (pewne — tak samo liczy `src/start.py`, zweryfikowane na 1097 ramkach z logu):

```
68 | dł.L dł.H | odbiorca | nadawca | typ nadawcy | wersja | typ ramki | dane... | CRC | 16
```

- długość = liczba bajtów całej ramki,
- CRC = XOR wszystkich bajtów przed CRC, łącznie z `68`.

Ramka kasowania alarmu 32 jako panel:

```
68 0D 00 45 50 B0 07 71 03 20 00 95 16
```

| element | wartość | pewność |
|---|---|---|
| typ ramki `0x71`, dane `[3, 32, 0]` | zaobserwowane u Ciebie 04.10.2026 01:17:11 | pewne, że panel to wysłał w chwili końca alarmu |
| `3` = „kasuj alarm”, `32` = kod | wniosek z jednej obserwacji | prawdopodobne |
| odpowiedź pieca `0xF1` | zaobserwowana | pewne |
| nagłówek panelu `B0 07` (typ nadawcy, wersja) | wzięte z ramek 0x89 panelu | prawdopodobne; parser zapisuje teraz pełne ramki, więc przy następnym kasowaniu z panelu sprawdzisz w `/home/pi/piec_dane/polecenia.jsonl` (pole `ramka_pelna`) |
| ramka `0x71 [2]` wysyłana przez panel 10 s po kasowaniu | zaobserwowana | **znaczenie nieznane**; skrypt jej nie wysyła |
| nagłówek ecoNET `30 07` | `30` z oryginalnego kodu econetanalyze, `07` zgadnięte | niepewne |

**Moment nadania.** RS-485 to jedna para przewodów; naraz może nadawać jedno
urządzenie. Piec (0x45) jest masterem i co ok. 1 s odpytuje kolejne adresy:

- `--jako panel`: prawdziwy panel odpowiada co cykl (ramka 0x89). Skrypt czeka,
  aż panel skończy swoją ramkę, i nadaje zaraz po niej. Jeśli piec zaczyna
  nadawać natychmiast po panelu, ramki mogą się zderzyć — wtedy skrypt zgłosi
  brak efektu (kod 7).
- `--jako econet`: piec odpytuje adres 0x56 (typ 0x30) i nikt nie odpowiada —
  skrypt nadaje w tym pustym okienku, więc kolizji nie ma. **Nie wiadomo**, czy
  piec przyjmie polecenie od tego adresu.

**Echo.** Wiele przejściówek USB-RS485 odbiera własną transmisję. `echo=True`
w wyniku oznacza, że bajty wyszły na magistralę — to dobry znak dla przejściówki,
ale nie znaczy, że piec je przyjął. O tym mówi `odpowiedz_F1` i zmiana stanu.

## Gdy się nie uda

Skrypt nie ponawia. Kolejność sprawdzania:

1. `echo=False` — przejściówka nie nadaje albo nie przełącza kierunku (potrzebna automatyczna obsługa DE/RE).
2. `echo=True`, brak `0xF1` — kolizja albo piec nie akceptuje nadawcy/nagłówka. Po upływie limitu można spróbować `--jako econet`.
3. Jest `0xF1`, ale nadal ALARM — polecenie przyjęte, ale nie zadziałało (inny kod, brakujące `0x71 [2]` itp.). Skasuj z panelu i porównaj w `polecenia.jsonl` pełne ramki panelu z naszą.

## Pliki

| plik | co to |
|---|---|
| `/home/pi/piec_dane/kasowanie_alarmu.log` | dziennik wysyłek tego skryptu (z niego liczony jest limit) |
| `/home/pi/piec_dane/polecenia.jsonl` | zapisywany przez usługę `piec`: każda ramka spoza cyklicznego odpytywania — polecenia z panelu (0x70, 0x61, 0x71…) i odpowiedzi pieca (0xF0, 0xE1, 0xF1…), z pełną ramką i stanem pieca przed/po |
| `/home/pi/piec_dane/parametry.json`, `parametry_zmiany.jsonl` | tabela nastaw sterownika i dziennik jej zmian (tylko odczyt — ten skrypt niczego w niej nie zmienia) |
| `/home/pi/piec_dane/alarmy/alarm_*.json` | historia alarmów; pole `sposob_zakonczenia` mówi, czy alarm skasowano poleceniem, czy minął sam |

Kody alarmów i ich opisy są w `src/ecomax850p2.py` → `ALARM_KODY`. Gdy
potwierdzisz opis z panelu, ustaw tam `"potwierdzony": True`.
