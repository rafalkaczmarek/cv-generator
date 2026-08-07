# CV Generator

Lokalna aplikacja, która na podstawie Twojego profilu i wymagań konkretnej oferty pracy generuje dopasowane CV w formacie DOCX. Wykorzystuje wieloagentowy pipeline (LangGraph + LLM) do analizy oferty, mapowania Twoich doświadczeń na wymagania i przepisania treści CV bez halucynacji.

## Funkcje

- Formularz profilu z importem z publicznego URL LinkedIn (dane schema.org ze strony profilu).
- Import danych z oficjalnego eksportu LinkedIn (archiwum ZIP lub pojedynczy plik CSV).
- Pobieranie i analiza oferty pracy z URL lub wklejonego tekstu.
- **Zakładka Oferty (PL)** — automatyczne pobieranie ofert z Just Join IT,
  No Fluff Jobs, Bulldogjob, pracuj.pl i The Protocol, dopasowanie do
  wczytanego profilu (score bez LLM), sortowanie po dacie publikacji,
  generowanie i ponowne pobieranie CV dla wybranej oferty; oferty
  wycofane z portali są automatycznie wyszarzane.
- Pipeline agentów: analiza oferty, gap analysis, dopasowanie treści, walidacja jakości.
- Human-in-the-loop: edycja w UI przed eksportem.
- Eksport do `.docx` z konfigurowalnego szablonu Word.
- Faza 2: integracja z Google Docs (kopiowanie szablonu + `replaceAllText` + eksport).

## Wymagania

- Python **3.11** lub nowszy
- Dostęp do modelu LLM: Google Gemini (darmowy klucz z Google AI Studio), OpenAI albo Anthropic
- Microsoft Word, LibreOffice albo Google Docs do edycji szablonu CV

## Instalacja

```bash
git clone <repo-url> cv-generator
cd cv-generator

python -m venv .venv
.venv\Scripts\activate     # Windows PowerShell
# source .venv/bin/activate # Linux/macOS

pip install -e .[dev]

copy .env.example .env     # Windows
# cp .env.example .env     # Linux/macOS
```

Uzupełnij `.env` danymi dostawcy LLM.

Domyślnie używany jest **Google Gemini** — ma darmowy tier (m.in. ~250 req/dzień
na `gemini-3.6-flash`) i nie wymaga karty. Ustaw:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<klucz z https://aistudio.google.com/apikey>
GEMINI_MODEL=gemini-3.6-flash
```

Klucz wygenerujesz w [Google AI Studio](https://aistudio.google.com/apikey)
(wymagane konto Google). Alternatywnie ustaw `LLM_PROVIDER=openai` lub
`LLM_PROVIDER=anthropic` i wypełnij odpowiedni klucz API.

## Uruchomienie

```bash
streamlit run src/cv_generator/ui/app.py
```

Aplikacja otworzy się w przeglądarce pod `http://localhost:8501`.

## Workflow

1. **Profil** — wypełnij formularz ręcznie, zaimportuj z URL LinkedIn lub z eksportu LinkedIn (patrz niżej).
2. **Oferty** *(opcjonalnie)* — pobierz oferty z polskich portali IT i wygeneruj CV od razu dla najlepiej dopasowanej.
3. **Oferta** — wklej URL oferty pracy lub jej treść (do jednorazowych analiz).
4. **Generuj** — pipeline pobiera, analizuje i przepisuje CV pod ofertę.
5. **Podgląd** — popraw treść w razie potrzeby.
6. **Pobierz DOCX** — gotowy plik trafia do `output/`.

### Zakładka Oferty (PL)

Wymaga wczytanego profilu. Kliknij **Odśwież oferty** — aplikacja pobiera
listy równolegle z Just Join IT, No Fluff Jobs, Bulldogjob, pracuj.pl i
The Protocol, zapisuje je w bazie, ocenia dopasowanie do profilu
(deterministycznie, bez LLM) i sortuje malejąco po dacie publikacji.

Dla każdej oferty widzisz portal, tytuł, firmę, datę, pasujące i
brakujące umiejętności oraz przycisk **Generuj CV**. Wygenerowane CV
jest zapamiętywane per para (profil, oferta) — kolejne wejście na
zakładkę pokaże przy tej ofercie przycisk **Pobierz CV**. Możesz
zregenerować CV w każdej chwili.

Oferty, które zniknęły z portalu przy ostatnim odświeżeniu, zostają na
liście i są wyszarzone (przełącznik „Pokaż nieaktywne”).

Konfiguracja progu w `.env` (domyślnie `40`):

```env
MIN_BOARD_MATCH_SCORE=40
```

## Struktura

```
cv-generator/
├── src/cv_generator/
│   ├── agents/        # węzły LangGraph (job_analyzer, gap_analyzer, tailor, validator)
│   ├── graph/         # definicja grafu i stanu
│   ├── models/        # schematy Pydantic
│   ├── services/      # job_fetcher, docx_generator, storage, linkedin_import, linkedin_url_import, google_docs
│   ├── ui/            # Streamlit
│   └── cli.py
├── templates/         # szablony Word
├── tests/
├── data/              # SQLite + cache (ignored)
├── output/            # wygenerowane CV (ignored)
└── pyproject.toml
```

## Import z LinkedIn

### Z publicznego URL profilu

W zakładce **Profil** rozwiń **„Importuj z URL profilu LinkedIn”**, wklej adres
(`https://www.linkedin.com/in/...`) i kliknij **Pobierz dane z URL**.

Aplikacja odczytuje publiczne dane strukturalne (schema.org JSON-LD) z głównej
strony profilu i **uzupełnia brakujące pola** formularza — istniejące dane nie
są nadpisywane. Doświadczenie zawodowe pobierane jest z podstrony projektów
(`/details/projects/`), ponieważ główny profil często maskuje historię
zatrudnienia gwiazdkami dla niezalogowanych użytkowników.

### Z oficjalnego eksportu (ZIP/CSV)

LinkedIn pozwala pobrać kopię Twoich danych jako archiwum CSV.

1. Na LinkedIn wejdź w **Ustawienia → Prywatność danych → Pobierz kopię swoich danych**.
2. Zaznacz dane profilu (lub całość) i pobierz przygotowane archiwum ZIP.
3. W aplikacji, w zakładce **Profil**, rozwiń **„Importuj z eksportu LinkedIn”** i wgraj archiwum ZIP
   (możesz też wgrać pojedynczy plik, np. `Positions.csv`).
4. Formularz wypełni się automatycznie — przejrzyj, uzupełnij brakujące pola i zapisz profil.

Rozpoznawane pliki: `Profile.csv`, `Positions.csv`, `Projects.csv`, `Education.csv`,
`Skills.csv`, `Languages.csv`, `Email Addresses.csv`.
Brakujące pliki lub kolumny są pomijane, a daty w formatach LinkedIn (`Mar 2019`, `2019`)
są parsowane automatycznie. Projekty z `Projects.csv` trafiają do listy doświadczeń.

## Szablony CV

W zakładce **Eksport** wybierasz szablon Word. Wbudowane warianty (tworzone automatycznie w `templates/`):

| Plik | Opis |
|------|------|
| `cv_template.docx` | Klasyczny — ciemnoniebieskie nagłówki |
| `cv_modern.docx` | Nowoczesny — wyśrodkowany nagłówek, akcent teal |
| `cv_compact.docx` | Kompaktowy — mniejsza czcionka na jedną stronę |

Własny szablon: wrzuć plik `.docx` do `templates/` — pojawi się na liście. Składnia Jinja2 (przez `docxtpl`), kontekst `cv`:

- `{{ cv.full_name }}`, `{{ cv.headline }}`, `{{ cv.summary }}`
- `{%p for exp in cv.experiences %}` ... `{%p endfor %}`
- `{{ cv.skills | join(', ') }}`, `{{ cv.courses | join(', ') }}`, `{{ cv.languages | join(', ') }}`
- `{%p for line in cv.education_lines %}`

## Google Docs (opcjonalne)

```bash
pip install -e .[google]
```

1. Utwórz projekt w Google Cloud Console, włącz Drive API i Docs API.
2. Pobierz OAuth credentials → zapisz jako `secrets/google_credentials.json`.
3. Skopiuj szablon CV do Drive (placeholdery płaskie: `{{full_name}}`, `{{experiences}}`, …), ustaw `GOOGLE_DRIVE_TEMPLATE_ID` w `.env`.
4. W zakładce Eksport → „Google Docs” → eksportuj.
## Testy

Testy jednostkowe (domyślnie bez E2E):

```bash
pytest
```

Testy E2E (Playwright + lokalny serwer Streamlit):

```bash
pip install -e ".[dev,e2e]"
playwright install chromium
pytest -m e2e tests/e2e
```

## Licencja

MIT
