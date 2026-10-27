-- GameDap Phase 1: news items collected from Discord, plus per-channel cursor.
-- gen_random_uuid() is built into Postgres 13+.

create table if not exists public.news_items (
  id            uuid primary key default gen_random_uuid(),
  game_id       text not null,
  source        text not null default 'discord'
                  check (source in ('discord', 'official_web', 'x')),
  source_ref    text,          -- discord message id
  channel_id    text,
  origin        text,          -- e.g. 'VAMPIR Official Discord #dev-notes'
  item_type     text,          -- announcements | dev-notes | contents | ama | code | maintenance | other
  title         text,
  body          text,
  url           text,
  image_urls    text[] default '{}',
  published_at  timestamptz not null,
  tier          text not null,
  region        text not null default 'Global',
  content_hash  text not null unique,
  raw           jsonb,
  fetched_at    timestamptz not null default now()
);

create index if not exists news_items_game_published_idx
  on public.news_items (game_id, published_at desc);

create table if not exists public.collector_state (
  channel_id       text primary key,
  last_message_id  text,
  updated_at       timestamptz default now()
);

-- Locked down: no public policies. The collector uses the secret key
-- (service_role), which bypasses RLS.
alter table public.news_items enable row level security;
alter table public.collector_state enable row level security;

revoke all on table public.news_items from anon, authenticated;
revoke all on table public.collector_state from anon, authenticated;

grant all on table public.news_items to service_role;
grant all on table public.collector_state to service_role;
