-- Spectrum room mode.
-- Patient tablets do not create accounts. They receive a short-lived pairing code once,
-- then an HttpOnly room-device cookie. The server is the only client allowed to read these tables.

create extension if not exists pgcrypto;

create table if not exists public.clinic_rooms (
  id text primary key check (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$'),
  label text not null check (char_length(label) between 1 and 80),
  wing text not null default 'Main ward' check (char_length(wing) between 1 and 80),
  floor integer not null default 1 check (floor between 0 and 99),
  created_at timestamptz not null default now()
);

create table if not exists public.room_patients (
  id uuid primary key default gen_random_uuid(),
  first_name text not null check (first_name ~ '^[[:alpha:]][[:alpha:]'' -]{0,39}$'),
  medical_record_ref text not null check (medical_record_ref ~ '^[A-Za-z0-9][A-Za-z0-9._/ -]{0,63}$'),
  status text not null default 'admitted' check (status in ('admitted', 'discharged')),
  admitted_at timestamptz not null default now(),
  discharged_at timestamptz,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create unique index if not exists room_patients_record_ref_idx on public.room_patients (medical_record_ref);

create table if not exists public.room_assignments (
  id uuid primary key default gen_random_uuid(),
  room_id text not null references public.clinic_rooms(id) on update cascade,
  patient_id uuid not null references public.room_patients(id) on delete restrict,
  assigned_by uuid references auth.users(id) on delete set null,
  assigned_at timestamptz not null default now(),
  discharged_at timestamptz
);

create unique index if not exists room_assignments_one_room_idx
  on public.room_assignments (room_id) where discharged_at is null;
create unique index if not exists room_assignments_one_patient_idx
  on public.room_assignments (patient_id) where discharged_at is null;

create table if not exists public.room_devices (
  id uuid primary key default gen_random_uuid(),
  room_id text not null references public.clinic_rooms(id) on update cascade,
  device_label text not null check (char_length(device_label) between 1 and 60),
  pairing_code_hash text unique,
  pairing_expires_at timestamptz,
  session_token_hash text unique,
  session_expires_at timestamptz,
  last_seen_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index if not exists room_devices_one_active_per_room_idx
  on public.room_devices (room_id) where revoked_at is null;
create index if not exists room_devices_session_idx on public.room_devices (session_token_hash) where revoked_at is null;

alter table public.clinic_rooms enable row level security;
alter table public.room_patients enable row level security;
alter table public.room_assignments enable row level security;
alter table public.room_devices enable row level security;

revoke all on public.clinic_rooms from anon, authenticated;
revoke all on public.room_patients from anon, authenticated;
revoke all on public.room_assignments from anon, authenticated;
revoke all on public.room_devices from anon, authenticated;

-- The application API uses the server-only Supabase secret key after checking the admin
-- access token or the device session. Never put that key in a browser or in a tablet app.

insert into public.clinic_rooms (id, label, wing, floor)
values
  ('room-212', 'Room 212', 'North wing', 2),
  ('room-213', 'Room 213', 'North wing', 2),
  ('room-216', 'Room 216', 'North wing', 2)
on conflict (id) do update set
  label = excluded.label,
  wing = excluded.wing,
  floor = excluded.floor;
