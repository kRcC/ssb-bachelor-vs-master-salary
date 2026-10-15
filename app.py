"""Kjør med det lokale Python-miljøet utenfor Google Drive; se README.md."""

import csv
from io import StringIO

import streamlit as st
import altair as alt

from src.main import MEASURES, compare_fields, fetch_records, scenario

# 1. Sidetittel og forklaring av casen
st.set_page_config(page_title='Lønner det seg å ta en master?', page_icon='🎓', layout='wide')
st.caption('SSB-ANALYSE · UTDANNING OG LØNN')
st.title('Lønner det seg å ta en master?')
st.write(
    'Du er ferdig med bachelor: begynne å jobbe nå, eller studere videre? '
    'Velg fagområde og se hvordan ekstra studieår påvirker samlet inntekt.'
)
st.caption(
    '1. Velg fagområde → 2. Juster studieplanen → 3. Se når masterløpet tar igjen bachelorløpet.'
)
st.info(
    '«Bachelor» betyr her SSBs høyere utdanning på 1–4 år. «Master» betyr over 4 år, '
    'inkludert doktorgrad. Tallene gjelder heltidsansatte 0–2 år etter fullført utdanning.'
)

# 2. Hent data fra MySQL
st.sidebar.header('Koble til databasen')
# Streamlit kjører filen på nytt ved endrede valg; passordfeltets key bevarer verdien i økten.
password = st.sidebar.text_input('MySQL-passord', type='password', key='mysql_password')
st.sidebar.button('Hent fra databasen på nytt')
if not password:
    st.info('Oppgi MySQL-passordet i sidepanelet.')
    st.stop()
try:
    records = fetch_records(password)
except Exception:
    st.error(
        'Kan ikke hente lønnstall. Kontroller SSH-tunnelen, MySQL-passordet og at '
        'education_salaries er opprettet, gitt tilgang og importert. Se README, «Første oppsett».'
    )
    st.stop()

# 3. Brukerens valg i sidepanelet
st.sidebar.header('1. Velg lønnsdata fra SSB')
# Filtrene lager en sammenligning fra MySQL-radene, uten å endre data i databasen.
year = st.sidebar.selectbox(
    'Hvilket år vil du bruke lønnstall fra?',
    sorted({r[0] for r in records}, reverse=True),
    help='Begge utdanningsnivåene bruker tall fra samme år. Dette er ikke året du starter studiene.',
)
measure = st.sidebar.selectbox(
    'Hvilken lønn vil du sammenligne?',
    list(MEASURES),
    format_func=lambda value: 'Vanlig lønn (median)' if value == 'median' else 'Gjennomsnittslønn',
    help='Median: halvparten av arbeidsforholdene har lavere lønn og halvparten høyere. '
    'Gjennomsnitt: alle lønningene lagt sammen og delt på antallet.',
)
st.sidebar.caption('Usikker? Behold siste år og «Vanlig lønn (median)».')
with st.sidebar.expander('Flere valg: størrelsen på datagrunnlaget'):
    min_jobs = st.number_input(
        'Minst så mange jobber i hver gruppe',
        min_value=0,
        max_value=1_000_000,
        value=100,
        step=100,
        help='Antall arbeidsforhold, ikke nødvendigvis antall personer. '
        'Et fagområde vises bare hvis begge nivåer oppfyller grensen.',
    )
    st.caption(
        'Høyere grense fjerner små grupper. Dette endrer hvilke fagområder som vises, ikke lønnen deres.'
    )
rows = compare_fields(records, year, measure, min_jobs)
if not rows:
    st.warning(
        'Ingen utdanningsgrupper har begge lønnstall og oppfyller filteret. Prøv et annet år eller en lavere terskel.'
    )
    st.stop()
options = {row['Kode']: row['Fagfelt'] for row in rows}
# Vis navnet i menyen, men behold fagkoden som nøkkel når riktig rad velges.
selected = st.sidebar.selectbox(
    'Hvilket fagområde vil du undersøke?',
    sorted(options, key=lambda code: options[code]),
    format_func=lambda code: options[code],
    help='Sammenlign bachelor og master innen samme fagområde. Bare områder med tall for begge vises.',
)
row = next(r for r in rows if r['Kode'] == selected)
bachelor, master = row['Bachelor (kr/mnd)'], row['Master (kr/mnd)']

st.sidebar.header('2. Hvordan vil du studere?')
# Brukerens antakelser sendes til scenario; SSB-lønningene holdes uendret.
st.sidebar.caption('Disse valgene er dine antakelser. De endrer beregningen, ikke SSBs lønnstall.')
study_years = st.sidebar.number_input(
    'Hvor mange ekstra år vil du studere?',
    min_value=1,
    max_value=6,
    value=2,
    help='År etter bachelor før du begynner å jobbe med masterlønn. To år er standard i dette scenarioet.',
)
study_income = st.sidebar.number_input(
    'Hvor mye vil du tjene på jobb under studiene? (kr/mnd)',
    min_value=0,
    max_value=int(bachelor),
    value=0,
    step=1000,
    help='Brutto lønn før skatt, for eksempel fra deltidsjobb. Bruk et gjennomsnitt per måned '
    'over hele studieperioden. Studielån og stipend regnes ikke med.',
)
st.sidebar.caption(
    'Eksempel: 10 000 kr/mnd fra deltidsjobb gir masterløpet mindre tapt arbeidsinntekt.'
)
extra_cost = st.sidebar.number_input(
    'Hva vil studiene koste ekstra til sammen? (kr)',
    min_value=0,
    max_value=10_000_000,
    value=0,
    step=10_000,
    help='Ett totalbeløp for hele studieperioden, for eksempel studieavgift og ekstra bøker. '
    'Ikke ta med vanlige levekostnader du også ville hatt i jobb, eller tapt lønn; den beregnes automatisk.',
)
st.sidebar.caption('Sett 0 hvis du ikke vil regne med ekstra studiekostnader.')
st.sidebar.header('3. Hvor langt fram vil du se?')
horizon = st.sidebar.slider(
    'Antall år fra du er ferdig med bachelor',
    min_value=5,
    max_value=40,
    value=20,
    help='Endrer lengden på grafen og sluttbeløpene. Endrer ikke når inntektsløpene blir like.',
)

# 4. Beregn scenarioet før resultatene vises
lost_income, break_even = scenario(bachelor, master, study_years, study_income, extra_cost)
catch_up_year = study_years + break_even if break_even is not None else None

# ponytail: sammenlign to faste inntektsløp fra samme starttidspunkt.
# Én rad per år: min teller studieår, max teller arbeidsår etter studiene.
points = [
    {
        'År fra valget': t,
        'Bachelor': t * 12 * bachelor,
        'Master': min(t, study_years) * 12 * study_income
        + max(0, t - study_years) * 12 * master
        - extra_cost,
    }
    for t in range(horizon + 1)
]
bachelor_total = points[-1]['Bachelor']
master_total = points[-1]['Master']
difference = master_total - bachelor_total

# 5. Oppsummer månedslønn og innhentingstid
st.subheader(row['Fagfelt'])
st.caption(f'{MEASURES[measure]} · {year} · heltidsansatte · 0–2 år etter fullført utdanning')
columns = st.columns(3)
columns[0].metric('Bachelor – månedslønn', f'{bachelor:,.0f} kr'.replace(',', ' '))
columns[1].metric('Master – månedslønn', f'{master:,.0f} kr'.replace(',', ' '))
columns[2].metric('Forskjell per måned', f'{master - bachelor:+,.0f} kr'.replace(',', ' '))
st.caption(
    f'Arbeidsforhold: bachelor {row["Arbeidsforhold bachelor"]:,}, master {row["Arbeidsforhold master"]:,}.'
)
st.write(
    f'I studieperioden tjener masterløpet **{study_years * 12 * (bachelor - study_income):,.0f} kr mindre** '
    f'på jobb enn bachelorløpet. Med **{extra_cost:,.0f} kr** i ekstra studiekostnader '
    f'er det totalt **{lost_income:,.0f} kr** å ta igjen.'
)
st.caption('Tapt arbeidsinntekt er lønn du går glipp av, ikke en regning du må betale.')
if break_even is None:
    st.warning(
        'Mastergruppen har ikke høyere lønn i dette utvalget. Scenarioet henter derfor ikke inn studiekostnaden gjennom en lønnsgevinst.'
    )
else:
    st.success(
        f'Masterløpet tar igjen bachelorløpet etter {study_years + break_even:.1f} år fra bachelor er fullført. '
        f'Det er {study_years} studieår og deretter {break_even:.1f} år i jobb.'
    )
st.caption(
    'Dette er et regnescenario med faste brutto lønninger. Skatt, lønnsvekst, renter, '
    'avkastning og risiko for arbeidsledighet er ikke beregnet.'
)

# 6. Vis detaljer i tre faner
simulation, comparison, source = st.tabs(
    ['Ditt valg: inntekt over tid', 'Lønnsforskjeller mellom fag', 'Se SSB-tallene']
)

with simulation:
    st.subheader('Akkumulert bruttoinntekt over tid: bachelor vs. master')
    st.write(
        'Akkumulert betyr alt du har tjent til sammen fram til et bestemt år. '
        'Bachelorløpet begynner i jobb med én gang. Masterløpet studerer først og begynner i jobb senere.'
    )
    totals = st.columns(3)
    totals[0].metric(f'Bachelor etter {horizon} år', f'kr {bachelor_total:,.0f}'.replace(',', ' '))
    totals[1].metric(f'Master etter {horizon} år', f'kr {master_total:,.0f}'.replace(',', ' '))
    totals[2].metric('Master minus bachelor', f'kr {difference:+,.0f}'.replace(',', ' '))
    if difference > 0:
        st.write(
            f'Etter {horizon} år har masterløpet **{difference:,.0f} kr mer** samlet i denne beregningen.'
        )
    elif difference < 0:
        st.write(
            f'Etter {horizon} år har bachelorløpet **{-difference:,.0f} kr mer** samlet i denne beregningen.'
        )
    else:
        st.write(f'Etter {horizon} år er samlet inntekt lik i begge løp.')
    # Inntektsgraf: én kurve per utdanning.
    # fold gjør Bachelor/Master-kolonnene til én beløpskolonne med utdanning som farge.
    chart = (
        alt.Chart(alt.Data(values=points))
        .transform_fold(['Bachelor', 'Master'], as_=['Utdanning', 'Inntekt'])
        .transform_calculate(Belop="'kr ' + replace(format(datum.Inntekt, ',.0f'), /,/g, ' ')")
        .mark_line(point=True)
        .encode(
            x=alt.X(
                'År fra valget:Q',
                title='År etter fullført bachelor',
                axis=alt.Axis(format='d', tickMinStep=1),
            ),
            y=alt.Y(
                'Inntekt:Q',
                title='Akkumulert bruttoinntekt (kr)',
                axis=alt.Axis(labelExpr="'kr ' + replace(format(datum.value, ',.0f'), /,/g, ' ')"),
            ),
            color=alt.Color(
                'Utdanning:N',
                scale=alt.Scale(domain=['Bachelor', 'Master'], range=['#236b54', '#bc5a22']),
            ),
            tooltip=[
                alt.Tooltip('Utdanning:N'),
                alt.Tooltip('År fra valget:Q', format='.0f'),
                alt.Tooltip('Belop:N', title='Akkumulert inntekt'),
            ],
        )
    )
    # Marker innhentingspunktet hvis det ligger innenfor valgt tidshorisont.
    if catch_up_year is not None and catch_up_year <= horizon:
        marker = alt.Chart(
            alt.Data(
                values=[
                    {
                        'År fra valget': catch_up_year,
                        'Inntekt': catch_up_year * 12 * bachelor,
                        'Merking': f'Master tar igjen bachelor: {catch_up_year:.1f} år',
                    }
                ]
            )
        ).encode(x=alt.X('År fra valget:Q', title='År etter fullført bachelor'))
        rule = marker.mark_rule(color='#666666', strokeDash=[5, 5])
        dot = marker.mark_point(color='#333333', filled=True, size=100).encode(
            y='Inntekt:Q',
            tooltip=[
                alt.Tooltip('Merking:N'),
                alt.Tooltip('Inntekt:Q', title='Beløp (kr)', format=',.0f'),
            ],
        )
        label = marker.mark_text(align='right', dx=-8, dy=-15).encode(
            y='Inntekt:Q', text='Merking:N'
        )
        chart = chart + rule + dot + label
    st.altair_chart(chart)
    if catch_up_year is not None and catch_up_year > horizon:
        st.info(
            f'Innhentingspunktet er ved {catch_up_year:.1f} år, utenfor grafen. '
            'Øk tidshorisonten for å se det dersom det er innenfor 40 år.'
        )
    st.caption(
        'Begge løp starter etter bachelor. Ekstra studiekostnader trekkes fra masterløpet ved start. '
        'Kurvene er beregnet; de viser ikke observert karriereutvikling.'
    )
    st.caption(
        'Alle beløp er i kroner. Masterløpet vises etter fratrekk av ekstra studiekostnader. '
        'Hold pekeren over grafen for å se beløpet ved et bestemt år.'
    )
    if catch_up_year is not None and catch_up_year <= horizon:
        st.caption(
            'Den stiplede linjen viser når masterløpet har tatt igjen lønnen du gikk glipp av under studiene, '
            'pluss ekstra studiekostnader.'
        )
    # CSV-eksport: forutsetninger og beregnede inntekter år for år.
    metadata = {
        'SSB-tabell': 14378,
        'Statistikkår': year,
        'Fagkode': selected,
        'Utdanningsgruppe': row['Fagfelt'],
        'Lønnsmål': MEASURES[measure],
        'Bachelorlønn (kr/mnd)': bachelor,
        'Masterlønn (kr/mnd)': master,
        'Ekstra studieår': study_years,
        'Studieinntekt (kr/mnd)': study_income,
        'Ekstra studiekostnader (kr)': extra_cost,
        'År til lik inntekt fra valget': catch_up_year,
        'Forutsetning': 'Faste brutto lønninger; uten skatt, lønnsvekst, renter og arbeidsledighet',
    }
    # ponytail: én flat CSV med forutsetninger og årstall; ingen lokal eksportfil.
    buffer = StringIO(newline='')
    # StringIO bygger CSV i minnet. Metadata gjentas per år så filen er én vanlig tabell.
    writer = csv.DictWriter(
        buffer,
        fieldnames=[*metadata, 'År fra valget', 'Bachelor (kr)', 'Master (kr)', 'Forskjell (kr)'],
        delimiter=';',
    )
    writer.writeheader()
    for point in points:
        exported = {
            **metadata,
            'År fra valget': point['År fra valget'],
            'Bachelor (kr)': point['Bachelor'],
            'Master (kr)': point['Master'],
            'Forskjell (kr)': point['Master'] - point['Bachelor'],
        }
        writer.writerow(
            {
                key: f'{value:.2f}'.replace('.', ',') if isinstance(value, float) else value
                for key, value in exported.items()
            }
        )
    # UTF-8 med BOM hjelper Excel å lese norske tegn; filen sendes til nettleseren.
    st.download_button(
        'Last ned beregningen til Excel (CSV)',
        data=buffer.getvalue().encode('utf-8-sig'),
        file_name=f'master_scenario_{selected}_{year}.csv',
        mime='text/csv',
        help='Laster ned dine valg, lønnstall og samlet inntekt år for år. CSV-filen kan åpnes i Excel.',
    )

with comparison:
    st.write(
        'Her sammenlignes forskjellen i månedslønn mellom bachelor og master i hvert fagområde. '
        'Dine studieår og kostnader påvirker ikke denne listen. År, lønnsmål og datagrense fra sidepanelet gjelder.'
    )
    st.subheader('Størst forskjell i månedslønn – opptil 15 utdanningsgrupper')
    st.bar_chart(rows[:15], x='Fagfelt', y='Forskjell (kr/mnd)', horizontal=True, color='#236b54')
    st.dataframe(rows, hide_index=True)

with source:
    st.write(
        'Bare utdanningsgrupper med publisert lønn og antall arbeidsforhold for begge nivåer '
        'i samme år tas med. Manglende tall blir aldri behandlet som null lønn.'
    )
    st.dataframe(
        [
            {
                'År': r[0],
                'Kode': r[1],
                'Utdanningsgruppe': r[2],
                'Utdanningsnivå': (
                    'Bachelor (1–4 år)' if r[3] == '3' else 'Master (over 4 år, inkl. doktorgrad)'
                ),
                'Gjennomsnitt (kr/mnd)': r[4],
                'Median (kr/mnd)': r[5],
                'Arbeidsforhold': r[6],
            }
            for r in records
            if r[0] == year and r[1] == selected
        ],
        hide_index=True,
    )

# 7. Kilder og begrensninger
st.divider()
st.markdown(
    'Kilde: [SSB-tabell 14378](https://www.ssb.no/statbank/table/14378/). '
    '[SSBs forklaring av startlønn](https://www.ssb.no/arbeid-og-lonn/lonn-og-arbeidskraftkostnader/artikler/hvem-har-hoyest-startlonn).'
)
st.caption(
    'Gruppene kan ha ulik alder, arbeidserfaring og ulike jobber. Lønnsforskjellen viser ikke '
    'effekten av mastergraden alene, og beregningen avgjør ikke hvilket studievalg som passer deg.'
)
