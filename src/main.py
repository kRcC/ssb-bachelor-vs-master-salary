"""SSB utdanningsfordelt lønn -> MySQL gjennom OpenSSH -> Streamlit."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from getpass import getpass
from itertools import product
import json
import math
import os
import re
import sys
from typing import cast
from urllib.parse import urlencode
from urllib.request import urlopen

API = 'https://data.ssb.no/api/pxwebapi/v2/tables/14378'
MEASURES = {'median': 'Median', 'mean': 'Gjennomsnitt'}
# MySQL-markøren returnerer tupler: år, fagkode, navn, nivå, gjennomsnitt, median, jobber.
SalaryRecord = tuple[int, str, str, str, Decimal | None, Decimal | None, int | None]


def rows_from_dataset(dataset):
    """Gjør SSB-svaret om til validerte rader som kan lagres i MySQL.

    Leser dimensjonenes rekkefølge fra svaret og samler lønnsmålene per
    år, fagkode og utdanningsnivå. Returnerer en liste med tupler:
    (år, fagkode, navn, nivå, gjennomsnitt, median, arbeidsforhold).
    Ugyldige data gir ValueError; manglende tall beholdes som None.
    """
    ids = dataset['id']
    if len(ids) != 7 or set(ids) != {'MaaleMetode', 'UtdNivaa', 'AntAarEtterUtd', 'Fagfelt',
                                    'AvtaltArbTid', 'ContentsCode', 'Tid'}:
        raise ValueError('Uventede dimensjoner fra SSB.')
    codes = []
    for dimension in ids:
        index = dataset['dimension'][dimension]['category']['index']
        if not isinstance(index, dict) or sorted(index.values()) != list(range(len(index))):
            raise ValueError('Ugyldig dimensjonsindeks.')
        codes.append(sorted(index, key=lambda code: index[code]))
    values = dataset['value']
    if dataset['size'] != [len(c) for c in codes] or not isinstance(values, list) or len(values) != math.prod(dataset['size']):
        raise ValueError('Ufullstendig datasett.')
    groups = {}
    # product lager alle kombinasjonene i samme rekkefølge som SSBs flate verdiliste.
    for coordinates, value in zip(product(*codes), values, strict=True):
        point = dict(zip(ids, coordinates, strict=True))
        field, year, level, metric = (point[k] for k in ('Fagfelt', 'Tid', 'UtdNivaa', 'MaaleMetode'))
        if not re.fullmatch(r'[1-8][0-9]{2}', field) or level not in ('3', '4') or metric not in ('01', '02', '10'):
            raise ValueError('Uventet utdanning eller statistikkmål.')
        if not re.fullmatch(r'20[0-9]{2}', year) or not 2015 <= int(year) <= datetime.now(timezone.utc).year:
            raise ValueError('Ugyldig år.')
        if point['AntAarEtterUtd'] != '00-02' or point['AvtaltArbTid'] != '5' or point['ContentsCode'] != 'Manedslonn':
            raise ValueError('Uventet erfaring, arbeidstid eller lønnsvariabel.')
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Ugyldig tall fra SSB.')
            if metric == '10':
                if value != int(value) or not 0 <= value <= 4_294_967_295:
                    raise ValueError('Ugyldig antall arbeidsforhold.')
            elif not 0 < value < 10_000_000_000:
                raise ValueError('Ugyldig månedslønn.')
        # Samme nøkkel samler median (01), gjennomsnitt (02) og antall jobber (10).
        groups.setdefault((int(year), field, level), {})[metric] = value
    rows = []
    for (year, field, level), measures in groups.items():
        name = dataset['dimension']['Fagfelt']['category']['label'][field]
        if set(measures) != {'01', '02', '10'} or not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise ValueError('Mangler statistikkmål eller gyldig fagfeltnavn.')
        # ponytail: skjermede verdier blir SQL NULL, aldri null kroner i sammenligningen.
        rows.append((year, field, name, level, measures['02'], measures['01'], measures['10']))
    if not rows or not any(row[4] is not None for row in rows):
        raise ValueError('Ingen publiserte lønnstall.')
    return rows


def fetch_ssb_rows():
    """Henter utdanningskoder og lønnstall fra SSB-tabell 14378 over HTTPS.

    Velger heltidsansatte 0–2 år etter utdanning og kort/lang høyere utdanning.
    Sender svaret til rows_from_dataset og returnerer databaseklare rader.
    Nettverksfeil og ugyldige svar sendes videre til den som startet importen.
    """
    with urlopen(API + '/metadata?lang=no', timeout=30) as response:
        metadata = json.load(response)
    fields = [code for code in metadata['dimension']['Fagfelt']['category']['index']
              if re.fullmatch(r'[1-8][0-9]{2}', code)]
    if not fields:
        raise ValueError('Ingen utdanningsgrupper fra SSB.')
    params = {'lang': 'no', 'outputFormat': 'json-stat2', 'valueCodes[MaaleMetode]': '01,02,10',
              'valueCodes[UtdNivaa]': '3,4', 'valueCodes[AntAarEtterUtd]': '00-02',
              'valueCodes[Fagfelt]': ','.join(fields), 'valueCodes[AvtaltArbTid]': '5',
              'valueCodes[ContentsCode]': 'Manedslonn', 'valueCodes[Tid]': '*'}
    with urlopen(API + '/data?' + urlencode(params), timeout=30) as response:
        dataset = json.load(response)
    # ponytail: kun utdanningsgrupper på samme detaljnivå; ingen lokal JSON-fil.
    return rows_from_dataset(dataset)


def connect(password=None):
    """Returnerer en MySQL-forbindelse via den lokale SSH-tunnelporten.

    Appen sender inn passordet fra passordfeltet. Uten argument spør getpass
    i terminalen. DB_USER og DB_PORT kan overstyre standardene krcc og 3307.
    Endringer lagres først når den som bruker forbindelsen kaller commit.
    """
    import mysql.connector

    return mysql.connector.connect(
        host='127.0.0.1', port=int(os.environ.get('DB_PORT', '3307')),
        user=os.environ.get('DB_USER', 'krcc'),
        password=getpass('MySQL-passord: ') if password is None else password, database='ssb_case',
        connection_timeout=10, autocommit=False, use_pure=True)


def load():
    """Henter og validerer SSB-data, og importerer dem til MySQL.

    Nye år/fagkoder/nivåer settes inn; eksisterende rader oppdateres.
    Alt skrives i én transaksjon: commit lagrer, rollback angrer ved feil.
    Skriver antall importerte rader til terminalen; returnerer ingen verdi.
    """
    rows = fetch_ssb_rows()
    with connect() as connection:
        try:
            with connection.cursor() as cursor:
                # %s-plassholdere sender data separat fra SQL; executemany bruker alle radene.
                cursor.executemany(
                    'INSERT INTO education_salaries '
                    '(year, field_code, field_name, education_level, mean_salary, median_salary, jobs) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s) AS incoming '
                    'ON DUPLICATE KEY UPDATE field_name = incoming.field_name, '
                    'mean_salary = incoming.mean_salary, median_salary = incoming.median_salary, '
                    'jobs = incoming.jobs', rows)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    print(f'Importert/oppdatert {len(rows)} lønnsobservasjoner i MySQL.')


def fetch_records(password=None) -> list[SalaryRecord]:
    """Leser lønnstabellen fra MySQL og returnerer en liste med radtupler.

    Bruker connect med appens passord og sorterer nyeste år først.
    with-blokkene lukker markør og forbindelse etter lesingen.
    En tom tabell gir ValueError, slik at appen ikke viser tomme resultater.
    """
    with connect(password) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT year, field_code, field_name, education_level, mean_salary, median_salary, jobs '
                           'FROM education_salaries ORDER BY year DESC, field_code, education_level')
            records = cast(list[SalaryRecord], cursor.fetchall())
    if not records:
        raise ValueError('Ingen lønnstall i databasen. Kjør load.')
    return records


def compare_fields(records, year, measure, min_jobs=0):
    """Sammenligner utdanningsnivåene innen hvert fagområde i valgt år.

    records er databaseradene; measure velger median eller mean (gjennomsnitt).
    Utelater manglende lønn og grupper med færre arbeidsforhold enn min_jobs.
    Returnerer ordbøker med lønn og forskjell, sortert etter størst lønnsforskjell.
    Bare fagområder med begge nivåer blir med; scenarioets studieplan brukes ikke her.
    """
    if measure not in MEASURES or type(min_jobs) is not int or min_jobs < 0:
        raise ValueError('Ugyldig statistikkmål eller minsteantall arbeidsforhold.')
    groups = {}
    for period, code, name, level, mean, median, jobs in records:
        if period != year:
            continue
        salary = median if measure == 'median' else mean
        if salary is None or jobs is None or jobs < min_jobs:
            continue
        salary = float(salary)
        if not math.isfinite(salary) or salary <= 0:
            raise ValueError('Ugyldig månedslønn i databasen.')
        groups.setdefault(code, {'Fagfelt': name, 'Kode': code})[level] = (salary, int(jobs))
    rows = []
    for group in groups.values():
        if '3' not in group or '4' not in group:
            continue
        bachelor, bachelor_jobs = group['3']
        master, master_jobs = group['4']
        rows.append({'Fagfelt': group['Fagfelt'], 'Kode': group['Kode'],
                     'Bachelor (kr/mnd)': bachelor, 'Master (kr/mnd)': master,
                     'Forskjell (kr/mnd)': master - bachelor,
                     'Forskjell (%)': (master / bachelor - 1) * 100,
                     'Arbeidsforhold bachelor': bachelor_jobs, 'Arbeidsforhold master': master_jobs})
    return sorted(rows, key=lambda row: (-row['Forskjell (kr/mnd)'], row['Kode']))


def scenario(bachelor, master, study_years, study_income, extra_cost):
    """Beregner hvor mye masterløpet må ta igjen, og tiden det tar etter studiene.

    bachelor/master/study_income er brutto månedslønn i kroner; study_years
    er ekstra studieår, og extra_cost er samlet ekstra kostnad i kroner.
    Returnerer (tapt inntekt pluss kostnader, år i jobb for å hente inn dette).
    Det siste tallet er None hvis masterlønn ikke er høyere enn bachelorlønn.
    """
    numbers = (bachelor, master, study_years, study_income, extra_cost)
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in numbers):
        raise ValueError('Scenarioet må inneholde endelige tall.')
    if bachelor <= 0 or master <= 0 or study_years <= 0 or not 0 <= study_income <= bachelor or extra_cost < 0:
        raise ValueError('Ugyldige scenarioverdier.')
    # ponytail: faste brutto lønninger, uten skatt, lønnsvekst, rente eller avkastning.
    lost_income = study_years * 12 * (bachelor - study_income) + extra_cost
    annual_gain = 12 * (master - bachelor)
    return lost_income, lost_income / annual_gain if annual_gain > 0 else None


if __name__ == '__main__':
    # Kjøres bare ved «python src/main.py load», ikke når app.py importerer funksjonene.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('load',))
    parser.parse_args()
    try:
        load()
    except (Exception, KeyboardInterrupt) as error:
        print(f'Avbrutt: {error}', file=sys.stderr)
        sys.exit(1)
