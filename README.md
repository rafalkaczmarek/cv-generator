# CV Generator

Lokalna aplikacja, która na podstawie Twojego profilu i wymagań konkretnej oferty pracy generuje dopasowane CV w formacie DOCX. Wykorzystuje wieloagentowy pipeline (LangGraph + LLM) do analizy oferty, mapowania Twoich doświadczeń na wymagania i przepisania treści CV bez halucynacji.

## Funkcje

- Formularz profilu z importem z publicznego URL LinkedIn (dane schema.org ze strony profilu).
- Import danych z oficjalnego eksportu LinkedIn (archiwum ZIP lub pojedynczy plik CSV).
- Pobieranie i analiza oferty pracy z URL lub wklejonego tekstu.
- Pipeline agentów: analiza oferty, gap analysis, dopasowanie treści, walidacja jakości.
- Human-in-the-loop: edycja w UI przed eksportem.
- Eksport do `.docx` z konfigurowalnego szablonu Word.
- Faza 2: integracja z Google Docs (kopiowanie szablonu + `replaceAllText` + eksport).

## Wymagania

- Python **3.11** lub nowszy
- Dostęp do modelu LLM: GitHub Models (token GitHub z uprawnieniem `models:read`), OpenAI albo Anthropic
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

Domyślnie używany jest **GitHub Models** (kompatybilny z API OpenAI). Ustaw:

```env
LLM_PROVIDER=github
GITHUB_TOKEN=<twój_token_github_z_uprawnieniem_models:read>
GITHUB_MODEL=openai/gpt-4.1-mini
```

Token wygenerujesz w GitHub: **Settings → Developer settings → Personal access tokens**
(fine-grained), nadając uprawnienie **Models: read**. Alternatywnie ustaw
`LLM_PROVIDER=openai` lub `LLM_PROVIDER=anthropic` i wypełnij odpowiedni klucz API.

## Uruchomienie

```bash
streamlit run src/cv_generator/ui/app.py
```

Aplikacja otworzy się w przeglądarce pod `http://localhost:8501`.

## Workflow

1. **Profil** — wypełnij formularz ręcznie, zaimportuj z URL LinkedIn lub z eksportu LinkedIn (patrz niżej).
2. **Oferta** — wklej URL oferty pracy lub jej treść.
3. **Generuj** — pipeline pobiera, analizuje i przepisuje CV pod ofertę.
4. **Podgląd** — popraw treść w razie potrzeby.
5. **Pobierz DOCX** — gotowy plik trafia do `output/`.

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

Rozpoznawane pliki: `Profile.csv`, `Positions.csv`, `Education.csv`, `Skills.csv`,
`Languages.csv`, `Certifications.csv`, `Email Addresses.csv`. Brakujące pliki lub kolumny
są pomijane, a daty w formatach LinkedIn (`Mar 2019`, `2019`) są parsowane automatycznie.

## Szablon CV

Domyślny szablon znajduje się w `templates/cv_template.docx`. Używa składni Jinja2 (przez `docxtpl`):

- `{{ profile.full_name }}`
- `{{ profile.headline }}`
- `{%tr for exp in experiences %}` ... `{%tr endfor %}` (pętla wierszami)

Możesz podmienić szablon na swój własny — wystarczy zachować nazwy zmiennych.

## Google Docs (faza 2, opcjonalne)

```bash
pip install -e .[google]
```

1. Utwórz projekt w Google Cloud Console, włącz Drive API i Docs API.
2. Pobierz OAuth credentials → zapisz jako `secrets/google_credentials.json`.
3. Skopiuj szablon CV do swojego Drive, ustaw `GOOGLE_DRIVE_TEMPLATE_ID` w `.env`.

## Testy

```bash
pytest
```

## Licencja

MIT
