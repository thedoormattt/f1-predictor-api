# F1 Predictions League — API

FastAPI backend for the F1 Predictions League webapp.

## Stack
- **FastAPI** — API framework
- **Supabase** — PostgreSQL database + auth (service role client)
- **OpenF1** — race result data
- **Render** — hosting

---

## Local setup

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Copy env file and fill in your Supabase credentials
cp .env .env

# 3. Run locally
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs

---

## Project structure

```
app/
  main.py              # FastAPI app, CORS, router registration
  config.py            # Settings (reads from .env)
  database.py          # Supabase client singleton
  models.py            # Pydantic schemas for all entities
  routers/
    races.py            # GET /races, GET /races/{id}
    predictions.py      # GET + POST /predictions
    results.py          # GET /results, admin fetch + score endpoints
    leaderboard.py      # GET /leaderboard, GET /leaderboard/cumulative
    reference.py        # GET /reference/drivers, /reference/teams
  services/
    scoring.py          # Core scoring engine (mirrors spreadsheet logic)
    openf1.py           # OpenF1 API integration
tests/
  test_scoring.py       # Scoring unit tests
render.yaml             # Render deployment config
```

---

## Endpoints

### Public
| Method | Path | Description |
|--------|------|-------------|
| GET | `/races` | All races in calendar order |
| GET | `/races/{id}` | Single race |
| GET | `/predictions/race/{race_id}` | All predictions for a race (visible after race starts) |
| GET | `/predictions/player/{player_id}` | All predictions for a player |
| POST | `/predictions` | Submit/update a prediction (locked at race start) |
| GET | `/results/{race_id}` | Race result |
| GET | `/results/{race_id}/scores` | All player scores for a race |
| GET | `/leaderboard` | Current standings |
| GET | `/leaderboard/cumulative` | Cumulative scores per race (for chart) |
| GET | `/reference/drivers` | Driver list for prediction form |
| GET | `/reference/teams` | Team list for pitstop prediction |

### Admin (requires `X-Admin-Secret` header)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/results/admin/{race_id}/fetch-openf1` | Fetch result from OpenF1 and save |
| PATCH | `/results/admin/{race_id}/dotd` | Set Driver of the Day manually |
| POST | `/results/admin/{race_id}/score` | Run scoring for all players |

---

## After each race — workflow

```
1. POST /results/admin/{race_id}/fetch-openf1   # pulls data from OpenF1
2. PATCH /results/admin/{race_id}/dotd?dotd=BOT # add DotD manually
3. POST /results/admin/{race_id}/score           # calculates all scores
```

Scoring is idempotent — safe to re-run if you correct the result.

---

## Running tests

```bash
pytest tests/
```

---

## Deploying to Render

1. Push repo to GitHub
2. Create a new **Web Service** on Render, connect your repo
3. Render detects `render.yaml` automatically
4. Add environment variables in Render dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `SECRET_KEY` (used to protect admin endpoints)
5. Deploy — Render builds and starts automatically on every push
