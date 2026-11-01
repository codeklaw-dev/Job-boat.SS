-- Run in Supabase SQL editor. Every personal row belongs to its signed-in owner.
create table if not exists public.jobs (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null references auth.users(id) on delete cascade,
 source text not null,
 source_id text not null,
 title text not null,
 company text not null default '',
 location text not null default '',
 url text not null,
 description text not null default '',
 track text not null check (track in ('temp','career')),
 status text not null default 'new' check (status in ('new','approved','applied','skipped')),
 note text not null default '',
 verified_at timestamptz,
 created_at timestamptz not null default now(),
 unique(owner_id,source,source_id)
);
create table if not exists public.cvs (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null references auth.users(id) on delete cascade,
 filename text not null,
 category text not null default 'general',
 content text not null default '',
 created_at timestamptz not null default now(),
 unique(owner_id,filename)
);
create table if not exists public.profile (
 owner_id uuid primary key references auth.users(id) on delete cascade,
 location text not null default '',
 temp_roles text not null default '',
 career_roles text not null default '',
 temp_pay text not null default '',
 career_pay text not null default '',
 updated_at timestamptz not null default now()
);
create table if not exists public.activity (
 id uuid primary key default gen_random_uuid(),
 owner_id uuid not null references auth.users(id) on delete cascade,
 job_id uuid references public.jobs(id) on delete set null,
 message text not null,
 created_at timestamptz not null default now()
);
alter table public.jobs enable row level security;
alter table public.cvs enable row level security;
alter table public.profile enable row level security;
alter table public.activity enable row level security;
create policy "own jobs" on public.jobs for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own cvs" on public.cvs for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own profile" on public.profile for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy "own activity" on public.activity for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create index if not exists jobs_owner_status on public.jobs(owner_id,status,track);
