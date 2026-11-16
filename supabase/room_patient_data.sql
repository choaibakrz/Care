-- Patient requests for room-bound tablets. These rows reference the clinic patient record,
-- not auth.users: a patient has no email address, phone number or Supabase account.

create table if not exists public.room_patient_day_items (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.room_patients(id) on delete cascade,
  service_date date not null default current_date,
  time time not null,
  kind text not null check (kind in ('breakfast', 'round', 'physio', 'lunch', 'visits', 'dinner')),
  until_time time,
  unique (patient_id, service_date, time, kind)
);

create table if not exists public.room_patient_questions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.room_patients(id) on delete cascade,
  text text not null check (char_length(text) between 1 and 300),
  created_at timestamptz not null default now()
);

create table if not exists public.room_patient_requests (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.room_patients(id) on delete cascade,
  service_date date not null default current_date,
  kind text not null check (kind in ('water', 'blanket', 'wheelchair', 'pain', 'interpreter', 'care-team')),
  priority text not null default 'normal' check (priority in ('normal', 'high')),
  status text not null default 'sent' check (status in ('sent', 'seen', 'on_the_way', 'done')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.room_patient_mood (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.room_patients(id) on delete cascade,
  service_date date not null default current_date,
  value smallint not null check (value between 1 and 5),
  created_at timestamptz not null default now()
);

create index if not exists room_patient_day_idx on public.room_patient_day_items (patient_id, service_date, time);
create index if not exists room_patient_questions_idx on public.room_patient_questions (patient_id, created_at desc);
create index if not exists room_patient_requests_idx on public.room_patient_requests (patient_id, service_date, created_at desc);
create index if not exists room_patient_mood_idx on public.room_patient_mood (patient_id, service_date, created_at desc);

alter table public.room_patient_day_items enable row level security;
alter table public.room_patient_questions enable row level security;
alter table public.room_patient_requests enable row level security;
alter table public.room_patient_mood enable row level security;

revoke all on public.room_patient_day_items from anon, authenticated;
revoke all on public.room_patient_questions from anon, authenticated;
revoke all on public.room_patient_requests from anon, authenticated;
revoke all on public.room_patient_mood from anon, authenticated;
