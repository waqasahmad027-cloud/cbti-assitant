-- Run once in Supabase: SQL Editor > New query > paste > Run.
create extension if not exists vector;

create table if not exists documents (
  name text primary key,
  title text,
  doc_type text,
  chunk_count int default 0,
  uploaded_at timestamptz default now()
);

create table if not exists chunks (
  id bigint generated always as identity primary key,
  doc text references documents(name) on delete cascade,
  doc_title text, doc_type text, section text,
  page int, page_end int,
  pillar_no int, pillar text, metric_no int, metric_title text,
  related_metrics int[] default '{}',
  text text, embed_text text,
  embedding vector(384)
);
create index if not exists chunks_doc_idx on chunks (doc);

-- Only the server (service key) may read or write; the public key sees nothing.
alter table documents enable row level security;
alter table chunks enable row level security;

create or replace function match_chunks(query_embedding vector(384), match_count int default 5, metric int default null)
returns table (id bigint, doc text, doc_title text, doc_type text, section text, page int, page_end int,
               pillar_no int, pillar text, metric_no int, metric_title text, related_metrics int[],
               chunk_text text, score float)
language sql stable as $$
  select c.id, c.doc, c.doc_title, c.doc_type, c.section, c.page, c.page_end, c.pillar_no, c.pillar,
         c.metric_no, c.metric_title, c.related_metrics, c.text,
         (1 - (c.embedding <=> query_embedding))::float as score
  from chunks c
  where c.embedding is not null
    and (metric is null or c.metric_no = metric or metric = any(c.related_metrics))
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function set_embeddings(payload jsonb)
returns void language sql as $$
  update chunks c
  set embedding = (e->>'embedding')::vector
  from jsonb_array_elements(payload) e
  where c.id = (e->>'id')::bigint;
$$;
