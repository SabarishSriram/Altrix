-- Altrix paper trading journal in Supabase (Postgres): one shared journal, no sign-in.
--
-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste this file -> Run.
-- Safe to re-run: every statement is idempotent, and the copy / seed below runs only on the first run.
--
-- Access: the browser uses the public publishable (anon) key and nobody signs in, so the policies below
-- let that key read and write the journal. The 4-digit code page in the web app is the only gate; anyone
-- who has the publishable key can edit these two tables. Keep nothing in them you would mind leaking.

create table if not exists public.journal_settings (
  id            smallint primary key default 1 check (id = 1), -- exactly one row
  starting_cash double precision not null default 100000 check (starting_cash > 0),
  cost_rate     double precision not null default 0.001 check (cost_rate >= 0 and cost_rate < 0.1),
  updated_at    timestamptz not null default now()
);

create table if not exists public.journal_trades (
  id          text primary key check (char_length(id) between 1 and 64),
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
  check ((exit_date is null) = (exit_price is null)),
  check (exit_date is null or exit_date >= entry_date)
);

alter table public.journal_settings enable row level security;
alter table public.journal_trades enable row level security;

grant select, insert, update, delete on public.journal_settings to anon, authenticated;
grant select, insert, update, delete on public.journal_trades to anon, authenticated;

drop policy if exists "shared journal" on public.journal_settings;
create policy "shared journal" on public.journal_settings
  for all to anon, authenticated
  using (true)
  with check (true);

drop policy if exists "shared trades" on public.journal_trades;
create policy "shared trades" on public.journal_trades
  for all to anon, authenticated
  using (true)
  with check (true);

-- First run only (no settings row yet): bring over the journal from the old signed-in tables
-- (paper_journals / paper_trades), then add the starting trades if there is still nothing.
-- The old tables are left untouched; drop them by hand once you have checked the journal.
do $$
begin
  if exists (select 1 from public.journal_settings) then
    return;
  end if;

  if to_regclass('public.paper_trades') is not null then
    insert into public.journal_trades (id, symbol, quantity, entry_date, entry_price, exit_date, exit_price, source, note, created_at, updated_at)
    select id, symbol, quantity, entry_date, entry_price, exit_date, exit_price, source, note, created_at, updated_at
    from public.paper_trades
    on conflict (id) do nothing;
  end if;

  if to_regclass('public.paper_journals') is not null then
    insert into public.journal_settings (id, starting_cash, cost_rate, updated_at)
    select 1, starting_cash, cost_rate, updated_at
    from public.paper_journals
    order by updated_at desc
    limit 1;
  end if;

  if not exists (select 1 from public.journal_trades) then
    insert into public.journal_trades (id, symbol, quantity, entry_date, entry_price, source, note, created_at) values
      ('seed-zyduslife-20261026', 'ZYDUSLIFE.NS', 3, '2026-10-26', 1160.40, 'smart_money_buy', 'same thing not buying i wanna see smart money', '2026-10-26 10:00+05:30'),
      ('seed-kotakbank-20261026', 'KOTAKBANK.NS', 10, '2026-10-26', 440.75, 'smart_money_buy', 'i am not buying this, i just wanna see it', '2026-10-26 10:01+05:30'),
      ('seed-adaniports-20261028', 'ADANIPORTS.NS', 5, '2026-10-28', 1761.30, 'smart_money_buy', 'TEST', '2026-10-28 10:00+05:30'),
      ('seed-bhartiartl-20261028', 'BHARTIARTL.NS', 15, '2026-10-28', 1948.10, 'manual', 'its literally in the middle', '2026-10-28 10:01+05:30');
  end if;

  insert into public.journal_settings (id) values (1) on conflict (id) do nothing;
end $$;

-- Keep-alive for the free plan (projects pause after a week without activity): the daily GitHub
-- workflow calls this with the anon key. It reads no data.
create or replace function public.keepalive() returns text
  language sql stable security invoker set search_path = ''
  as $$ select 'ok'::text $$;
grant execute on function public.keepalive() to anon, authenticated;
