# Full datatest — 10. oktober 2026

Testen fant konkrete feil i kvalitetskontrollen og store hull i datadekningen.
De strukturelle kontrollene bestod; datagrunnlaget er ikke godkjent som komplett
eller som grunnlag for en påstand om netto meravkastning.

## Omfang og metode

Leste alle rader i 61 markeds-, forsknings- og driftstabeller i produksjon.
Inventartellingen inneholdt 198 518 rader. Dette inkluderer 148 465 resultatposter
fra bakgrunnsskanninger; tallet er ikke antall handler eller uavhengige signaler.
Kontrollene ble kjørt 10. oktober fra ca. 00:27 Oslo (9. oktober 22:27 UTC).
Separate lesetransaksjoner gir tidsavgrensede observasjoner, ikke ett atomisk
øyeblikksbilde mens bakgrunnsjobbene fortsetter å skrive.

Kontrollerte datatyper, tidsstempler, manglende felt, koblinger, regnestykker,
versjonsinnhold, kilde- og identitetsdekning. Personlige beholdninger fikk bare
en aggregert gyldighetskontroll. Ingen kontosaldoer, nøkler, abonnementer eller
sikkerhetslogger inngår i det lagrede resultatet. Ingen produksjonsrader ble
rettet, slettet eller fylt ut av testen.

Dette er en full gjennomgang av de angitte lagrede tabellene, ikke en ny kontroll
av hvert selskaps tall mot alle originale rapporter. Live kurser og kalenderdata
som bare hentes ved forespørsel kan ikke godkjennes fra lagrede tabeller.
Detaljer og eksakte felt/tellinger ligger i JSON-filen med samme navn.

## Resultater

| Kontroll | Funn |
| --- | --- |
| 82 tidsstempelfelt | Ingen ugyldige/tidssoneløse eller framtidige utfylte verdier |
| 29 datofelt | Ingen ugyldige/framtidige utfylte datoer |
| 24 JSON-felt | Ingen ugyldig JSON |
| 116 desimaltallfelt | Ingen NaN eller uendelige verdier; manglende verdier er registrert separat |
| 23 tabellkoblinger | Ingen foreldreløse poster |
| 33 437 scorer | Alle totaler og komponenter innenfor sine intervaller |
| 3 122 avkastningsutfall | Kursregnestykkene stemmer innen 0,001 prosentpoeng |
| 1 378 historikkversjoner | Sammenhengende revisjoner; innhold stemmer med lagret signatur når innsamlingsklokker utelates |
| Siste skanning | 26 av 26 forventede aksjer hadde et lagret snapshot |
| Finanspiloter | HYPRO, HDLY og INIFY: 12 regnskapsgrupper og 30 sammenligninger består datakontrakten |

Signaturkontrollen sammenligner lagret innhold. Den er ikke en ekstern signatur
eller en garanti mot endring av både innhold og signatur. Pilotkontrollen leser
de versjonerte forskningsdataene; originalrapportene ble ikke lest på nytt her.
Avkastningskontrollen bekrefter aritmetikk, ikke inngangspris, utbyttejustering,
kostnader eller sammenfallende faktiske indeksdatoer.

## Reelle datagap

- **Selskapsprofiler:** 186 lagrede profiler; 63 partial, 76 stale og 47 unavailable.
  74 har en beskrivelse, som også kan være registrert virksomhetsaktivitet.
  12 har lagrede finansielle verdier; bare 8 har verifisert leverandøridentitet,
  og alle disse finansielle feltene er markert gamle. 20 verdier i fire eldre
  profiler mangler feltkilde og identitetsbekreftelse og skjules allerede av
  leselaget. De tre manuelt gjennomgåtte finanspilotene er separate.
- **Kurslager:** 212 av 213 historiske snapshots mangler handelstidspunkt.
  Blant de 26 aktive aksjene har 24 et lagret kurssnapshot og bare én et
  handelstidspunkt. Dette sier ikke at 25 live kurser er feil; live forespørsler
  blir ikke alltid lagret. Hentetid må ikke brukes som erstatning for handelstid.
- **Finansiering:** 293 dokumenter, alle med jobboppføring. 269 har
  unsupported_document og 24 partial. Ingen er her godkjent som komplett uttrekk
  av vilkår. Alle 740 lagrede NewsWeb-dagsvinduer er partial; de beviser ikke
  komplett emisjonshistorikk eller fravær av finansieringsrisiko.
- **Innsidere:** 235 poster har kildelenke og handelsdato; 114 mangler
  transaksjonsverdi, 102 mangler pris og 32 mangler antall. Kildelenke alene er
  ikke kontroll av det underliggende dokumentets innhold.
- **Historiske skanninger:** fire eldre kjøringer står fortsatt som RUNNING uten
  sluttid (senest 25. september). Den siste kjøringen er fullført med 26/26.
  Historikken er bevart; de fire gamle postene er ikke bekreftet aktive jobber.
- **Resultater:** ti gamle Opportunity-hendelser og 29 horisontutfall med
  indekspar finnes. Den nye serien har null signaler og null innganger.
  Verifiserte åpninger, selskapshendelser, indeksobservasjoner, kostnadspolicy
  og samlet porteføljeregnskap mangler fortsatt for nettoresultater.

Tomme eldre tabeller for blant annet fundamentals, insider_trades og short_positions
må ikke forveksles med feil i dagens direkte leverandørforespørsler. Vi har heller
ikke utledet nyhetsferskhet fra den eldre, valgfrie feed-cachen.

## Kontroll mot børsdata og identitetsfeil

Den tidligere hentede Euronext-prøven fra 9. oktober inneholder 115 364 handler
og 283 instrument-ID-er. Alle 283 består ISIN-format og kontrollsiffer. Dette
sertifiserer ikke justering, åpning eller fullstendig handelsdekning.

Det historiske noteringsregisteret har 102 rader. Én oppgir NORSE med
`NO001288525` (elleve tegn). Samme feil finnes på Euronexts historiske
presentasjon av noteringen 28. april 2023. En nyere utstedermelding og
instrumentoversikten oppgir `NO0012885252`. Vi bevarer kildeobservasjonen og
avviser den ugyldige verdien; vi fyller ikke inn et antatt kontrollsiffer eller
skriver om historisk identitet automatisk.

61 forskjellige identifikatorer fra noteringsregisteret finnes i handelsprøven;
222 av prøvens identifikatorer finnes ikke i dette registeret. Registeret dekker
historiske opptak, ikke alle nåværende instrumenter. En handelsdag dekker heller
ikke nødvendigvis illikvide eller suspenderte instrumenter. Tallene er derfor
ikke en dekningsprosent for hele børsen.

## Rettet i kode

1. Beholdningskontrollen brukte den ikke-eksisterende kolonnen purchase_price
   og rapporterte spørringsfeilen som godkjent. Den bruker nå price_nok og
   kontrollerer også manglende/ikke-endelige verdier. Utilgjengelig kontroll
   gir varsel, aldri grønt resultat.
2. Framtidige tidsstempler ble avrundet til alder null, og tidssoneløse verdier
   fikk antatt UTC. Begge gir nå ukjent alder. En fersk scoreberegning brukes
   heller ikke som dokumentasjon på regnskapenes publiseringsdato.
3. Valgfrie SQL-feil tilbakestiller lesetransaksjonen slik at én feil ikke
   ødelegger resten av kontrollene i PostgreSQL.
4. Kursdekning og handelstid kontrolleres per aktiv aksje. Den nyeste kursraden
   for ett selskap kan ikke lenger skjule hull for resten av utvalget.
5. Kvalitetsstatus viser konkret regnskapsdekning og ISIN-avvik. Parser og
   leselag bevarer rapportert ISIN, men eksponerer ugyldige verdier som
   isin=null og isin_status=invalid. Selskapskobling krever kontrollsiffer.
   Formatgodkjenning kalles format_valid og er ikke identitetssertifisering.

Frosne scoremodeller, vekter, terskler, posisjonsstørrelser og varsler er uendret.
Ingen nye leverandørkall, cronjobber, handler eller tilgangsendringer er lagt til.

## Validering og videre arbeid

990 backendtester og 78 frontend/Worker-tester bestod lokalt. Nye tester dekker
faktisk beholdningsskjema, avbrutt lesetransaksjon, manglende tabell, framtidige
klokker, manglende kurs per aksje, gamle/ubekreftede regnskapstall og bevaring av
ugyldig kildeidentitet uten duplisering eller automatisk retting.

Neste datakrav er en kilde med dokumentert instrument-/sesjonsidentitet og
åpningspris, bedre originale regnskaps- og finansieringsdokumenter, samt
verifiserte selskapshendelser. Fysisk iPhone-test og koordinert nøkkelrotasjon
inngikk ikke i denne datatesten.

Kilder:
- https://live.euronext.com/en/ipo-showcase/norse-atlantic-0
- https://live.euronext.com/en/node/12896720
- https://live.euronext.com/nl/product/equities/no0012885252-xoas
- https://anna-web.org/identifiers/
- https://marketdata.euronext.com/data-reporting-service/trades-file
- https://www.postgresql.org/docs/18/functions-info.html
