# Lønner det seg å ta en master?

Dette prosjektet sammenligner lønn etter kort og lang høyere utdanning innen samme fagområde.
Appen viser også en enkel beregning av hvor lang tid det tar å hente inn arbeidsinntekten
man går glipp av når man studerer videre.

Prosjektet dekker de fire delene av oppgaven:

| Del av oppgaven | Løsningen i prosjektet |
| --- | --- |
| Velge og beskrive en case | Sammenligne lønn og samlet inntekt etter bachelor og master |
| Samle inn data | Hente lønnstall fra SSB-tabell 14378 med Python |
| Lagre data på en ekstern server | MySQL på en Ubuntu-VM i VMware |
| Hente og presentere data | Streamlit-app som leser fra MySQL og viser tabeller og grafer |

## Data og avgrensning

Dataene kommer fra [SSB-tabell 14378](https://www.ssb.no/statbank/table/14378/).
Uttrekket gjelder heltidsansatte 0–2 år etter fullført utdanning. Det inneholder
gjennomsnittslønn, medianlønn og antall arbeidsforhold for hele Norge.

Appen bruker navnene bachelor og master for å gjøre sammenligningen lettere å lese.
SSBs grupper er litt bredere:

| Navn i appen | Utdanningsnivå i SSB |
| --- | --- |
| Bachelor | Høyere utdanning på 1–4 år, nivå 6 |
| Master | Høyere utdanning på over 4 år, nivå 7–8, inkludert doktorgrad |

Begge nivåene sammenlignes innen samme tresifrede fagkode og samme statistikkår.
Grupper uten publisert lønn eller med for få arbeidsforhold tas ikke med.
Manglende tall lagres som NULL i MySQL og brukes aldri som null kroner.

Ved kontroll 10. oktober 2026 inneholdt uttrekket 3 850 rader for 2015–2025.
Med median og minst 100 arbeidsforhold i hver gruppe kunne 41 faggrupper sammenlignes i 2025.
Dette er tall fra kildeuttrekket; innholdet på VM-en kan kontrolleres med SQL-kommandoene nedenfor.

## Hvordan programmet fungerer

~~~text
SSB → Python → MySQL på Ubuntu-VM → Streamlit → nettleser
~~~

Importen og appen kjøres hver for seg. Importen henter først metadata fra SSB for å finne
fagkodene, og deretter lønnstallene. Svaret valideres og skrives til MySQL gjennom
en SSH-tunnel. JSON-svaret behandles i minnet; det lagres ikke i en lokal datafil.

Hver databaserad identifiseres av år, fagkode og utdanningsnivå. En ny import oppdaterer
eksisterende rader uten å lage duplikater. Importen bruker én transaksjon:
commit lagrer endringene, mens rollback angrer dem hvis noe feiler.

Appen henter data fra MySQL ved oppstart og når brukeren endrer et valg.
Den beregner lønnsforskjeller og inntektsløp i Python. Grafen tegnes med Altair,
som allerede følger med Streamlit.

| Fil | Innhold |
| --- | --- |
| app.py | Brukergrensesnitt, grafer og CSV-nedlasting |
| src/main.py | SSB-import, validering, databasekobling og beregninger |
| start.ps1 | Korte kommandoer for tunnel, import og app |
| sql/schema.sql | Opprettelse av database og lønnstabell |
| tests/test_data.py | Tester av import, beregning og app |
| requirements.txt | Python-pakkene prosjektet bruker |
| video/ | Forklaringsvideo, undertekster og kapitteloversikt |

Funksjonene i src/main.py har korte forklaringer i koden.

## Beregningen

Begge inntektsløp starter etter fullført bachelor. Bachelorløpet begynner i jobb med én gang.
Masterløpet studerer først og får eventuell arbeidsinntekt under studiene.

~~~text
Tapt arbeidsinntekt og ekstra kostnader =
studieår × 12 × (bachelorlønn − arbeidsinntekt under studiene) + ekstra studiekostnader

Årlig lønnsforskjell = 12 × (masterlønn − bachelorlønn)

År for å hente inn kostnaden etter studiene = kostnad / årlig lønnsforskjell
~~~

Studieårene legges til for å finne tidspunktet regnet fra fullført bachelor.
Hvis mastergruppen ikke har høyere lønn, beregnes ingen innhentingstid.

For eksempel gir 50 000 kr mot 60 000 kr i månedslønn og to ekstra studieår uten jobb
1 200 000 kr i tapt arbeidsinntekt. Med en årlig lønnsforskjell på 120 000 kr
tar det 10 år i arbeid å hente dette inn, eller 12 år fra fullført bachelor.
Dette er et regneeksempel, ikke tall for et bestemt fagområde.

Lønningene holdes faste i hele beregningen. Skatt, lønnsvekst, renter, avkastning
og arbeidsledighet er ikke regnet med. Månedslønn × 12 brukes som årlig inntekt.
Resultatet er derfor et scenario, ikke en prognose.

Lønnsgruppene kan også ha forskjellig alder, arbeidserfaring og jobber.
Forskjellen viser ikke hva mastergraden alene gjør med lønnen.
SSB forklarer dette i [artikkelen om startlønn](https://www.ssb.no/arbeid-og-lonn/lonn-og-arbeidskraftkostnader/artikler/hvem-har-hoyest-startlonn).

## Starte prosjektet på denne maskinen

Oppsettet bruker Ubuntu-brukeren krcc, VM-adressen 192.168.68.53 og
MySQL-brukeren krcc@localhost. Databasen heter ssb_case.
Python-miljøet ligger under %LOCALAPPDATA%\venvs\ssb-arbeidskrav01.

Start VM-en og åpne to PowerShell-terminaler i prosjektmappen.

**Terminal 1:**

~~~powershell
.\start.ps1 tunnel
~~~

Oppgi Ubuntu-passordet og la terminalen stå åpen. Et stille vindu etter innlogging er normalt.

**Terminal 2:**

~~~powershell
.\start.ps1
~~~

Åpne http://127.0.0.1:8501 og skriv MySQL-passordet i det maskerte feltet.
Appen bruker ikke en lagret passordfil. Avslutt med Ctrl+C i begge terminalene.

Hvis PowerShell blokkerer skriptet, kan det startes slik i hvert sitt vindu.
Dette endrer bare policyen for prosessen som startes:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 tunnel
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
~~~

### Oppdatere data

Med tunnelen åpen, stopp appen og kjør i terminal 2:

~~~powershell
.\start.ps1 load
.\start.ps1
~~~

Importen spør etter MySQL-passordet. Import er bare nødvendig ved første innlasting
eller når SSB-dataene skal oppdateres.

## Første oppsett

### Python på Windows

Opprett miljøet og installer pakkene én gang:

~~~powershell
$projectEnv = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01'
python -m venv $projectEnv
$projectPython = Join-Path $projectEnv 'Scripts\python.exe'
& $projectPython -m pip install --no-compile -r requirements.txt
~~~

Miljøet ligger utenfor Google Drive fordi Drive tidligere la desktop.ini-filer
inn blant bibliotekets JSON-skjemaer. Det førte til feil ved grafvisning.
Prosjektkoden kan fortsatt ligge på G:. Startskriptet velger det lokale miljøet
automatisk. Det gamle .venv-miljøet er arkivert i ikke_leveres/ og skal ikke brukes.

### Ubuntu-server og MySQL

Bruk en VM-adresse som Windows kan nå, for eksempel med Bridged-nettverk i VMware.
I Ubuntu:

~~~bash
sudo apt update
sudo apt install openssh-server mysql-server
sudo systemctl enable --now ssh mysql
systemctl is-active ssh mysql
hostname -I
sudo ss -ltnp | grep ':3306'
~~~

MySQL skal lytte på 127.0.0.1:3306. Hvis den lytter på alle adresser,
sett bind-address = 127.0.0.1 under [mysqld] i
/etc/mysql/mysql.conf.d/mysqld.cnf og kjør sudo systemctl restart mysql.
Hvis UFW er aktiv, tillat SSH med sudo ufw allow OpenSSH.
MySQL-porten trenger ikke åpnes, siden forbindelsen går gjennom SSH.

Ved første SSH-tilkobling kan fingeravtrykket kontrolleres i VM-konsollen:

~~~bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
~~~

Bruk MySQL 8.0.19 eller nyere. Overfør skjemaet fra PowerShell:

~~~powershell
scp sql/schema.sql krcc@192.168.68.53:/home/krcc/schema.sql
ssh krcc@192.168.68.53
~~~

Kjør i Ubuntu:

~~~bash
sudo mysql < /home/krcc/schema.sql
sudo env MYSQL_HISTFILE=/dev/null mysql
~~~

Opprett databasebrukeren hvis den ikke finnes, og gi tilgang til den nye tabellen.
Erstatt passordplassholderen med et eget passord:

~~~sql
CREATE USER 'krcc'@'localhost' IDENTIFIED BY 'BYTT_TIL_ET_STERKT_PASSORD';
GRANT SELECT, INSERT, UPDATE ON ssb_case.education_salaries TO 'krcc'@'localhost';
EXIT;
~~~

Brukeren krcc finnes allerede på den nåværende VM-en. Der kjøres bare GRANT.
Skjemaet sletter ikke eksisterende tabeller eller data.
Ubuntu-passordet brukes av SSH, og MySQL-passordet brukes av importen og appen.
Passord skal ikke legges i prosjektfilene.

SSH-tunnelen videresender lokal port 3307 til MySQL på VM-en:

~~~powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:3307:127.0.0.1:3306 krcc@192.168.68.53
~~~

Hvis VM-adressen endres, må den oppdateres i start.ps1.
Startskriptet bruker port 3307; ved portendring må både tunnelen og DB_PORT i skriptet endres.

## Bruke appen

Start med siste år, median, ønsket fagområde og to studieår. Endre ett valg om gangen.

| Valg | Hva det påvirker |
| --- | --- |
| Statistikkår | Hvilket års lønnstall som brukes; ikke studiestartåret |
| Median eller gjennomsnitt | Median er lønnen i midten, mens gjennomsnitt kan trekkes opp av svært høye lønninger |
| Fagområde | Hvilken utdanningsgruppe som sammenlignes |
| Ekstra studieår | Hvor lenge masterløpet studerer før det begynner i jobb |
| Jobbinntekt under studiene | Reduserer arbeidsinntekten man går glipp av; lån og stipend regnes ikke med |
| Ekstra studiekostnader | Ett totalbeløp, for eksempel studieavgift og ekstra bøker; ikke tapt lønn |
| Antall år etter bachelor | Lengden på grafen og tidspunktet for sluttbeløpene |
| Minste antall jobber | Utelater små grupper; ligger under «Flere valg» |

Fanen **Ditt valg: inntekt over tid** viser akkumulert inntekt, altså alt man har tjent
til sammen. Masterløpet vises etter fratrekk av ekstra studiekostnader.
Den stiplede linjen markerer når inntektsløpene blir like.
Hvis tidspunktet ligger utenfor grafen, vises en melding.

**Lønnsforskjeller mellom fag** sammenligner månedslønninger, mens
**Se SSB-tallene** viser de importerte verdiene for valgt fagområde.
Studieplanen påvirker inntektsberegningen, ikke SSBs månedslønninger.

Knappen **Last ned beregningen til Excel (CSV)** laster ned valgene og beløpene
for hvert år i grafen. Filen bruker semikolon, desimalkomma og UTF-8 med BOM.
Passord tas ikke med i eksporten.

## Kontrollere løsningen

På Ubuntu kan innholdet i databasen kontrolleres slik:

~~~bash
sudo mysql ssb_case -e 'SELECT COUNT(*) AS observations, MIN(year) AS first_year, MAX(year) AS last_year FROM education_salaries;'
sudo mysql ssb_case -e "SELECT year, field_code, field_name, education_level, mean_salary, median_salary, jobs FROM education_salaries WHERE year = 2025 AND field_code = '541';"
~~~

Kjør testene fra PowerShell:

~~~powershell
$projectPython = Join-Path $env:LOCALAPPDATA 'venvs\ssb-arbeidskrav01\Scripts\python.exe'
& $projectPython -B -m unittest discover -s tests -v
~~~

De åtte testene kontrollerer validering, lønnssammenligning, innhentingstid,
import og rollback, passordfelt, grafmarkering og CSV-beløp.
Webtestene bruker en simulert database. Tilkobling og innhold på den faktiske VM-en
må i tillegg kontrolleres ved å kjøre importen og appen.

Ved feilmelding i appen: kontroller at tunnelen kjører, at tabellen er opprettet,
at MySQL-brukeren har tilgang, og at data er importert.
Kjør .\start.ps1 load i terminalen for å se importfeilen hvis appens melding ikke er nok.
En feil i passordet eller dataimporten kan ikke løses ved å endre grafen.

## Levering

Lever prosjektmappen uten **ikke_leveres/**. README.md er prosjektbeskrivelsen,
og video/ inneholder videopresentasjonen. Testene følger med kildekoden.

~~~text
prosjekt/
├── app.py
├── src/main.py
├── sql/schema.sql
├── tests/test_data.py
├── start.ps1
├── requirements.txt
├── README.md
├── .gitignore
├── video/
└── ikke_leveres/          ← utelates fra innleveringen
    ├── .venv/            ← gammelt Python-miljø
    ├── VIDEO_MANUS.md    ← manus til eget opptak
    ├── desktop.ini
    ├── src/__pycache__/
    └── tests/__pycache__/
~~~

Manuset ligger i ikke_leveres/VIDEO_MANUS.md og kan brukes som støtte under opptaket.
Tilpass formuleringene til måten du selv forklarer ting på.
Oppstartsskriptet og testkommandoen bruker -B for å unngå nye Python-cachefiler.
Google Drive kan opprette nye desktop.ini-filer; disse skal heller ikke leveres.
Passordfiler og SSH-nøkler skal aldri legges i leveringsmappen.
Kontroller import og databasekobling før opptaket, og bruk beløpene appen faktisk viser.

Kilder:
[SSB-tabell 14378](https://www.ssb.no/statbank/table/14378/),
[SSB om startlønn](https://www.ssb.no/arbeid-og-lonn/lonn-og-arbeidskraftkostnader/artikler/hvem-har-hoyest-startlonn),
[SSB API](https://www.ssb.no/api/pxwebapiv2).
En ferdig forklaringsvideo med syntetisk norsk tale ligger i
[video/MASTER_PRESENTASJON.mp4](video/MASTER_PRESENTASJON.mp4).
Se [video/LES_MEG.md](video/LES_MEG.md) for kapitler og undertekster.
Videoen viser kode og beregnede grafer. Suppler med et skjermopptak av den kjørende
appen og databasen for å dekke demonstrasjonen som oppgaven ber om.
