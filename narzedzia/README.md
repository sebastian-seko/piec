# Narzędzia ręczne — sterowanie piecem

> **Narzędzie eksperymentalne.** Wysyła polecenia do sterownika kotła. Nic w tym
> katalogu nie uruchamia się samo: usługa `piec`, `piec-mqtt`, `install.sh`, cron
> ani Home Assistant go nie wywołują. Każde użycie to Twoja decyzja przy terminalu (SSH).

## Spis

- [Co robi `sterowanie.py`](#co-robi-sterowaniepy)
- [Zanim użyjesz — bezpieczeństwo](#zanim-użyjesz--bezpieczeństwo)
- [Użycie](#użycie)
- [Kiedy skrypt odmówi](#kiedy-skrypt-odmówi)
- [Kody wyjścia](#kody-wyjścia)
- [Co wiemy o protokole, a co jest zgadnięte](#co-wiemy-o-protokole-a-co-jest-zgadnięte)
- [Gdy się nie uda](#gdy-się-nie-uda)
- [Pliki](#pliki)

## Co robi `sterowanie.py`

Wysyła na magistralę RS-485 **jedną** ramkę — dokładnie taką, jaką wysyła panel
ecoSTER, gdy naciskasz przycisk (bajt w bajt identyczną z ramkami złapanymi od panelu):

| polecenie | ramka | oczekiwany efekt |
|---|---|---|
| `wlacz` | `68 0B 00 45 50 B0 07 71 01 B1 16` | WYŁĄCZONY → CZYSZCZENIE → ROZPALANIE |
| `wylacz` | `68 0B 00 45 50 B0 07 71 02 B2 16` | → WYGASZANIE → WYŁĄCZONY |
| `kasuj --kod 32` | `68 0D 00 45 50 B0 07 71 03 20 00 95 16` | ALARM → wyjście z alarmu (kolejne rozpalanie) |

Przebieg z `--wyslij`:

1. odczyt stanu pieca z `/data/odczyty.json` (bez dotykania portu i usługi) i sprawdzenie warunków,
2. sprawdzenie limitu czasowego,
3. ostrzeżenie i **wpisanie `TAK`**,
4. zatrzymanie usługi `piec` (zwalnia port),
5. ponowne sprawdzenie stanu **na żywo z magistrali**,
6. nadanie w wolnym okienku, zapis do dziennika,
7. obserwacja (do 60 s, krócej gdy cel osiągnięty): odpowiedź pieca `0xF1` i zmiana stanu,
8. **zawsze** ponowne uruchomienie usługi `piec` — także po błędzie i Ctrl+C.

Przerwa w odczytach (HA, alarmy) trwa zwykle 15–40 s.

## Zanim użyjesz — bezpieczeństwo

`wlacz` i `kasuj` uruchamiają **rozpalanie**, gdy nikt nie stoi przy kotle.

- Alarm 32 to **„Nieudana próba rozpalenia kotła”** (tekst z panelu, potwierdzony 10.11.2026). Skasowanie = kolejna próba, często
  z pelletem, który już leży w palniku. W złym scenariuszu: dużo dymu albo zapłon
  nagromadzonych gazów w komorze. Po drugim nieudanym rozpaleniu idź do kotła.
- Zdalnie włączaj tylko, jeśli wiesz, w jakim stanie jest kocioł (pellet w zasobniku,
  palnik wyczyszczony, nic nie zostało zalane).
- `wylacz` jest bezpiecznym kierunkiem — piec sam przechodzi przez wygaszanie.
- Pierwszy test każdego polecenia zrób przy piecu.

## Użycie

Na Raspberry Pi, w `/home/pi/piec/narzedzia`:

```bash
# podgląd - pokazuje stan i ramkę, NIC nie wysyła, nie dotyka portu ani usługi
python3 sterowanie.py wlacz
python3 sterowanie.py wylacz
python3 sterowanie.py kasuj --kod 32

# wysyłka - pyta o TAK, sama zatrzymuje i przywraca usługę piec
sudo python3 sterowanie.py wlacz --wyslij
sudo python3 sterowanie.py wylacz --wyslij
sudo python3 sterowanie.py kasuj --kod 32 --wyslij
```

Opcje:

| opcja | znaczenie |
|---|---|
| `--wyslij` | naprawdę wyślij (wymaga `sudo` i wpisania `TAK`) |
| `--kod N` | kod alarmu dla `kasuj` — musi zgadzać się z bieżącym alarmem |
| `--jako panel` | domyślnie; nadaje jako panel ecoSTER (0x50) |
| `--jako econet` | nadaje jako moduł ecoNET (0x56) — patrz niżej |
| `--obserwuj S` | maks. sekund obserwacji po wysłaniu (domyślnie 60) |
| `--port P` | port szeregowy (domyślnie `/dev/ttyUSB0`) |

## Kiedy skrypt odmówi

| polecenie | wolno tylko gdy | limit |
|---|---|---|
| `wlacz` | stan WYŁĄCZONY i brak kodu alarmu | wspólny z `kasuj`: 1 na 30 min |
| `wylacz` | ROZPALANIE, PRACA, POSTÓJ, PRACA RĘCZNA, CZYSZCZENIE | 1 na 2 min |
| `kasuj` | ALARM z kodem = `--kod`, kod na liście `DOZWOLONE_KODY` (dziś: 32) | wspólny z `wlacz`: 1 na 30 min |

Oraz zawsze, gdy: dane parsera są starsze niż 120 s, brak terminala (cron/skrypt),
brak `sudo`, stan na magistrali różni się od tego z pliku, brak wolnego okienka w 10 s.

Wspólny limit dla `wlacz` i `kasuj`: oba uruchamiają rozpalanie, więc nie da się
zrobić „włącz, nie wyszło, kasuj, włącz…” w kółko.

## Kody wyjścia

| kod | znaczenie |
|---|---|
| 0 | podgląd OK albo polecenie przyjęte (stan zmienił się zgodnie z oczekiwaniem) |
| 2 | błąd użycia: kod spoza listy, brak sudo, nie da się zatrzymać usługi / otworzyć portu |
| 3 | stan pieca nie pozwala (z pliku albo na żywo) / brak świeżych danych |
| 4 | limit czasowy |
| 5 | nie wpisano `TAK` |
| 6 | nie znaleziono momentu nadania w 10 s |
| 7 | wysłano, ale stan się nie zmienił |

## Co wiemy o protokole, a co jest zgadnięte

Budowa ramki (pewne — zweryfikowane na 1097 ramkach z logu i ramkach panelu):

```
68 | dł.L dł.H | odbiorca | nadawca | typ nadawcy | wersja | typ ramki | dane... | CRC | 16
```

- długość = liczba bajtów całej ramki,
- CRC = XOR wszystkich bajtów przed CRC, łącznie z `68`.

| element | skąd wiemy | pewność |
|---|---|---|
| `0x71 [1]` = włącz | 06.11.2026 16:27:38: WYŁĄCZONY → CZYSZCZENIE | pewne |
| `0x71 [2]` = wyłącz | 06.11.2026 16:31:20: ROZPALANIE → WYGASZANIE | pewne |
| `0x71 [3, kod, 0]` = kasuj alarm | 04.10.2026 01:17:11: koniec alarmu 32 w tej samej sekundzie | prawdopodobne (jedna obserwacja) |
| odpowiedź pieca `0xF1` na każde `0x71` | wszystkie obserwacje | pewne |
| nagłówek panelu `50 B0 07` | pełne ramki panelu z 06.11.2026 | pewne |
| piec przyjmie ramkę od nas tak jak od panelu | — | **do sprawdzenia przy pierwszym użyciu** |
| nagłówek ecoNET `56 30 07` | `30` z oryginalnego econetanalyze, `07` zgadnięte | niepewne |

**Moment nadania.** RS-485 to jedna para przewodów; naraz może nadawać jedno
urządzenie. Piec (0x45) jest masterem i ok. 1,2 razy na sekundę odpytuje kolejne adresy.

- `--jako panel`: prawdziwy panel odpowiada co cykl. Skrypt czeka, aż panel skończy
  swoją ramkę, i nadaje zaraz po niej. Jeśli piec zacznie nadawać w tej samej chwili,
  ramki się zderzą — wtedy skrypt zgłosi brak efektu (kod 7).
- `--jako econet`: piec odpytuje adres 0x56 i nikt nie odpowiada — skrypt nadaje
  w tym pustym okienku, więc kolizji nie ma. **Nie wiadomo**, czy piec przyjmie
  polecenie od tego adresu.

**Echo.** Wiele przejściówek USB-RS485 odbiera własną transmisję. `echo=True`
oznacza, że bajty wyszły na magistralę — ale nie, że piec je przyjął. O tym mówi
`odpowiedz_F1` i zmiana stanu.

## Gdy się nie uda

Skrypt nie ponawia. Kolejność sprawdzania (wynik jest w dzienniku):

1. `echo=False` — przejściówka nie nadaje albo nie przełącza kierunku (potrzebna automatyczna obsługa DE/RE).
2. `echo=True`, brak `0xF1` — kolizja albo piec nie akceptuje nadawcy. Po upływie limitu spróbuj ponownie albo `--jako econet`.
3. Jest `0xF1`, ale stan bez zmian — polecenie przyjęte, ale nie zadziałało. Wykonaj to samo z panelu
   i porównaj w `/home/pi/piec_dane/polecenia.jsonl` pełną ramkę panelu z naszą.

## Pliki

| plik | co to |
|---|---|
| `/home/pi/piec_dane/sterowanie.log` | dziennik wysyłek (`WYSLANO …` i `WYNIK …`); z niego liczone są limity |
| `/home/pi/piec_dane/polecenia.jsonl` | zapisywany przez usługę `piec`: każde polecenie z panelu i odpowiedź pieca, z pełną ramką i stanem przed/po |
| `/home/pi/piec_dane/alarmy/alarm_*.json` | historia alarmów; `sposob_zakonczenia` mówi, czy alarm skasowano poleceniem |

Polecenia wysłane tym skryptem **nie** trafią do `polecenia.jsonl` — na czas
wysyłki parser jest zatrzymany. Są w `sterowanie.log`.

Kody alarmów i opisy: `src/ecomax850p2.py` → `ALARM_KODY`. Dozwolone do kasowania:
`narzedzia/sterowanie.py` → `DOZWOLONE_KODY`.
