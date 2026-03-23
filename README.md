# Follow the Money 💰

**Political Intelligence Platform — Every dollar tells a story.**

Follow the Money is a Wikipedia-style political transparency platform where every person, company, bill, organization, and dollar amount is a clickable node that reveals deeper connections.

## Quick Start

```bash
# Clone and start
docker-compose up --build

# Access the app
open http://localhost:8060

# Seed data (auto-seeds on first run, or manually):
docker-compose exec backend python -m app.services.seed_service
```

The app will be available at **http://localhost:8060**.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14+ (TypeScript, App Router, Tailwind CSS) |
| Backend | FastAPI (Python 3.11+, async) |
| Database | PostgreSQL 16 (SQLAlchemy async + Alembic) |
| Proxy | Nginx (reverse proxy on port 8060) |
| Orchestration | Docker Compose |
| AI | Anthropic Claude API (stubbed, ready for integration) |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Browser    │────▶│    Nginx     │────▶│   Next.js    │
│              │     │   :8060      │     │   :3000      │
└─────────────┘     │              │     └──────────────┘
                    │  /api/* ─────│────▶┌──────────────┐
                    └──────────────┘     │   FastAPI     │
                                        │   :8000       │
                                        │       │       │
                                        │       ▼       │
                                        │  PostgreSQL   │
                                        │   :5432       │
                                        └──────────────┘
```

- All traffic enters through Nginx on port 8060
- `/api/*` routes proxy to FastAPI backend (strips `/api/` prefix)
- All other routes proxy to Next.js frontend
- Backend auto-runs Alembic migrations on startup
- Database auto-seeds with demo data (John Fetterman) on first run

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/entities/{slug}` | Entity profile + metadata |
| GET | `/api/entities/{slug}/connections` | Entity relationships (paginated) |
| GET | `/api/entities/{slug}/briefing` | AI-generated briefing |
| GET | `/api/search?q=...&type=...` | Search entities |
| GET | `/api/graph/{slug}?depth=2` | Graph visualization data |
| POST | `/api/admin/seed` | Re-seed demo data |

## Data Sources (Planned)

| Source | Data | Status |
|--------|------|--------|
| Congress.gov API | Member profiles, bills, votes | Mock data ready |
| FEC API | Campaign finance, donors | Mock data ready |
| Senate eFD | Financial disclosures | Mock data ready |
| OpenSecrets | Industry donations, lobbying | Planned |

## Adding Real API Keys

Copy `.env.example` to `.env` and fill in:

```bash
ANTHROPIC_API_KEY=sk-ant-...     # For AI briefings
CONGRESS_GOV_API_KEY=...          # Congress.gov API
FEC_API_KEY=...                   # FEC.gov API
OPENSECRETS_API_KEY=...           # OpenSecrets API
```

## Host Nginx Config

To serve via a custom domain on the host machine:

```bash
sudo ln -s $(pwd)/nginx/jerry-maguire.site.conf /etc/nginx/sites-enabled/jerry-maguire
sudo nginx -t && sudo systemctl reload nginx
```

Then access via `http://jerry.localhost` or add `followthemoney.local` to `/etc/hosts`.

## Development

```bash
# Rebuild after changes
docker-compose up --build

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Database shell
docker-compose exec db psql -U jerry followthemoney

# Re-seed data
docker-compose exec backend python -m app.services.seed_service
```

## Project Structure

```
jerry-maguire/
├── backend/           # FastAPI application
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routers/
│   │   ├── services/
│   │   └── seed/
│   ├── alembic/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/          # Next.js application
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── Dockerfile
│   └── package.json
├── nginx/
│   ├── nginx.conf
│   └── jerry-maguire.site.conf
├── docker-compose.yml
├── .env.example
└── README.md
```
