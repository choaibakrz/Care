-- Spectrum patient data, scoped to the authenticated Supabase user.
-- Run this once in the Supabase SQL Editor for the Spectrum project.

create table if not exists public.patient_day_items (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references auth.users(id) on delete cascade,
  service_date date not null,
  time time not null,
  kind text not null check (kind in ('breakfast', 'round', 'physio', 'lunch', 'visits', 'dinner')),
  until_time time,
  created_at timestamptz not null default now(),
  unique (patient_id, service_date, time, kind)
);

create table if not exists public.patient_questions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references auth.users(id) on delete cascade,
  text text not null check (char_length(text) between 1 and 300),
  created_at timestamptz not null default now()
);

create table if not exists public.patient_requests (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references auth.users(id) on delete cascade,
  service_date date not null default current_date,
  kind text not null check (kind in ('water', 'blanket', 'wheelchair', 'pain', 'interpreter', 'care-team')),
  priority text not null default 'normal' check (priority in ('normal', 'high')),
  status text not null default 'sent' check (status in ('sent', 'seen', 'on_the_way', 'done')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.patient_mood (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references auth.users(id) on delete cascade,
  service_date date not null default current_date,
  value smallint not null check (value between 1 and 5),
  created_at timestamptz not null default now()
);

create index if not exists patient_day_items_owner_date_idx on public.patient_day_items (patient_id, service_date, time);
create index if not exists patient_questions_owner_idx on public.patient_questions (patient_id, created_at desc);
create index if not exists patient_requests_owner_date_idx on public.patient_requests (patient_id, service_date, created_at desc);
create index if not exists patient_mood_owner_date_idx on public.patient_mood (patient_id, service_date, created_at desc);

alter table public.patient_day_items enable row level security;
alter table public.patient_questions enable row level security;
alter table public.patient_requests enable row level security;
alter table public.patient_mood enable row level security;

grant select on public.patient_day_items to authenticated;
grant select, insert, delete on public.patient_questions to authenticated;
grant select, insert on public.patient_requests to authenticated;
grant select, insert on public.patient_mood to authenticated;

drop policy if exists "patients read their day" on public.patient_day_items;
create policy "patients read their day"
  on public.patient_day_items for select to authenticated
  using (patient_id = (select auth.uid()));

drop policy if exists "patients read their questions" on public.patient_questions;
create policy "patients read their questions"
  on public.patient_questions for select to authenticated
  using (patient_id = (select auth.uid()));

drop policy if exists "patients add their questions" on public.patient_questions;
create policy "patients add their questions"
  on public.patient_questions for insert to authenticated
  with check (patient_id = (select auth.uid()));

drop policy if exists "patients delete their questions" on public.patient_questions;
create policy "patients delete their questions"
  on public.patient_questions for delete to authenticated
  using (patient_id = (select auth.uid()));

drop policy if exists "patients read their requests" on public.patient_requests;
create policy "patients read their requests"
  on public.patient_requests for select to authenticated
  using (patient_id = (select auth.uid()));

drop policy if exists "patients create their requests" on public.patient_requests;
create policy "patients create their requests"
  on public.patient_requests for insert to authenticated
  with check (patient_id = (select auth.uid()));

drop policy if exists "patients read their mood" on public.patient_mood;
create policy "patients read their mood"
  on public.patient_mood for select to authenticated
  using (patient_id = (select auth.uid()));

drop policy if exists "patients add their mood" on public.patient_mood;
create policy "patients add their mood"
  on public.patient_mood for insert to authenticated
  with check (patient_id = (select auth.uid()));

create or replace function public.ensure_patient_day(p_service_date date)
returns setof public.patient_day_items
language plpgsql
security definer
set search_path = public
as $$
declare
  current_patient uuid := auth.uid();
begin
  if current_patient is null then
    raise exception 'not_authenticated';
  end if;

  insert into public.patient_day_items (patient_id, service_date, time, kind, until_time)
  values
    (current_patient, p_service_date, '07:30', 'breakfast', null),
    (current_patient, p_service_date, '10:00', 'round', null),
    (current_patient, p_service_date, '11:00', 'physio', null),
    (current_patient, p_service_date, '12:00', 'lunch', null),
    (current_patient, p_service_date, '14:00', 'visits', '20:00'),
    (current_patient, p_service_date, '18:30', 'dinner', null)
  on conflict (patient_id, service_date, time, kind) do nothing;

  return query
    select *
    from public.patient_day_items
    where patient_id = current_patient and service_date = p_service_date
    order by time;
end;
$$;

revoke all on function public.ensure_patient_day(date) from public;
grant execute on function public.ensure_patient_day(date) to authenticated;
