-- Enable UUID generation
create extension if not exists "pgcrypto";

-- =========================
-- USERS
-- =========================
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================
-- ATHLETE PROFILES
-- =========================
create table if not exists athlete_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references users(id) on delete cascade,
  birth_year int,
  sex text,
  weight_kg numeric(5,2),
  height_cm numeric(5,2),
  primary_sport text,
  training_goal text,
  dietary_preferences text,
  sweat_rate_notes text,
  caffeine_preference text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================
-- USER CONNECTIONS (STRAVA)
-- =========================
create table if not exists user_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider text not null, -- 'strava'
  provider_user_id text,
  access_token text,
  refresh_token text,
  token_expires_at timestamptz,
  scopes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider)
);

-- =========================
-- WORKOUTS (CORE TABLE)
-- =========================
create table if not exists workouts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  provider text not null,
  provider_workout_id text not null,
  name text,
  sport_type text,
  start_date timestamptz,
  start_date_local timestamptz,
  timezone text,
  distance_meters numeric(10,2),
  moving_time_seconds int,
  elapsed_time_seconds int,
  elevation_gain_meters numeric(10,2),
  average_speed numeric(10,4),
  max_speed numeric(10,4),
  average_heartrate numeric(6,2),
  max_heartrate numeric(6,2),
  calories numeric(8,2),
  device_name text,
  raw jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, provider_workout_id)
);

-- Helpful indexes
create index if not exists idx_workouts_user_start_date
  on workouts(user_id, start_date desc);

create index if not exists idx_workouts_raw_gin
  on workouts using gin (raw);

-- =========================
-- FUELING PROFILES
-- =========================
create table if not exists fueling_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references users(id) on delete cascade,
  pre_workout_carb_target_g numeric(6,2),
  during_workout_carb_target_g_per_hr numeric(6,2),
  hydration_target_ml_per_hr numeric(6,2),
  sodium_target_mg_per_hr numeric(6,2),
  preferred_fuel_types text,
  gi_sensitivity text,
  caffeine_strategy text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================
-- RECOMMENDATIONS
-- =========================
create table if not exists recommendations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  workout_id uuid references workouts(id) on delete set null,
  recommendation_type text not null, -- 'pre', 'during', 'post', 'daily'
  title text not null,
  body text not null,
  carb_grams numeric(6,2),
  fluid_ml numeric(6,2),
  sodium_mg numeric(6,2),
  caffeine_mg numeric(6,2),
  reason text,
  status text not null default 'active',
  created_at timestamptz not null default now()
);