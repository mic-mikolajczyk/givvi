# Testowe uruchomienie GIVVI na VPS

Ta instrukcja prowadzi przez uruchomienie aplikacji na świeżym VPS w środowisku zbliżonym do produkcyjnego: z HTTPS, zarządzanym PostgreSQL w Neon i zewnętrznym SMTP. Domyślnie proces wysyłający pocztę pozostaje wyłączony, aby nie zużywał niepotrzebnie limitu bazy.

To **nie jest instrukcja oficjalnego uruchomienia produkcyjnego**. Cały przepływ HTTPS kontenerów i integracja z Neon nie zostały jeszcze potwierdzone. Kopie zapasowe, odtwarzanie, monitoring i inne wymagania opisane w [planie](plan.md) oraz [instrukcji operacyjnej](operations.md) pozostają otwarte. Używaj fikcyjnych danych; nie traktuj tego środowiska jako bezpiecznego miejsca na prywatne informacje. Publiczny adres aplikacji może być dostępny dla osób spoza grupy testowej.

## 1. Przygotuj potrzebne rzeczy

- VPS z Linuxem i publicznym adresem IP. Instrukcja zakłada zwykły Docker Engine na Linuxie, bez rootless Docker i mapowania identyfikatorów użytkowników.
- Domenę lub subdomenę, np. `test.twojadomena.pl`. Rekord DNS `A` musi wskazywać adres IPv4 VPS. Jeżeli jest rekord `AAAA`, musi wskazywać poprawnie działający IPv6 VPS; w przeciwnym razie usuń go.
- Dostępne z Internetu porty TCP **80 i 443**, zarówno w zaporze VPS, jak i u dostawcy. Port 80 jest potrzebny Caddy do uzyskania certyfikatu HTTPS. Zachowaj dostęp SSH podczas konfiguracji zapory.
- Konto [Neon](https://neon.com/) i testowy projekt PostgreSQL w planie Free.
- Konto u dostawcy poczty obsługującego wysyłanie przez SMTP z **STARTTLS**. Przygotuj adres serwera, port, login i hasło lub hasło do aplikacji.
- Adres repozytorium i dostęp do niego z VPS. Polecenia poniżej zakładają, że użytkownik ma dostęp do Dockera bez `sudo`.

Nie wystawiaj portu PostgreSQL na VPS: w tym wariancie baza działa w Neon i aplikacja łączy się z nią przez Internet.

## 2. Przygotuj pocztę

Nie musisz uruchamiać własnego serwera pocztowego. Możesz użyć Gmaila albo innego dostawcy, np. int.pl, o ile jego aktualna oferta pozwala aplikacjom wysyłać pocztę przez SMTP z STARTTLS. Sama nazwa adresu nie musi odpowiadać nazwie aplikacji.

Przykład dla Gmaila:

1. Załóż konto przeznaczone do testów i włącz weryfikację dwuetapową.
2. W ustawieniach konta Google utwórz **hasło do aplikacji**, jeśli jest dostępne. Zwykłe hasło do konta zazwyczaj nie wystarcza.
3. Użyj serwera `smtp.gmail.com`, portu `587`, pełnego adresu Gmail jako loginu i hasła do aplikacji jako hasła SMTP. Nadawcą ustaw ten sam adres Gmail.

Przy innym dostawcy sprawdź jego dokumentację: adres serwera, port, sposób logowania i dozwolony adres nadawcy mogą być inne. Ta aplikacja używa STARTTLS, nie bezpośredniego połączenia SMTP przez SSL na porcie 465.

Nawet przy wyłączonym workerze obecna konfiguracja Compose wymaga ustawień SMTP i plików z loginem oraz hasłem. Dopóki worker jest wyłączony, wiadomości nie są wysyłane. Rejestracja i zalogowanie nowego konta nie wymagają wiadomości powitalnej ani weryfikacji adresu.

## 3. Utwórz bazę w Neon

1. Zaloguj się do Neon i utwórz osobny projekt Free do testów, najlepiej w regionie bliskim VPS. Wybierz PostgreSQL 15 lub nowszy.
2. Zanotuj nazwę bazy, gałęzi i roli właściciela, np. odpowiednio `neondb`, `main` i `neondb_owner`. W panelu **Connect** wybierz tę bazę i rolę właściciela, a następnie pobierz **bezpośredni** adres połączenia, bez `-pooler` w nazwie hosta. Rola właściciela będzie używana do migracji.
3. Utwórz osobną rolę aplikacji z ograniczonym dostępem, np. `givvi_runtime`. Role tworzone standardowo w panelu Neon mają szerokie uprawnienia administratora, dlatego rolę aplikacji utwórz przez SQL, zgodnie z [dokumentacją Neon](https://neon.com/docs/manage/database-access).

W edytorze SQL Neon wybierz utworzoną bazę i połącz się jako rola właściciela, której później użyjesz do migracji. Przykład poniżej zakłada nazwę bazy `neondb` i schemat `public`. Zastąp hasło własnym silnym, losowym hasłem i nie udostępniaj go. Sprawdź również zasady zapisywania historii zapytań w używanym edytorze SQL.

```sql
CREATE ROLE givvi_runtime WITH LOGIN PASSWORD 'ZASTAP_SILNYM_HASLEM';
GRANT CONNECT ON DATABASE neondb TO givvi_runtime;
GRANT USAGE ON SCHEMA public TO givvi_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO givvi_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO givvi_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO givvi_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO givvi_runtime;
```

Domyślne uprawnienia dotyczą przyszłych obiektów tworzonych przez rolę wykonującą te polecenia. Migracje muszą więc działać jako ta sama rola właściciela. Jeżeli wybierzesz inną nazwę bazy, zastąp `neondb` poprawnym identyfikatorem SQL. Nie nadawaj roli aplikacji uprawnień administratora ani tworzenia tabel.

W panelu **Connect** pobierz również bezpośredni adres połączenia dla `givvi_runtime`. Obydwa adresy zawierają hasła: traktuj je jak sekrety i nie wysyłaj ich innym osobom.

### Ograniczenia Neon Free

Według [planu Neon](https://neon.com/docs/introduction/plans) sprawdzonego 6 listopada 2026 r. Free obejmuje m.in. **1 GB bazy**, **100 CU-godzin miesięcznie** i **5 GB transferu wychodzącego miesięcznie** na projekt. Limity mogą się zmienić, więc sprawdź aktualne wartości w panelu dostawcy.

- Po 5 minutach bezczynności baza może się uśpić, a następne zapytanie ją wznowi. Pierwsze żądanie może być wolniejsze; zachowanie aplikacji przy wybudzaniu trzeba przetestować.
- Po wyczerpaniu miesięcznego limitu mocy lub transferu Neon zawiesza bazę do odnowienia limitu albo zmiany planu. Po przekroczeniu limitu pamięci operacje zwiększające zajęte miejsce mogą się nie powieść. Dane nie są automatycznie usuwane.
- Przy stale aktywnej bazie o rozmiarze 0,25 CU 100 CU-godzin odpowiada około 400 godzinom, czyli niecałym 17 dniom. Większa moc wyczerpuje limit szybciej.
- Worker poczty wykonuje zapytania co 3 sekundy i może utrzymywać bazę aktywną. Nawet przy wyłączonym workerze użycie aplikacji, monitoring i inne zapytania zużywają limit. Obserwuj zużycie w panelu Neon.
- Plan Free ma ograniczone możliwości odzyskiwania: historia przywracania sięga maksymalnie 6 godzin, a automatyczny harmonogram snapshotów nie jest dostępny. Nie zastępuje to wymaganych, przetestowanych kopii zapasowych.

## 4. Przygotuj VPS i repozytorium

Zainstaluj Git, Docker Engine, wtyczkę Docker Compose, `curl` i `openssl` zgodnie z instrukcją dla wybranej dystrybucji. Zweryfikuj, że `docker compose version` działa i że DNS kieruje na VPS. Następnie sklonuj repozytorium:

```bash
git clone ADRES_REPOZYTORIUM givvi
cd givvi
```

Wszystkie dalsze polecenia Docker Compose uruchamiaj z katalogu repozytorium. Obrazy API i frontendu budują się w Dockerze; nie musisz instalować Pythona ani Node.js na VPS.

## 5. Ustaw zmienne środowiskowe

W tej samej sesji SSH ustaw wartości bez haseł. Przykład dla Gmaila:

```bash
export GIVVI_DOMAIN=test.twojadomena.pl
export GIVVI_SMTP_HOST=smtp.gmail.com
export GIVVI_SMTP_PORT=587
export GIVVI_SMTP_FROM=twoje-konto@gmail.com
export GIVVI_SECRETS_DIR="$HOME/givvi-secrets"

umask 077
mkdir -p "$GIVVI_SECRETS_DIR"
chmod 700 "$GIVVI_SECRETS_DIR"
```

Podmień domenę, adres nadawcy i ewentualnie serwer oraz port SMTP. Te zmienne obowiązują tylko w bieżącej sesji powłoki; po kolejnym logowaniu ustaw je ponownie przed użyciem poleceń Compose. Nie zapisuj haseł w tych zmiennych ani w repozytorium.

## 6. Przygotuj pliki sekretów

W katalogu `"$GIVVI_SECRETS_DIR"` utwórz edytorem następujące pliki. Ich zawartość nie powinna trafiać do historii poleceń, logów, repozytorium ani wiadomości do innych osób.

| Plik | Zawartość |
| --- | --- |
| `database_url` | URL Neon dla roli `givvi_runtime` |
| `migration_database_url` | URL tej samej bazy dla roli właściciela wykonującej migracje |
| `smtp_username` | Login SMTP, dla Gmaila pełny adres e-mail |
| `smtp_password` | Hasło SMTP lub hasło do aplikacji |

Oba adresy PostgreSQL muszą używać sterownika SQLAlchemy `postgresql+psycopg`, weryfikacji certyfikatu i nazwy hosta. Zachowaj host, nazwę bazy i dane odpowiedniej roli z panelu Neon. Przykładowy format, bez prawdziwych danych:

```text
postgresql+psycopg://UZYTKOWNIK:HASLO@HOST_NEON/BAZA?sslmode=verify-full&sslrootcert=/run/secrets/database_ca
```

Jeżeli adres z Neon zawiera dodatkowe parametry, np. `channel_binding=require`, zachowaj je i oddziel kolejne parametry znakiem `&`. Znaki specjalne w loginie i haśle muszą być zakodowane do postaci URL. Nie zamieniaj `verify-full` na słabszy tryb.

Zgodnie z [dokumentacją Neon](https://neon.com/docs/connect/connect-securely) można użyć publicznego certyfikatu głównego ISRG Root X1. Pobierz go do pliku montowanego w kontenerach:

```bash
curl --fail --show-error --location \
  https://letsencrypt.org/certs/isrgrootx1.pem \
  --output "$GIVVI_SECRETS_DIR/database_ca"
```

Zbuduj obrazy i wygeneruj klucz szyfrowania oraz token metryk:

```bash
docker compose -f deploy/compose.yaml build api web

docker run --rm --entrypoint python givvi-api:local \
  -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' \
  > "$GIVVI_SECRETS_DIR/outbox_key"

openssl rand -hex 32 > "$GIVVI_SECRETS_DIR/metrics_token"
```

Powyższe polecenia generujące sekrety wykonaj tylko przy pierwszej konfiguracji: ponowne uruchomienie nadpisze istniejące wartości. Zachowaj `outbox_key` w bezpiecznym miejscu. Jego zmiana uniemożliwi odszyfrowanie oczekujących wiadomości oraz zapisanych aktywnych linków zaproszeń. Token metryk również jest poufny.

Kontenery API i migracji działają jako użytkownik `10001`. Przy standardowym Dockerze na Linuxie nadaj plikom dostęp temu użytkownikowi:

```bash
sudo chown 10001:10001 "$GIVVI_SECRETS_DIR"/*
sudo chmod 400 "$GIVVI_SECRETS_DIR"/*
```

Katalog sekretów pozostaje dostępny tylko dla Twojego użytkownika na hoście. Jeżeli po zmianie właściciela edytujesz pliki przez `sudo`, ponownie sprawdź ich właściciela i uprawnienia. Rootless Docker, mapowanie użytkowników lub nietypowe zabezpieczenia hosta mogą wymagać innej konfiguracji dostępu.

## 7. Wykonaj migracje i uruchom aplikację

Sprawdź konfigurację i utwórz schemat w **testowej** bazie Neon:

```bash
docker compose -f deploy/compose.yaml config --quiet
docker compose --profile tools -f deploy/compose.yaml run --rm migrate
```

Migracja korzysta z `migration_database_url`. Jeżeli się nie powiedzie, nie kontynuuj: sprawdź połączenie, TLS i uprawnienia roli właściciela.

Uruchom tylko API i frontend, bez workera:

```bash
docker compose -f deploy/compose.yaml up -d api web
```

Nie używaj tutaj samego `docker compose ... up -d` bez nazw usług: uruchomiłoby również workera. Caddy w kontenerze `web` będzie próbował uzyskać certyfikat dla skonfigurowanej domeny.

## 8. Sprawdź wdrożenie

```bash
docker compose -f deploy/compose.yaml ps
curl --fail --show-error "https://${GIVVI_DOMAIN}/api/health/ready"
docker compose -f deploy/compose.yaml logs --since=10m api web
```

Endpoint gotowości powinien zwrócić `{"status":"ready"}`. Otwórz `https://test.twojadomena.pl`, sprawdź certyfikat, zarejestruj konto testowe i utwórz wydarzenie. Z drugim kontem sprawdź dołączenie przez ręcznie skopiowany link zaproszenia. Unikaj prawdziwych danych osobowych w nazwach wydarzeń, uczestników i listach prezentów.

Jeżeli HTTPS nie działa, sprawdź DNS, rekord `AAAA`, porty 80/443 i logi `web`. Jeżeli API lub migracja nie działa, sprawdź URL-e, uprawnienia plików sekretów, uprawnienia ról oraz certyfikat CA i dostęp do Neon. Błąd gotowości po bezczynności może wymagać sprawdzenia czasu wybudzania bazy. Nie publikuj logów bez sprawdzenia, czy nie zawierają poufnych danych.

## 9. Poczta: wyłączanie i test wysyłki

Przy uruchomieniu z kroku 7 worker nie działa. Aby zatrzymać go po wcześniejszym włączeniu:

```bash
docker compose -f deploy/compose.yaml stop worker
```

Bez workera nie dochodzą wiadomości resetowania hasła, potwierdzenia zmiany adresu ani zaproszenia wysyłane e-mailem. Reset hasła nie jest więc dostępny dla użytkowników. Ręczne kopiowanie linków zaproszeń nadal może działać. Poinformuj grupę testową o ograniczeniu i poproś o zachowanie haseł.

Możesz uruchomić worker na czas testu poczty:

```bash
docker compose -f deploy/compose.yaml up -d worker
docker compose -f deploy/compose.yaml logs --since=10m worker
```

Poproś o reset hasła dla kontrolowanego konta testowego, sprawdź skrzynkę i folder spam, a po teście zatrzymaj worker poleceniem `stop worker`. Link resetu wygasa po 30 minutach od zgłoszenia. Wiadomości mogą czekać w kolejce podczas postoju workera, ale przeterminowane lub nieaktualne nie zostaną poprawnie dostarczone; po dłuższej przerwie wyślij nowe żądanie. Worker wykonuje też porządkowanie wygasłych danych, które nie będzie działało podczas jego postoju.

Zamiast pracy ciągłej możesz po zgłoszeniu wiadomości wykonać jedną partię i zakończyć proces:

```bash
docker compose -f deploy/compose.yaml run --rm --no-deps worker flask --app givvi mail-worker
```

Jedna partia przetwarza maksymalnie 20 wiadomości gotowych w danym momencie. W razie przejściowego błędu SMTP ponowienie może być zaplanowane na później, więc pojedyncze uruchomienie nie gwarantuje dostarczenia. Sprawdź wynik i w razie potrzeby powtórz próbę po usunięciu przyczyny.

## 10. Zatrzymanie środowiska

Gdy testy są skończone, zatrzymaj kontenery:

```bash
docker compose -f deploy/compose.yaml stop
```

To nie usuwa bazy Neon, sekretów ani wolumenów Caddy. Aby później wznowić testy bez workera, ponownie ustaw zmienne z kroku 5 i wykonaj `docker compose -f deploy/compose.yaml up -d api web`. Nie usuwaj wolumenów Caddy ani projektu Neon, jeżeli chcesz zachować dane. Przed zaproszeniem użytkowników z rzeczywistymi danymi wróć do wymagań bezpieczeństwa, kopii zapasowych i pozostałych warunków w [instrukcji operacyjnej](operations.md).