# SuccessKart — Telegram Jobs, Internships & Government Recruitment Bot

SuccessKart is a Telegram-only notification bot. It is separate from SGLTools and has no admin web dashboard.

## Included
- Telegram callback-query updates are enabled so inline option buttons work.
- Telegram registration and profile settings with inline option buttons for qualification, graduation year, opportunity type, location presets, stipend thresholds and notification mode. Free text is retained only for fields that genuinely need personal input (name, skills, custom location/amount). Invalid values are checked before saving.
- Skill-based or Every notification preference.
- Keyword skill matching, opportunity type, location and disclosed minimum stipend filters.
- Admin-only `/addinternship` guided flow with option buttons for stipend and opportunity type, plus validation for title, company, location, deadline and HTTPS application URL; manually added listings use the same notification-mode rules.
- Polling of two public private-job APIs: Remotive and Arbeitnow.
- `/search <keywords>` searches SuccessKart's database and imports live public Unstop and Internshala results when `APISH_API_KEY` is configured; it no longer redirects users to search-engine results.
- `/sources` explains which providers are automatically monitored, which require the optional API key, and which are not yet integrated.
- Official India recruitment-page monitoring for National Career Service (NCS), Employment News, APPSC, Andhra Pradesh SLPRB, UPSC, SSC, RRB, RRB Secunderabad, IBPS, SBI Careers, RBI Opportunities, ISRO Careers and DRDO Careers.
- Government apprenticeships and trainee notices are classified as Internship; other recruitment notices are classified as Full-time.
- Source label and official notice/application link are included in each alert.
- URL/title deduplication, persistent SQLite WAL database, delivery queue, retry/backoff, source health, Docker deployment and persistent volume.

## Source coverage — read before deploying
The bot monitors the public pages/APIs listed in `successkart/sources.py`. Government portals frequently change page structure, and some pages may block or change automated access. Each source is fetched independently: a failing source does not stop the others. Check `/adminstats` for source health and fetched counts.

This is **not** an internet-wide crawler and cannot guarantee every job or internship. Coverage of state-level recruitment beyond Andhra Pradesh is partial; many individual State PSC, police, municipal, university and PSU portals are not yet individually integrated. NCS and Employment News provide additional government and PSU coverage, but they do not replace every organization's own portal. Where a portal exposes only a listing page, the alert links to that official listing page rather than inventing an application URL. Always open the official notice and verify eligibility, age limit, vacancies, fees and deadlines before applying.

Important distinction: `/search` no longer sends users to Google or other job-board search pages. It searches SuccessKart's database and, when `APISH_API_KEY` is configured, imports public Unstop and Internshala results into the database before displaying them in Telegram. API.SH is an independent third-party data provider, not an official Unstop or Internshala API; each live search currently makes two provider calls and consumes credits. Check its current pricing and terms before enabling it. Indeed, Naukri, LinkedIn, Foundit, Wellfound, Cutshort, Hirist, Instahyre and Glassdoor are not live-imported by this build because approved/usable listing access has not been configured. Do not describe those as connected feeds.

The automatic integrations use public pages/APIs only. They do not bypass login pages, CAPTCHAs, anti-bot systems or website restrictions. If a source changes its layout, it may need a parser update. Do not rely on the bot as the sole source for a deadline-critical application.

Skill matching is keyword-based, not semantic AI. Government notice pages often omit structured qualification and skill metadata, so skill-based mode may not match every government post that a person is eligible for. Users who want all government alerts should choose `/mode all`. Qualification data is collected but eligibility is not automatically adjudicated. Minimum stipend filters reject listings with undisclosed stipend/salary when a minimum is set.

## Setup
1. Create a bot using Telegram `@BotFather`.
2. Obtain your numeric Telegram user ID.
3. Copy `.env.example` to `.env`.
4. Add your bot token to `BOT_TOKEN` and numeric admin IDs to `ADMIN_IDS`. Never commit or share `.env`.

## Docker deployment
```bash
docker compose up -d --build
docker compose logs -f successkart
```

The SQLite database is persisted in the `successkart_data` volume. Stop with `docker compose down`. Do not use `docker compose down -v` unless you intend to delete the database volume.

## Local development
Python 3.12 recommended:
```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m successkart.main
```

Keep the process running on an always-on server.

## User commands
`/start`, `/register`, `/settings`, `/mode`, `/pause`, `/resume`, `/jobs`, `/internships`, `/government`, `/remote`, `/search keywords`, `/notifications`, `/catchup`, `/testalert`, `/sources`, `/help`.

## Admin commands
All user commands plus `/addinternship`, `/adminstats`, `/adminjobs`, `/deletejob ID`, `/retryfailed`, `/refresh`.

## Before accepting public users
- Test registration and both notification modes with separate test accounts.
- Test admin publishing, deduplication, retries and blocked recipients.
- Verify each source's health on the actual deployment; this build environment had no outbound network access, so live source polling could not be exercised here.
- Add a privacy notice, explicit consent and account deletion/export workflow.
- Set up encrypted backups and test restore.
- Add uptime/error alerting and regularly review source changes.
- For high-volume/multi-instance operation, migrate SQLite to PostgreSQL and use a dedicated queue/worker system.

## Verification status
Python compilation passed and 14 automated tests passed in the build environment using lightweight Telegram-module stubs because the real python-telegram-bot dependency could not be installed in this offline environment. A separate mocked polling check verified that source-health rows, new opportunity insertion and one delivery complete successfully. Live Telegram delivery, live source parsing and deployment were not end-to-end tested with real credentials/network access. This is a production-oriented starter, not a verified production service or a guarantee of complete coverage.


### Optional Unstop and Internshala search integration

1. Create an API.SH account and generate an API key at https://app.api.sh/.
2. Add `APISH_API_KEY=your_key` to the project's `.env` file.
3. Rebuild/restart with `docker compose up -d --build`.
4. Run `/search python internship` in Telegram. Returned listings are imported into SuccessKart and shown in the chat; the original listing URL is retained as the application link.

API.SH is a third-party provider, not an official Unstop or Internshala API. Its current documentation lists 1,000 free credits per month and one credit per search request; this build makes two requests per search. Pricing and terms can change, so verify them before enabling the integration. No provider requests are made when the key is blank.

## Updated Telegram menu and notification troubleshooting

- `/start` installs the command menu for that chat based on the configured Telegram role. Normal users see the user commands; IDs listed in `ADMIN_IDS` also see admin commands. Send `/start` again after deployment to refresh the menu.
- Telegram clients may show only a few autocomplete suggestions while typing `/`; open the bot's command/menu button or run `/help` to view the complete role-specific list. The bot now publishes 16 user commands and additional admin-only commands.
- `/jobs`, `/internships`, `/government` and `/remote` show five listings per page with Previous/Next buttons.
- A successful registration sends a clearly labelled test notification and checks up to 25 recent matching listings. `/testalert` repeats the delivery test; it is not a job vacancy.
- `/notifications` reports published listing count and sent/pending/failed alert counts. `/catchup` retries matching listings from the last 14 days.
- `/refresh` is admin-only and immediately polls the connected sources. Check its per-source result and `/adminstats` before assuming a feed is working.
- New source polling starts shortly after bot startup and repeats at `POLL_INTERVAL_MINUTES`. A user receives a real vacancy alert only when a newly collected listing passes their active notification mode and profile filters.

Important: no software can guarantee a vacancy from a source that publishes no accessible listings or blocks the request. The test notification confirms Telegram delivery only; `/refresh` and `/adminstats` help diagnose source availability.
