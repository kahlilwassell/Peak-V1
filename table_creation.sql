-- Enable UUIDs
create extension if not exists "pgcrypto";

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  name text,
  created_at timestamptz not null default now()
);

create table if not exists user_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider text not null,                 -- 'strava' | 'garmin'
  provider_user_id text,                  -- athlete id / user id at provider
  access_token text,
  refresh_token text,
  token_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider)
);

create table if not exists workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider text,                          -- if sourced from strava/garmin
  provider_workout_id text,               -- activity id, etc.
  started_at timestamptz,
  duration_seconds int,
  distance_meters int,
  sport text,                             -- run/ride/swim/etc
  calories int,
  raw jsonb,                              -- store the original payload
  created_at timestamptz not null default now(),
  unique (provider, provider_workout_id)
);

create index if not exists idx_workouts_user_started_at
  on workouts(user_id, started_at desc);

create index if not exists idx_workouts_raw_gin
  on workouts using gin (raw);