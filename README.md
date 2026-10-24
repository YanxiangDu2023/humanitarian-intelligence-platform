# Humanitarian Intelligence Platform

An evidence-first data product for comparing public country indicators and, in later
phases, grounding AI-generated humanitarian briefs in structured data and cited reports.

This is a portfolio project inspired by UNICEF innovation and data-product workflows. It
uses public data only and is not an official UNICEF product.

## Phase 1 scope

- A 17-country comparison cohort selected from countries with UNICEF learning-indicator
  observations and usable World Bank context data
- Initial sources: UNICEF SDMX API and World Bank Indicators API
- Three persistent PostgreSQL layers: `bronze`, `silver`, and `gold`
- Idempotent loads, pipeline-run metadata, raw payload retention, and quality checks
- A first Gold table for latest values and changes over time

The first indicator set combines UNICEF learning poverty, learning deprivation, and
schooling deprivation with World Bank primary and secondary enrolment, education spending,
internet use, and population. The list is based on verified API coverage for the cohort;
it is not a claim that these variables alone measure child wellbeing or innovation maturity.

Countries: Argentina, Australia, Brazil, Germany, France, United Kingdom, Italy, Japan,
South Korea, Mexico, Russia, Saudi Arabia, Turkiye, United States, South Africa, Jordan,
and Kenya.

See `docs/phase1_indicator_catalog.md` for the decision and coverage details.

Before changing the production data model, profile the real source coverage:

```bash
humanitarian-probe
```

This writes `reports/data_source_feasibility.md`. Years without observations are reported
as coverage gaps, not automatically treated as errors, because survey-based UNICEF series
are not necessarily annual.

## Architecture

The repository is organized as a small monorepo:

```text
humanitarian-intelligence-platform/
├── backend/   Python, FastAPI, ETL, SQL, and backend tests
├── frontend/  React dashboard
├── docs/      Architecture and deployment notes
└── docker-compose.yml
```

```text
World Bank API ─┐
                ├─> bronze.api_responses            source payloads
UNICEF SDMX API ┘              |
                               v
                    silver.country_indicators       typed, deduplicated data
                               |
                               v
                    gold.country_indicator_summary  latest/change metrics
                               |
                               v
                    gold.ai_country_briefs          versioned AI reports
```

`meta.pipeline_runs` records status, timestamps, row counts, and errors for each execution.

## Run locally

Prerequisites: Python 3.11+ and Docker.

```bash
docker compose up -d
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
humanitarian-etl init-db
humanitarian-etl world-bank
humanitarian-etl unicef
humanitarian-etl validate
```

Inspect the output:

```sql
SELECT *
FROM gold.country_comparison
ORDER BY indicator_code, country_iso3;
```

Start the read-only API:

```bash
humanitarian-api
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation. The initial
endpoints are:

- `GET /health`
- `GET /api/v1/countries`
- `GET /api/v1/indicators`
- `GET /api/v1/comparisons/{indicator_code}`
- `GET /api/v1/trends/{indicator_code}`
- `GET /api/v1/countries/{country_iso3}/indicators`
- `GET /api/v1/analysis/countries/{country_iso3}`
- `POST /api/v1/ai/country-brief`
- `GET /api/v1/ai/country-brief/{country_iso3}`

The analysis endpoint prepares a deterministic, model-ready evidence package containing
latest values, historical changes, available years, cohort statistics, and explicit data
gaps. It does not call an AI model or incur model API costs.

The POST country-brief endpoint sends that closed evidence package to the configured OpenAI
model, validates the response, and saves the structured brief in PostgreSQL. The GET endpoint
returns the latest saved brief without calling the model, so refreshing the dashboard does not
incur another API charge. AI-written prose is not allowed to contain numbers; verified values,
years, ranks, and sources are attached by the application after generation. Briefs use a
multi-sentence executive summary and evidence-supported findings across the available education,
learning, connectivity, spending, and population domains.

Start the React dashboard in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. On networks that inspect HTTPS traffic, run the install as
`NODE_OPTIONS=--use-system-ca npm install` so Node uses the macOS system trust store.

## Deploy to Azure

The production layout uses Azure Static Web Apps for the React dashboard, Azure Container
Apps for the FastAPI service, and Azure Database for PostgreSQL Flexible Server. The backend
container listens on `0.0.0.0:8000`; database credentials, the OpenAI key, and allowed frontend
origins are supplied as Azure environment variables and secrets rather than committed files.

See `docs/azure-deployment.md` for the deployment sequence and cost controls.

The dashboard shows the latest cross-country comparison and a historical trend chart.
The trend chart supports one to three countries, a selectable year range, and preserves
missing observations as gaps instead of silently converting them to zero.

Run checks:

```bash
cd backend
python -m pytest
ruff check .
```

## Roadmap

1. Add PDF ingestion with document provenance and chunk-level citations.
2. Add cross-source interpretations that preserve indicator limitations.
3. Add grounded question answering and deterministic validation of numeric claims.
4. Add scheduling, observability, CI/CD, and cloud deployment.

