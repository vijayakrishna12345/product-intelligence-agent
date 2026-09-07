-- PIA core schema: catalog, crawl, chats, agent runs
-- Project: xqatwvlvdfkaujhwxoer

create table if not exists public.chats (
  id uuid primary key default gen_random_uuid(),
  title text not null default 'New chat',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  next_sequence_no bigint not null default 0
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.chats(id) on delete cascade,
  turn_id uuid not null,
  sequence_no bigint not null,
  role text not null check (role in ('user', 'assistant', 'tool')),
  content text not null default '',
  created_at timestamptz not null default now(),
  prompt_version text null,
  unique (chat_id, sequence_no)
);

create table if not exists public.tool_calls (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.chats(id) on delete cascade,
  turn_id uuid not null,
  message_id uuid null references public.chat_messages(id) on delete set null,
  tool_name text not null,
  arguments jsonb not null default '{}'::jsonb,
  result jsonb null,
  status text not null check (status in ('running', 'success', 'error')),
  error_type text null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null,
  latency_ms integer null
);

create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.chats(id) on delete cascade,
  turn_id uuid not null,
  status text not null check (status in ('queued', 'running', 'completed', 'failed')),
  user_message_id uuid not null references public.chat_messages(id) on delete cascade,
  assistant_message_id uuid null references public.chat_messages(id) on delete set null,
  started_at timestamptz not null default now(),
  completed_at timestamptz null,
  error_type text null,
  error_message text null,
  tools_called_count integer not null default 0,
  agent_steps integer not null default 0,
  input_tokens integer null,
  output_tokens integer null,
  cached_tokens integer null,
  history_tokens integer null,
  tool_result_tokens integer null,
  system_tools_tokens integer null,
  latency_ms integer null,
  prompt_version text null,
  model text null,
  unique (chat_id, turn_id)
);

create table if not exists public.crawl_runs (
  id uuid primary key default gen_random_uuid(),
  source text not null default 'petbarn',
  status text not null check (status in ('running', 'success', 'partial', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz null,
  urls_discovered integer not null default 0,
  products_ok integer not null default 0,
  products_failed integer not null default 0,
  reviews_ok integer not null default 0,
  error_summary jsonb not null default '[]'::jsonb,
  notes text null
);

create table if not exists public.products (
  sku text primary key,
  name text not null,
  brand text null,
  category text null,
  url text not null,
  description text null,
  price numeric null,
  currency text null default 'AUD',
  availability text null,
  rating_value numeric null,
  review_count integer null,
  payload jsonb not null default '{}'::jsonb,
  crawl_run_id uuid null references public.crawl_runs(id) on delete set null,
  scraped_at timestamptz null
);

create table if not exists public.product_reviews (
  id uuid primary key default gen_random_uuid(),
  sku text not null references public.products(sku) on delete cascade,
  external_review_id text not null,
  rating integer not null,
  title text null,
  body text null,
  author text null,
  reviewed_at date null,
  created_at timestamptz not null default now(),
  sentiment_label text null,
  sentiment_score numeric null,
  source text null,
  crawl_run_id uuid null references public.crawl_runs(id) on delete set null,
  payload jsonb not null default '{}'::jsonb,
  unique (sku, external_review_id)
);

create table if not exists public.crawl_pages (
  url text primary key,
  sku text null,
  content_hash text null,
  status text not null default 'fetched',
  fetched_at timestamptz not null default now()
);

create index if not exists idx_chat_messages_chat_sequence
  on public.chat_messages (chat_id, sequence_no);
create index if not exists idx_tool_calls_turn
  on public.tool_calls (turn_id);
create index if not exists idx_tool_calls_chat
  on public.tool_calls (chat_id, started_at);
create index if not exists idx_agent_runs_chat_started
  on public.agent_runs (chat_id, started_at);
create index if not exists idx_agent_runs_chat_status
  on public.agent_runs (chat_id, status);
create index if not exists idx_product_reviews_newest
  on public.product_reviews (sku, reviewed_at desc, created_at desc);
create index if not exists idx_products_brand on public.products (brand);
create index if not exists idx_products_name on public.products (name);

create or replace function public.allocate_chat_sequence(p_chat_id uuid)
returns bigint
language sql
volatile
set search_path = public
as $$
  update public.chats
  set next_sequence_no = next_sequence_no + 1,
      updated_at = now()
  where id = p_chat_id
  returning next_sequence_no;
$$;

revoke all on function public.allocate_chat_sequence(uuid) from public, anon, authenticated;
grant execute on function public.allocate_chat_sequence(uuid) to service_role;

alter table public.chats enable row level security;
alter table public.chat_messages enable row level security;
alter table public.tool_calls enable row level security;
alter table public.agent_runs enable row level security;
alter table public.crawl_runs enable row level security;
alter table public.products enable row level security;
alter table public.product_reviews enable row level security;
alter table public.crawl_pages enable row level security;

do $$
declare
  t text;
begin
  foreach t in array array[
    'chats','chat_messages','tool_calls','agent_runs',
    'crawl_runs','products','product_reviews','crawl_pages'
  ]
  loop
    execute format(
      'create policy deny_anon on public.%I for all to anon using (false) with check (false)',
      t
    );
    execute format(
      'create policy deny_authenticated on public.%I for all to authenticated using (false) with check (false)',
      t
    );
  end loop;
end $$;
