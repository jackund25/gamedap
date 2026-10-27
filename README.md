# gamedap
Personal gaming companion PWA: schedule, checklists, guides, and game news collected from Discord.

**Status: Phase 1:** a news collector. The web app comes later.

## How the collector works
A private Discord server has one channel per game. Those channels receive official posts through Discord's "Follow" feature (crossposts) or through manual forwards. Every 3 hours a GitHub Actions job:

1. reads new messages from each channel over the Discord REST API (no always-on bot),
2. normalizes them (title, markdown body, link, images, origin, type, and so on),
3. de-duplicates by content hash and upserts them into Supabase (`news_items`),
4. exports the last 30 days to [`exports/news-latest.json`](exports/news-latest.json) and commits it if it changed.

Games and channels are configured in [`collector/config.yaml`](collector/config.yaml).

## Setup
1. **Discord bot**: create an application at <https://discord.com/developers/applications>. Add a bot, enable the **Message Content Intent**, then invite it to your server with *View Channels* and *Read Message History* permissions.
2. **Supabase**: run [`supabase/migrations/0001_news.sql`](supabase/migrations/0001_news.sql) in the SQL editor. Copy the project URL and a **secret** API key.
3. **Environment**: copy `.env.example` to `.env` and fill in the values. `.env` is git-ignored.
4. **GitHub**: add the `DISCORD_BOT_TOKEN`, `SUPABASE_URL` and `SUPABASE_SECRET_KEY` repository secrets.

## Run locally
```bash
cd collector
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt -r requirements-dev.txt

python -m pytest -q                                      # tests
python -m gamedap_collector.main --dry-run --game vampir  # print items, write nothing
python -m gamedap_collector.main                         # collect, store, export
```
Dry runs only need `DISCORD_BOT_TOKEN`. If Supabase is configured, a dry run reads the saved cursor but never writes anything.
