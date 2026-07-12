from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.refresh import run_full_refresh, watchdog_tick
from app.routers import checklist, data_health, health, refresh, tips, tipster_tips, track_record

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Every 120 minutes: full pipeline (all scrapers, tipster scrapers, real-result
    # settlement for every tip vertical, then tip/multi regeneration) — one cadence
    # instead of a once-nightly run + a separate tipster-only cron, since a 2-hourly
    # tick already lands within 2 hours of any tipster site's posting time regardless
    # of exact time of day. Real runs take ~12-16 min, well inside the window; each
    # scraper is incremental (checks what's already fetched), so extra runs are cheap.
    scheduler.add_job(run_full_refresh, "interval", minutes=120, id="full_refresh_interval")
    # Runs independently of any user request so a hung refresh self-heals even if
    # nobody opens the app to trigger the check.
    scheduler.add_job(watchdog_tick, "interval", minutes=5, id="refresh_watchdog")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Betting Research App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(tips.router)
app.include_router(track_record.router)
app.include_router(checklist.router)
app.include_router(data_health.router)
app.include_router(refresh.router)
app.include_router(tipster_tips.router)
