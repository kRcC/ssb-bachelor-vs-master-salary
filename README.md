# Lønner det seg å ta en master?

En Streamlit-app som sammenligner lønn etter kort og lang høyere utdanning
innen samme fagområde, basert på tall fra Statistisk sentralbyrå (SSB).
Du kan justere ekstra studieår, inntekt under studiene og studiekostnader
for å se hvordan valgene påvirker samlet inntekt over tid.

Prosjektet er laget som en skoleoppgave med datainnsamling fra SSB,
lagring i MySQL på en Ubuntu-server og presentasjon i en Python-webapp.

## Funksjoner

- Sammenligne medianlønn eller gjennomsnittslønn for ulike år og fagområder.
- Beregne når masterløpet tar igjen bachelorløpet i samlet inntekt.
- Vise akkumulert bruttoinntekt i en graf med innhentingspunkt.
- Sammenligne lønnsforskjeller mellom fagområder og se de underliggende SSB-tallene.
- Laste ned beregningen og forutsetningene som en CSV-fil til Excel.

## Data og avgrensninger

Dataene hentes fra [SSB-tabell 14378](https://www.ssb.no/statbank/table/14378/).
Uttrekket gjelder heltidsansatte 0–2 år etter fullført utdanning, for hele Norge.
Det inneholder gjennomsnittslønn, medianlønn og antall arbeidsforhold.

Appen bruker navnene bachelor og master for å gjøre sammenligningen lettere å lese.
SSBs grupper er bredere enn disse navnene:

| Navn i appen | Utdanningsgruppe i SSB |
| --- | --- |
| Bachelor | Høyere utdanning på 1–4 år, nivå 6 |
| Master | Høyere utdanning på over 4 år, nivå 7–8, inkludert doktorgrad |

Sammenligningen bruker samme år og tresifrede fagkode for begge nivåer.
Grupper uten publisert lønn eller med færre arbeidsforhold enn valgt grense utelates.
Manglende tall lagres som SQL `NULL`, og behandles aldri som null kroner.

Beregningen bruker faste brutto lønninger. Skatt, lønnsvekst, renter, avkastning
og arbeidsledighet er utelatt. Gruppene kan ha ulik alder, erfaring og ulike jobber.
Resultatet er et regnescenario, ikke en personlig prognose eller et mål på
effekten av mastergraden alene.

## Hvordan løsningen fungerer

~~~text
SSB → Python-import → MySQL på Ubuntu → Python → Streamlit → nettleser
                          ↑
                     SSH-tunnel
~~~

Importen og appen kjøres hver for seg. Importen henter data over HTTPS,
validerer svaret og lagrer radene i MySQL gjennom en OpenSSH-tunnel.
JSON-svaret behandles i minnet; det lagres ingen lokal JSON-fil.

Hver rad identifiseres av år, fagkode og utdanningsnivå. Ved ny import oppdateres
eksisterende rader. Hele importen skjer i én transaksjon: `commit` lagrer
endringene, og `rollback` angrer dem ved feil.

Appen leser fra MySQL ved oppstart og når brukeren endrer et valg.
Beregningene gjøres i Python, og grafen tegnes med Altair, som følger med Streamlit.

## Filer

| Fil | Innhold |
| --- | --- |
| [app.py](app.py) | Streamlit-grensesnitt, grafer og CSV-eksport |
| [src/main.py](src/main.py) | SSB-import, validering, databasekobling og beregninger |
| [sql/schema.sql](sql/schema.sql) | Database og tabell |
| [start.ps1](start.ps1) | Snarveier for lokal oppstart i PowerShell |
| [tests/test_data.py](tests/test_data.py) | Automatiske tester |
| [requirements.txt](requirements.txt) | Python-avhengigheter |

Lokale arbeidsfiler i `ikke_leveres/`, Python-miljøer, cache og passordfiler
er utelatt med `.gitignore`. Videopresentasjonen inngår i skoleleveringen
og følger ikke med dette repoet.

## Første oppsett

Du trenger Python, Git og OpenSSH-klient på maskinen som skal kjøre appen,
samt en Ubuntu-server med MySQL og OpenSSH-server. Ubuntu kan kjøres i VMware.
Serveren må være tilgjengelig fra maskinen din.

Kommandoene på Windows kjøres i PowerShell. Ubuntu-kommandoene kjøres i serverens konsoll
eller over SSH. Erstatt SSH-bruker, serveradresse og passordplassholdere med egne verdier.

### 1. Klon repoet og installer Python-pakkene

~~~powershell
git clone https://github.com/kRcC/ssb-bachelor-vs-master-salary.git
cd ssb-bachelor-vs-master-salary

$projectEnv = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01'
python -m venv $projectEnv
$projectPython = Join-Path $projectEnv 'Scripts\python.exe'
& $projectPython -m pip install --no-compile -r requirements.txt
~~~

Miljøet opprettes utenfor prosjektmappen for å holde installerte pakker utenfor
Git og eventuell skysynkronisering. Det er ikke nødvendig å aktivere miljøet;
kommandoene bruker Python-programmet direkte.

### 2. Installer tjenestene på Ubuntu

~~~bash
sudo apt update
sudo apt install openssh-server mysql-server
sudo systemctl enable --now ssh mysql
systemctl is-active ssh mysql
hostname -I
~~~

Noter serverens IP-adresse. I VMware må nettverkskortet være tilkoblet,
og valgt nettverksoppsett må gi Windows tilgang til VM-en.
Hvis UFW er aktiv, tillat SSH med `sudo ufw allow OpenSSH`.

MySQL skal lytte på `127.0.0.1:3306`. Kontroller med:

~~~bash
sudo ss -ltnp | grep ':3306'
~~~

Ved behov settes `bind-address = 127.0.0.1` under `[mysqld]` i
`/etc/mysql/mysql.conf.d/mysqld.cnf`. Start deretter MySQL på nytt med
`sudo systemctl restart mysql`. MySQL-porten trenger ikke åpnes i brannmuren;
tilkoblingen går gjennom SSH.

### 3. Opprett database og databasebruker

Importkoden bruker SQL-syntaks som krever MySQL 8.0.19 eller nyere.

Kjør i PowerShell fra prosjektmappen. Variablene brukes også når tunnelen åpnes senere:

~~~powershell
$sshUser = 'DIN_UBUNTU_BRUKER'
$serverAddress = 'DIN_SERVERADRESSE'
scp sql/schema.sql "${sshUser}@${serverAddress}:schema.sql"
ssh "${sshUser}@${serverAddress}"
~~~

Ved første tilkobling: sammenlign SSH-fingeravtrykket med det som vises i
Ubuntu-konsollen når du kjører `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.

Kjør på Ubuntu etter innlogging:

~~~bash
sudo mysql < ~/schema.sql
sudo env MYSQL_HISTFILE=/dev/null mysql
~~~

Opprett en egen MySQL-bruker. Dette er en databasebruker, og trenger ikke
ha samme navn eller passord som Ubuntu-brukeren:

~~~sql
CREATE USER 'ssb_app'@'localhost' IDENTIFIED BY 'BYTT_TIL_ET_EGET_PASSORD';
GRANT SELECT, INSERT, UPDATE ON ssb_case.education_salaries TO 'ssb_app'@'localhost';
EXIT;
~~~

Hvis databasebrukeren allerede finnes, kjør bare `GRANT`.
Skjemaet oppretter databasen `ssb_case` og tabellen `education_salaries`
uten å slette eksisterende tabeller.

### 4. Åpne SSH-tunnelen

I en PowerShell-terminal der `$sshUser` og `$serverAddress` er satt:

~~~powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:3307:127.0.0.1:3306 "${sshUser}@${serverAddress}"
~~~

La terminalen stå åpen. Ingen utskrift etter innlogging er normalt.
Tunnelen videresender lokal port `3307` til MySQL på serverens port `3306`.

### 5. Importer data og start appen

Åpne en ny PowerShell-terminal i prosjektmappen:

~~~powershell
$projectPython = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01\Scripts\python.exe'
$env:DB_USER = 'ssb_app'
$env:DB_PORT = '3307'

& $projectPython -B src/main.py load
& $projectPython -B -m streamlit run app.py --server.address 127.0.0.1
~~~

Importen spør etter MySQL-passordet i terminalen. Åpne deretter
[http://127.0.0.1:8501](http://127.0.0.1:8501) og skriv MySQL-passordet
i appens maskerte felt. Passordet lagres ikke i prosjektet.

Ved senere oppstart trenger du bare å starte serveren, åpne tunnelen og starte appen.
Sett `DB_USER` og `DB_PORT` på nytt hvis du bruker en ny terminal.
Importen kjøres ved første innlasting og når du vil oppdatere SSB-dataene.
Avslutt app og tunnel med Ctrl+C i hver terminal.

### Snarveier med start.ps1

`start.ps1` er laget for det opprinnelige lokale oppsettet.
Før du bruker det på din maskin, endre SSH-bruker og serveradresse i SSH-kommandoen
og sett `$env:DB_USER` til din MySQL-bruker. Skriptet setter denne verdien selv,
så den overstyrer en verdi du har satt i terminalen.
Python-miljøet må ligge på stien fra steg 1.

| Kommando | Handling |
| --- | --- |
| `.\start.ps1 tunnel` | Åpne tunnelen i en egen terminal |
| `.\start.ps1 load` | Importere eller oppdatere SSB-data mens tunnelen er åpen |
| `.\start.ps1` | Starte appen mens tunnelen er åpen |

Hvis PowerShell blokkerer skriptet, kan det startes med en policy som bare gjelder
den nye prosessen, for eksempel:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 tunnel
~~~

## Beregningen

Begge inntektsløp starter etter fullført bachelor. Bachelorløpet begynner i jobb
med én gang. Masterløpet har eventuell studieinntekt først og masterlønn etter studiene.

~~~text
Tapt inntekt og ekstra kostnader =
studieår × 12 × (bachelorlønn − studieinntekt) + ekstra studiekostnader

Årlig lønnsgevinst = 12 × (masterlønn − bachelorlønn)

År i jobb for å hente inn kostnaden = kostnad / årlig lønnsgevinst
~~~

Studieårene legges til for å finne tidspunktet regnet fra fullført bachelor.
Hvis masterlønnen ikke er høyere, beregnes ingen innhentingstid.

Eksempel: 50 000 kr mot 60 000 kr i månedslønn og to ekstra studieår uten
studieinntekt eller ekstra kostnader gir 1 200 000 kr i tapt arbeidsinntekt.
En årlig lønnsgevinst på 120 000 kr henter dette inn etter ti år i jobb,
altså tolv år etter bachelor. Dette er et regneeksempel, ikke SSB-tall for et bestemt fag.

## Bruke appen

Start med siste tilgjengelige år, median, ønsket fagområde og to studieår.

| Valg | Hva det påvirker |
| --- | --- |
| Statistikkår | Hvilket års lønnstall som brukes |
| Median eller gjennomsnitt | Lønnsmålet for begge utdanningsgrupper |
| Fagområde | Hvilke grupper som sammenlignes |
| Ekstra studieår | Når masterløpet begynner å tjene masterlønn |
| Jobbinntekt under studiene | Reduserer tapt arbeidsinntekt; lån og stipend er utelatt |
| Ekstra studiekostnader | Ett totalbeløp; tapt lønn beregnes separat |
| Tidshorisont | Lengden på grafen og tidspunktet for sluttbeløpene |
| Minste antall jobber | Utelater små grupper fra sammenligningen |

Grafen viser akkumulert bruttoinntekt, altså samlet inntekt fram til hvert tidspunkt.
Ekstra studiekostnader trekkes fra masterløpet ved start.
En stiplet linje markerer innhentingspunktet når det ligger innenfor valgt tidshorisont.

CSV-eksporten inneholder valgene og beløpene for hvert år, med semikolon,
desimalkomma og UTF-8 med BOM. Passord tas ikke med.

## Kontroll og feilsøking

Kjør testene fra prosjektmappen i PowerShell:

~~~powershell
$projectPython = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01\Scripts\python.exe'
& $projectPython -B -m unittest discover -s tests -v
~~~

Testene dekker validering, sammenligning, innhentingstid, transaksjoner,
passordfelt, grafmarkering og CSV-eksport. De bruker en simulert database;
tilkoblingen til din faktiske server må kontrolleres separat.

Kontroller tabellen på Ubuntu:

~~~bash
sudo mysql ssb_case -e 'SELECT COUNT(*) AS observations, MIN(year) AS first_year, MAX(year) AS last_year FROM education_salaries;'
~~~

- **SSH gir tidsavbrudd:** Kontroller at serveren kjører, at IP-adressen stemmer,
  at nettverket er tilkoblet og at SSH er aktiv.
- **Appen kan ikke hente lønnstall:** Kontroller tunnelen, MySQL-bruker og passord,
  tabelltilgang og at importen er kjørt. Kjør importkommandoen i terminalen for
  å se en mer konkret feil.
- **Ingen fagområder vises:** Prøv et annet år eller senk minste antall arbeidsforhold.

## Kilder

- [SSB-tabell 14378](https://www.ssb.no/statbank/table/14378/)
- [SSBs forklaring av startlønn](https://www.ssb.no/arbeid-og-lonn/lonn-og-arbeidskraftkostnader/artikler/hvem-har-hoyest-startlonn)
- [SSB API](https://www.ssb.no/api/pxwebapiv2)
