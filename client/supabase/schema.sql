-- Altrix paper trading journal in Supabase (Postgres).
--
-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste this file -> Run.
-- Safe to re-run: every statement is idempotent.
--
-- Row Level Security: the browser uses the public "anon"/publishable key, so these policies are what
-- keep each signed-in user's journal private. Anonymous requests can read and write nothing.

create table if not exists public.paper_journals (
  user_id       uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  starting_cash double precision not null default 100000 check (starting_cash > 0),
  cost_rate     double precision not null default 0.001 check (cost_rate >= 0 and cost_rate < 0.1),
  updated_at    timestamptz not null default now()
);

create table if not exists public.paper_trades (
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id          text not null check (char_length(id) between 1 and 64),
  symbol      text not null check (symbol ~ '^[A-Z0-9&-]{1,20}\.NS$'),
  quantity    integer not null check (quantity > 0),
  entry_date  date not null,
  entry_price double precision not null check (entry_price > 0),
  exit_date   date,
  exit_price  double precision check (exit_price > 0),
  source      text not null check (source in ('ema_buy', 'smart_money_buy', 'manual')),
  note        text not null default '' check (char_length(note) <= 200),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (user_id, id),
  check ((exit_date is null) = (exit_price is null)),
  check (exit_date is null or exit_date >= entry_date)
);

alter table public.paper_journals enable row level security;
alter table public.paper_trades enable row level security;

drop policy if exists "own journal" on public.paper_journals;
create policy "own journal" on public.paper_journals
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "own trades" on public.paper_trades;
create policy "own trades" on public.paper_trades
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- Keep-alive for the free plan (projects pause after a week without activity): the daily GitHub
-- workflow calls this with the anon key. It reads no user data.
create or replace function public.keepalive() returns text
  language sql stable security invoker set search_path = ''
  as $$ select 'ok'::text $$;
grant execute on function public.keepalive() to anon, authenticated;
