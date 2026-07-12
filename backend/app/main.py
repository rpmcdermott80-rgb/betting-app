from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.refresh import run_full_refresh, run_tipster_refresh, watchdog_tick
from app.routers import checklist, data_health, health, refresh, tips, tipster_tips, track_record

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 18:00 UTC ≈ 4am AEST (UTC+10) — a rough approximation good enough for a
    # personal AU-only tool, same as the timezone handling in the scrapers.
    scheduler.add_job(run_full_refresh, "cron", hour=18, minute=0, id="nightly_refresh")
    # 00:45 UTC ≈ 10:45am AEST/QLD — after freehorseracingtipsaustralia.com.au's
    # stated latest posting times for the morning's meetings; the main nightly run
    # above is too early in the day to ever catch same-day tipster picks.
    scheduler.add_job(run_tipster_refresh, "cron", hour=0, minute=45, id="tipster_refresh")
    # Runs independently of any user request so a hung refresh (manual or nightly)
    # self-heals even if nobody opens the app to trigger the check.
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
