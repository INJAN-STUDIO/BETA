-- Run once: Supabase dashboard -> SQL Editor -> paste -> Run.
create table if not exists beta_kv (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz default now()
);

-- Lock the table: with row-level security on and no policies, the public (anon) key
-- can't read or write it. Only B.E.T.A.'s server, using your SECRET key, can.
alter table beta_kv enable row level security;
