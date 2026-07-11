"""Registry of known data sources, seeded into the `sources` table on startup.

Every entry here is either a primary-data source we scrape for facts (game logs,
results, odds) or a discovery target that failed previously and is recorded honestly
as such.

Tipster/tip-aggregator sites are a separate category: they are NEVER used to derive
our own `tips`/Track Record (that stays real-data-only). A small number are enabled
specifically to feed the separate Tipster Tips feature (`TipsterPick`, not `Tip`) —
see the "Tipster sites" section below. Everything else in that section is disabled,
kept for reference only.
"""

SOURCE_REGISTRY = [
    # --- AFL/NRL player props: confirmed working, primary data ---
    {
        "vertical": "player_prop",
        "name": "legz.com.au",
        "base_url": "https://www.legz.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt explicitly disallows ClaudeBot (and other "
        "AI crawlers) with Content-Signal ai-train=no. Replaced by afltables.com + "
        "rugbyleagueproject.org below. Kept disabled for the record, not as a source.",
    },
    {
        "vertical": "player_prop",
        "name": "afltables.com",
        "base_url": "https://afltables.com",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed working 2026-07-10. Plain server-rendered HTML, no robots.txt "
        "(no restrictions), no AI-crawler mentions. Real per-game player logs at "
        "/afl/stats/players/<Initial>/<Name>.html — anchored per-season tables with "
        "disposals/goals/etc per game, linked to game IDs. AFL reference scraper.",
    },
    {
        "vertical": "player_prop",
        "name": "rugbyleagueproject.org",
        "base_url": "https://www.rugbyleagueproject.org",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed working 2026-07-10, scraper built + real data verified. "
        "Plain HTML, robots.txt only blocks /matches/Custom and query strings — no "
        "AI-crawler restriction. Per-game logs at /players/<slug>/games.html with a "
        "'Scoring' column (e.g. 'T: 1, G: 4/5') giving tries per game. NRL reference "
        "scraper. Currently degraded/blocked (connection refused) after a discovery "
        "burst during testing — likely temporary, retry later with the request "
        "delays already added rather than immediately re-hammering it.",
    },
    {
        "vertical": "player_prop",
        "name": "nrl.com",
        "base_url": "https://www.nrl.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-10 as a backup NRL source. Clean robots.txt, no "
        "restrictions. Player bio pages (/players/<comp>/<team>/<slug>/) are real, "
        "server-rendered HTML with a 'Career By Season' table — but only SEASON "
        "aggregates (e.g. '2026: 12 games, 4 tries'), no per-match breakdown. Not "
        "useful for prop hit-rate analysis, which needs per-game data. Disabled — "
        "kept as a documented dead end, not a live source.",
    },
    {
        "vertical": "player_prop",
        "name": "api.squiggle.com.au",
        "base_url": "https://api.squiggle.com.au",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed working 2026-07-10. Official public JSON API for AFL "
        "fixtures/scores/ladder — good for events/results backbone, but explicitly "
        "does not include individual player stats (their own docs point to afltables-"
        "style sources for that). Use for events, not player_game_logs.",
    },
    {
        "vertical": "player_prop",
        "name": "ESPN",
        "base_url": "https://www.espn.com.au",
        "scrape_method": "http",
        "enabled": True,
        "notes": "AFL/NRL scores and results for building the events/results tables.",
    },
    # --- Horse racing: discovery completed 2026-07-10, see notes per source ---
    {
        "vertical": "horse_racing",
        "name": "race.com.au",
        "base_url": "https://www.race.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DEAD DOMAIN. No longer a racing site at all — now just a domain-parking "
        "for-sale page (loads assets.abovedomains.com forsale.min.js). The HTTPS cert "
        "mismatch that looked like a block was just this. Not a source anymore.",
    },
    {
        "vertical": "horse_racing",
        "name": "Racing Australia racebooks",
        "base_url": "https://www.racingaustralia.horse",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt has a blanket 'User-agent: * / Disallow: /' "
        "— a general no-scraping policy for everyone except Google/MSN/Yahoo's own "
        "indexing bots, not just AI crawlers. Disabled out of respect for that.",
    },
    {
        "vertical": "horse_racing",
        "name": "breednet",
        "base_url": "https://www.breednet.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same Cloudflare AI-crawler block pattern as legz.com.au "
        "— robots.txt explicitly disallows ClaudeBot, Content-Signal ai-train=no.",
    },
    {
        "vertical": "horse_racing",
        "name": "racenet.com.au",
        "base_url": "https://www.racenet.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt opens with an explicit plain-English notice: "
        "'Collection of content... through automated means is prohibited unless you "
        "have express written permission from the publisher.' Clearer than any bot "
        "rule — treat the same as an explicit AI-crawler disallow.",
    },
    {
        "vertical": "horse_racing",
        "name": "punters.com.au",
        "base_url": "https://www.punters.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same explicit automated-collection prohibition notice "
        "in robots.txt as racenet.com.au (both are owned by the same publisher).",
    },
    {
        "vertical": "horse_racing",
        "name": "racing.com",
        "base_url": "https://www.racing.com",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed 2026-07-10: robots.txt fully permissive, no AI-bot mentions, "
        "no prohibition notice. Horse profile pages are a client-side SPA, but "
        "Playwright network inspection (one-time discovery, not needed for production "
        "scraping) found a real GraphQL API at graphql.rmdprod.racing.com — no "
        "robots.txt on that subdomain either. Auth is a static x-api-key header "
        "embedded in racing.com's own JS bundle (da2-6nsi4ztsynar3l3frgxf77q5fe) — "
        "public, shipped to every visitor's browser, not a secret credential. "
        "Confirmed working queries: GetRaceMeetingsByStateNew (today's meetings/races/"
        "results), getHorseUpcomingRacesGrouped (fields/barriers/jockeys), "
        "GetRaceEntryItemByHorsePaged (historical form + starting price). This is now "
        "http/direct-API, not Playwright — cheaper and more reliable than rendering. "
        "Production scraper (event/entity normalization) not yet built.",
    },
    {
        "vertical": "horse_racing",
        "name": "racingvictoria.com.au",
        "base_url": "https://www.racingvictoria.com.au",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed 2026-07-10: robots.txt fully permissive, no restrictions. "
        "Not yet checked for actual page structure/JS-rendering — do that before "
        "building a scraper against it.",
    },
    {
        "vertical": "multi",
        "name": "oddschecker",
        "base_url": "https://www.oddschecker.com",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt itself is clean but every request hits an "
        "active Cloudflare bot challenge ('Just a moment...'), same as "
        "racingandsports.com.au/rwwa.com.au. Bypassing an active challenge is "
        "detection evasion, not scraping.",
    },
    {
        "vertical": "multi",
        "name": "ladbrokes.com.au",
        "base_url": "https://www.ladbrokes.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Site's own embedded client config literally sets "
        "'kasada': true — Kasada is a dedicated commercial bot-detection product, "
        "not a generic challenge. About as explicit a 'do not automate against us' "
        "signal as exists. neds.com.au shares the same auth domain "
        "(authentication.neds.com) and config, confirmed also kasada:true — same "
        "group/protection, ruled out together.",
    },
    {
        "vertical": "multi",
        "name": "unibet.com.au",
        "base_url": "https://www.unibet.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Uses the Kambi white-label betting platform, and "
        "confirmed DataDome (api-js.datadome.co sets a fingerprint cookie on every "
        "session) — another dedicated commercial bot-defense vendor, same category "
        "as Kasada/Cloudflare challenges. The underlying Kambi offering-api "
        "(ap.offering-api.kambicdn.com) returns rich real data through a real "
        "browser session, but that's DataDome passing a real browser's JS/behavioral "
        "challenge, not an open API — replicating it outside a real browser would "
        "mean defeating that challenge, which is evasion, not scraping.",
    },
    {
        "vertical": "multi",
        "name": "betr.com.au (bluebet API)",
        "base_url": "https://web20-api.bluebet.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-10. Clean robots.txt, real no-auth API found via "
        "legitimate Playwright network capture (MasterCategory?EventTypeId=101 gave "
        "real AFL match-winner odds, e.g. St Kilda v Port Adelaide $1.58/$X). BUT: "
        "while hunting for player-prop markets I guessed at an undocumented endpoint "
        "(/MasterEvent?MasterEventId=X) that wasn't part of the real frontend's "
        "traffic — it returned an internal-looking HTML 'Snapshot' debug page, and "
        "every request since (including the previously-working legitimate endpoint) "
        "now returns that same debug page instead of real data. Looks like my own "
        "probing tripped a defensive response. Disabled and not retried — don't want "
        "to keep poking at a system that may be flagging this client as suspicious. "
        "If revisited later, stick strictly to endpoints observed from real frontend "
        "navigation, never guessed URLs.",
    },
    # --- Greyhounds: discovery completed 2026-07-10, all realistic candidates ruled out ---
    {
        "vertical": "greyhound",
        "name": "thedogs.com.au",
        "base_url": "https://www.thedogs.com.au",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Genuine WAF-level block — 403 Forbidden on every "
        "request including /robots.txt itself, not just a courtesy policy. A "
        "technical barrier, not something to route around.",
    },
    {
        "vertical": "greyhound",
        "name": "racingandsports",
        "base_url": "https://www.racingandsports.com.au",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt itself is clean, but every request hits an "
        "active Cloudflare bot challenge ('Just a moment...' / Turnstile). Attempting "
        "to solve/bypass an active anti-bot challenge crosses into detection evasion "
        "territory — treated the same as an explicit block.",
    },
    {
        "vertical": "greyhound",
        "name": "greyhoundrecorder",
        "base_url": "https://www.greyhoundrecorder.com.au",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same explicit 'automated collection prohibited "
        "without express written permission' notice as racenet.com.au/punters.com.au "
        "(same publisher). thegreyhounds.com.au redirects to the same robots.txt.",
    },
    {
        "vertical": "greyhound",
        "name": "betfair",
        "base_url": "https://api.betfair.com/exchange/betting/rest/v1.0",
        "scrape_method": "http",
        "enabled": False,
        "notes": "NOT PURSUED. Official Betfair Exchange API (developer.betfair.com), "
        "not scraping — added 2026-07-10 after every greyhound scraping source was "
        "ruled out, and login/call shapes were verified against the live endpoint "
        "(confirmed the real NO_APP_KEY error). Client code (app/scrapers/betfair.py) "
        "is complete and left in place, but the user decided 2026-07-11 that signing "
        "up for a real betting account with ID verification just for API access "
        "isn't worth it right now. Disabled, not deleted — revisit if that changes.",
    },
    {
        "vertical": "greyhound",
        "name": "racingqueensland.com.au",
        "base_url": "https://www.racingqueensland.com.au",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Confirmed working 2026-07-10, scraper built + real data verified. "
        "robots.txt fully permissive. Real per-race data (box, dog name, trainer, "
        "finish position, margin, time, starting price, form, sectional) via a "
        "same-origin API — auth is a JWT embedded server-side in every page load "
        "(window.apiToken), public/refreshed-per-page rather than a secret. QLD "
        "tracks only — the sole working greyhound source; VIC/NSW/SA/WA coverage "
        "was going to come from Betfair but the user decided against pursuing that "
        "(see betfair entry), so greyhounds stay QLD-only for now.",
    },
    {
        "vertical": "greyhound",
        "name": "fasttrack.grv.org.au",
        "base_url": "https://fasttrack.grv.org.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Blanket robots.txt 'Disallow: /' for everyone — "
        "GRV's own official nomination/fields database explicitly opts out of all "
        "crawling, not just AI-specific.",
    },
    {
        "vertical": "greyhound",
        "name": "grsa.com.au",
        "base_url": "https://www.grsa.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same Cloudflare AI-crawler block template as "
        "legz.com.au/breednet — explicit ClaudeBot disallow, Content-Signal ai-train=no.",
    },
    {
        "vertical": "greyhound",
        "name": "rwwa.com.au",
        "base_url": "https://www.rwwa.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Active bot challenge ('Vercel Security Checkpoint') "
        "on every request, including robots.txt itself. Same treatment as an "
        "explicit block — not something to route around.",
    },
    {
        "vertical": "greyhound",
        "name": "tab.com.au",
        "base_url": "https://www.tab.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Consistent connection timeouts across multiple attempts — matches "
        "the pattern of other actively-blocked wagering-operator sites this session "
        "(thedogs.com.au, racingandsports.com.au). Not pursued further.",
    },
    {
        "vertical": "greyhound",
        "name": "tasracing (racing-api.com)",
        "base_url": "https://stride.racing-api.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-10 while hunting for a shared multi-state vendor "
        "(found via form.tasracing.com.au's network calls). No robots.txt, no auth "
        "needed at all — genuinely open. BUT scoped to Tasmania only (a tiny market), "
        "and 'raceEntries' is empty on every race checked (resulted and upcoming) — "
        "gives box numbers + finish positions but no dog names, so entities can't be "
        "tracked across races without more digging. Not pursued further given low "
        "value (small market) vs effort. Also confirmed: this vendor instance doesn't "
        "cover other states (no VIC/NSW venues in its calendar) — a shared vendor "
        "hope that didn't pan out.",
    },
    {
        "vertical": "greyhound",
        "name": "racingnsw.com.au",
        "base_url": "https://www.racingnsw.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-10. No greyhound content at all — NSW greyhounds "
        "is a fully separate body (GRNSW/GWIC), not covered by Racing NSW's site. "
        "GRNSW's own public presence is thegreyhounds.com.au, already ruled out "
        "(same publisher/prohibition notice as greyhoundrecorder.com.au).",
    },
    {
        "vertical": "greyhound",
        "name": "grv.org.au",
        "base_url": "https://www.grv.org.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-10 — Greyhound Racing Victoria's official site, "
        "clean robots.txt. Has a /racedata/ page with Isolynx sectional/timing CSVs "
        "for specific Victorian tracks only, and explicitly offers an API 'for "
        "personal use' on request via email. But no race fields/box draws/entries "
        "section found — only timing data and editorial tips (not usable per our "
        "primary-data-only rule). Not a fields/results source; worth revisiting if "
        "sectional-time modelling becomes relevant later.",
    },
    # --- Tipster sites: NEVER used to derive our own `tips`/Track Record. As of
    # 2026-07-11 the user asked for a genuinely separate "follow a real tipster,
    # track our own verified win-rate" feature (TipsterPick model, not Tip) — the
    # entries below are for that feature specifically, kept structurally isolated.
    {
        "vertical": "horse_racing",
        "name": "KRUZEY (horse racing)",
        "base_url": "https://www.kruzey.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE (as of 2026-07-11). robots.txt itself looked fully "
        "permissive on inspection, and real content was readable through a "
        "one-off content-fetch tool — but a real production request from our "
        "actual scraper (plain httpx, real User-Agent, same infra as every other "
        "working scraper in this project) gets 403 Forbidden on literally every "
        "path including /robots.txt itself, regardless of User-Agent string "
        "(tried both our honest self-identifying UA and a standard browser UA — "
        "same 403 either way, plain nginx-served block page, no Cloudflare/"
        "Kasada/DataDome branding). Same treatment as thedogs.com.au/"
        "thegreattipoff.com: a real technical barrier, not something to route "
        "around by further disguising the request. The scraper code "
        "(app/scrapers/tipsters/kruzey_*.py) is complete and left in place in "
        "case this site's blocking posture changes later, same pattern as "
        "betfair.py. Kept disabled, not deleted.",
    },
    {
        "vertical": "afl",
        "name": "KRUZEY (AFL)",
        "base_url": "https://www.kruzey.com.au/afl-tips/",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same site/block as KRUZEY (horse racing) — see "
        "that entry. Scraper code kept, disabled.",
    },
    {
        "vertical": "nrl",
        "name": "KRUZEY (NRL)",
        "base_url": "https://www.kruzey.com.au/nrl-tips/",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. Same site/block as KRUZEY (horse racing) — see "
        "that entry. Scraper code kept, disabled.",
    },
    {
        "vertical": "horse_racing",
        "name": "freehorseracingtipsaustralia.com.au",
        "base_url": "https://www.freehorseracingtipsaustralia.com.au",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Found 2026-07-11 after KRUZEY turned out blocked. robots.txt "
        "clean (standard WordPress), and — unlike KRUZEY — a real request from "
        "our actual scraper gets a normal 200, confirmed live. Single page "
        "(/free-horse-racing-tips/) holds one real, static, server-rendered "
        "'meeting' div per venue with a heading like 'RANDWICK race tips:' — "
        "confirmed by direct inspection, not just a research-tool summary. Free "
        "tier only covers each meeting's first three races (rest is Premium/"
        "paywalled — never scraped, per the no-paid-sources rule). VERIFIED "
        "2026-07-11 against real posted selections: format is runner NUMBERS in "
        "order of preference (not names), resolved via our own "
        "EventParticipant.barrier_or_number — 26/27 real picks resolved (96%), "
        "settled 15 real losses via app/analysis/tipster_settle.py the same day.",
    },
    {
        "vertical": "horse_racing",
        "name": "justhorseracing.com.au",
        "base_url": "https://www.justhorseracing.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11. robots.txt clean, real 200 response — "
        "technically scrapable, but actual editorial tip content is buried "
        "under an enormous amount of bookmaker bonus-bet legal/promo boilerplate "
        "(a 'Race 1' text match on one article turned out to be inside Unibet "
        "Odds Boost terms and conditions, not a real tip). Not pursued further "
        "in favour of freehorseracingtipsaustralia.com.au, which has a much "
        "cleaner purpose-built tips container. Worth a proper look later if "
        "that source stops working.",
    },
    {
        "vertical": "horse_racing",
        "name": "racingbase.com.au",
        "base_url": "https://www.racingbase.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt request itself returns a Cloudflare "
        "'Just a moment...' challenge page (confirmed via a real request, not "
        "just inspection) — same treatment as oddschecker/racingandsports.com.au: "
        "an active bot challenge is a hard stop, never attempted to bypass.",
    },
    {
        "vertical": "afl",
        "name": "Alphr (AFL)",
        "base_url": "https://alphr.com.au/afl",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Found 2026-07-11 during a fresh AFL/NRL discovery pass after "
        "KRUZEY turned out blocked. robots.txt is unusually explicit about "
        "welcoming AI crawlers — ClaudeBot, GPTBot, PerplexityBot all "
        "individually 'Allow: /'. Real production fetch confirmed a normal 200 "
        "with substantial server-rendered HTML (not a JS shell) — an AI model "
        "site (159-feature XGBoost per their own docs) publishing round-by-round "
        "H2H tips as clean per-match cards: explicit '{Team} to Win' text, real "
        "official team names, venue, and a stable "
        "/afl/match/{year}-r{round}-{team-a}-v-{team-b} URL per card. Publishes "
        "its own backtested strike rate prominently — never read or trusted "
        "here, we only show our own settled win-rate (app/analysis/"
        "tipster_settle.py). Feeds TipsterPick, never Tip.",
    },
    {
        "vertical": "nrl",
        "name": "Alphr (NRL)",
        "base_url": "https://alphr.com.au/nrl",
        "scrape_method": "http",
        "enabled": True,
        "notes": "Same site/robots.txt/card format as Alphr (AFL) — see that "
        "entry. NRL team names in the 'to Win' text are official club names "
        "(e.g. 'Warriors', 'Bulldogs'), matched to our own afltables.com/"
        "rugbyleagueproject.org-derived team strings via substring matching "
        "in app/scrapers/tipsters/matching.py, same approach as venue matching.",
    },
    {
        "vertical": "afl",
        "name": "statsinsider.com.au",
        "base_url": "https://www.statsinsider.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11. robots.txt permissive (blocks only /news/"
        "preview/, /go/, /pro/finalize — no AI-crawler restriction), real 200 "
        "confirmed. Not built — Alphr found first and is cleaner to parse "
        "(explicit 'to Win' text vs needing to infer the pick). Worth a look if "
        "Alphr ever stops working.",
    },
    {
        "vertical": "afl",
        "name": "gobet.com.au",
        "base_url": "https://www.gobet.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11. robots.txt permissive (blocks /visit/, "
        "rogerbot, dotbot — no AI-crawler restriction), real 200 confirmed. Not "
        "built — same reasoning as statsinsider.com.au (Alphr found first, "
        "cleaner to parse). Worth a look if Alphr ever stops working.",
    },
    {
        "vertical": "nrl",
        "name": "expertfootytips.com.au",
        "base_url": "https://expertfootytips.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11. robots.txt fully permissive (default Yoast, "
        "no disallows at all), real 200 confirmed. Not built — Alphr found "
        "first. Worth a look if Alphr ever stops working.",
    },
    {
        "vertical": "afl",
        "name": "bettingpro.com.au",
        "base_url": "https://www.bettingpro.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt request itself returns a Cloudflare "
        "'Just a moment...' challenge page (confirmed via a real request) — same "
        "treatment as racingbase.com.au/oddschecker: an active bot challenge is "
        "a hard stop, never attempted to bypass.",
    },
    {
        "vertical": "afl",
        "name": "betseeker.com.au",
        "base_url": "https://www.betseeker.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked properly 2026-07-11 for the Tipster Tips feature (an "
        "earlier combined 'Betseeker/Before You Bet/Stats Insider' entry had "
        "never actually verified this — it predated the primary-data rule). "
        "robots.txt permissive (blocks AdsBot only), real 200 confirmed. Not "
        "built — Alphr found first and is cleaner to parse. Worth a look if "
        "Alphr ever stops working.",
    },
    {
        "vertical": "greyhound",
        "name": "Betseeker / Before You Bet / Stats Insider",
        "base_url": "",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Tipster/prop-picks aggregators used in earlier research before the "
        "primary-data rule was established. Never checked for greyhound coverage "
        "and not revisited for Tipster Tips 2026-07-11 — no known greyhound tip "
        "content from these to justify checking. Disabled — do not use to derive tips.",
    },
    # --- Greyhound tipster discovery for the Tipster Tips feature, 2026-07-11:
    # every realistic candidate was blocked, prohibited, paywalled, offline, or
    # would need Playwright-based discovery not yet done. Mirrors the primary-
    # data greyhound search — this vertical may simply have no viable source.
    {
        "vertical": "greyhound",
        "name": "justracing.com.au",
        "base_url": "https://www.justracing.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt explicitly disallows ClaudeBot (and "
        "other AI crawlers) with Content-Signal ai-train=no — same template as "
        "legz.com.au/breednet/grsa.com.au.",
    },
    {
        "vertical": "greyhound",
        "name": "timeform.com",
        "base_url": "https://www.timeform.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "robots.txt blanket-disallows GPTBot specifically ('Disallow: /' "
        "for that agent) — doesn't name ClaudeBot, but an explicit anti-AI-"
        "crawler block for one AI agent is treated the same as a general "
        "anti-AI-scraping signal here, not an invitation for agents it didn't "
        "happen to list. Not pursued.",
    },
    {
        "vertical": "greyhound",
        "name": "surepick.com.au",
        "base_url": "https://surepick.com.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Clean, permissive robots.txt, but all tips are paywalled ($6/day "
        "or $40/day PRO pass) — the project's data strategy explicitly rules out "
        "paid sources, so this is a dead end regardless of scrapability.",
    },
    {
        "vertical": "greyhound",
        "name": "thegreattipoff.com",
        "base_url": "https://thegreattipoff.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "DO NOT SCRAPE. robots.txt itself is clean (just a 120s crawl-"
        "delay), but every page — including the homepage — returns 403 Forbidden. "
        "Treated the same as an explicit block, same as thedogs.com.au/rwwa.com.au.",
    },
    {
        "vertical": "greyhound",
        "name": "betfair.com.au/hub (greyhound tips)",
        "base_url": "https://www.betfair.com.au/hub/category/racing/greyhound-tips/",
        "scrape_method": "http",
        "enabled": False,
        "notes": "robots.txt is clean (only /user/login, /user/logout blocked). "
        "But real content check 2026-07-11 showed articles roughly once every "
        "few months per state (Geelong Jul, Cannington Apr, Wentworth Park Oct, "
        "Rockhampton Sep) — an occasional feature column, not a real ongoing "
        "daily tips feed. Not enough volume for a meaningful tracked win-rate.",
    },
    {
        "vertical": "greyhound",
        "name": "australianracinggreyhound.com",
        "base_url": "https://australianracinggreyhound.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11 — site is currently showing a 'TEMPORARILY "
        "OFFLINE' page site-wide, robots.txt unreachable. Inconclusive rather "
        "than ruled out; worth rechecking later if this feature needs another "
        "greyhound candidate.",
    },
    {
        "vertical": "greyhound",
        "name": "skyracing.com.au (greyhound tips)",
        "base_url": "https://skyracing.com.au/skyExpertTips/greyhoundsTips",
        "scrape_method": "playwright",
        "enabled": False,
        "notes": "Checked 2026-07-11 — no robots.txt file exists at all (404 on "
        "both skyracing.com.au and www.skyracing.com.au), so technically open, "
        "but the actual tips page is JS-driven (static HTML shell shows 'No "
        "races available' with client-side date/venue filters) — the real tip "
        "data loads via an internal API not visible to a plain HTTP fetch. Needs "
        "the same one-time Playwright network-inspection discovery pass used "
        "for racing.com's GraphQL API before this can be assessed properly. Not "
        "done yet — deferred, not ruled out.",
    },
    {
        "vertical": "greyhound",
        "name": "greyhounds.attheraces.com",
        "base_url": "https://greyhounds.attheraces.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Re-checked 2026-07-11. robots.txt looks clean, but a real "
        "request hits an active 'Client Challenge' bot-defense page (JS-gated) — "
        "same treatment as any other confirmed technical block. Also a UK "
        "racing broadcaster ('At The Races'), so AU/QLD track coverage would "
        "have been doubtful even if accessible.",
    },
    {
        "vertical": "greyhound",
        "name": "grv.org.au (tips)",
        "base_url": "https://www.grv.org.au",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Re-checked 2026-07-11 specifically for real tipster content "
        "(the existing grv.org.au entry above only assessed it as a primary-"
        "data source). Found genuinely real, well-structured tips — a named "
        "tipster (e.g. Jason Adams), clean BEST/VALUE/WORTH THE RISK tiers with "
        "race number + dog name + box number, real robots.txt. NOT pursued: "
        "GRV is Greyhound Racing VICTORIA — every meeting covered (Sandown, "
        "Geelong, Bendigo, The Meadows) is a Victorian track, and our only "
        "primary greyhound results source (racingqueensland.com.au) is QLD-only "
        "— every pick would come back permanently unresolved since we'd have no "
        "real result to verify it against. User explicitly chose not to pursue "
        "this (would require adding a VIC primary-data greyhound source too, a "
        "separate, bigger task) — kept disabled, not deleted, in case that "
        "changes.",
    },
    {
        "vertical": "greyhound",
        "name": "qldgreys.com",
        "base_url": "https://qldgreys.com",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11 — 'Queensland's home of greyhound racing', "
        "clean robots.txt, but it's the Brisbane/Ipswich Greyhound Racing "
        "Club's own official venue/membership site (track records, feature "
        "race dates, membership info) — no tips/editorial predictions section "
        "at all. Not a tipster source.",
    },
    {
        "vertical": "greyhound",
        "name": "betfair.com.au/hub (QLD greyhound tips)",
        "base_url": "https://www.betfair.com.au/hub/racing/greyhound-tips/qld-greyhound-tips/",
        "scrape_method": "http",
        "enabled": False,
        "notes": "Checked 2026-07-11 — genuinely real, well-structured, QLD-"
        "specific content this time (a real Rockhampton article with explicit "
        "'BACK: {box}. {Dog Name} (WIN) for 1 unit (Rated at $X.XX)' picks — "
        "exactly the shape needed, and QLD tracks ARE covered by our own "
        "primary results data). But confirmed via the category listing page: "
        "the QLD article is from 17 Sep 2025 — nearly a year stale, no newer "
        "QLD entry since (other states have had 2026 updates, QLD hasn't). "
        "Same conclusion as the general greyhound-tips hub entry above: real "
        "content, but nowhere near frequent enough to be an ongoing tracked "
        "feed. Worth rechecking periodically in case QLD coverage resumes.",
    },
]
