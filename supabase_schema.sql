rain Battle Arena - Supabase schema
-- MirAI Capstone Project
--
-- Recreated from the project's current Supabase public schema.
-- Foreign-key relationships were verified from information_schema.
-- RLS policies/privileges are intentionally not included here because
-- they are environment/security settings rather than table structure.

create extension if not exists pgcrypto;

create table if not exists public.matches (
    id uuid primary key default gen_random_uuid(),
    match_code text not null,
    status text default 'waiting',
    topics jsonb not null,
    question_set jsonb,
    battle_start_time timestamp with time zone,
    created_at timestamp with time zone default now(),
    difficulty text default 'Mixed',
    risk_questions jsonb default '[]'::jsonb,
    clutch_question integer default 14
);

create table if not exists public.players (
    id uuid primary key default gen_random_uuid(),
    match_id uuid not null references public.matches(id),
    player_number integer not null,
    player_name text not null,
    score integer default 0,
    questions_answered integer default 0,
    correct_answers integer default 0,
    current_question integer default 0,
    is_ready boolean default false,
    joined_at timestamp with time zone default now(),
    hints_left integer default 3,
    best_streak integer default 0,
    total_xp integer default 0,
    matches_played integer default 0,
    wins integer default 0,
    losses integer default 0,
    draws integer default 0
);

create table if not exists public.answers (
    id uuid primary key default gen_random_uuid(),
    match_id uuid not null references public.matches(id),
    player_id uuid not null references public.players(id),
    question_number integer not null,
    selected_answer text,
    correct boolean default false,
    points integer default 0,
    response_time_seconds numeric,
    answered_at timestamp with time zone default now()
);

create table if not exists public.match_results (
    id uuid primary key default gen_random_uuid(),
    match_id uuid not null references public.matches(id),
    player1_score integer default 0,
    player2_score integer default 0,
    winner_player integer,
    player1_accuracy numeric,
    player2_accuracy numeric,
    completed_at timestamp with time zone default now()
);

create table if not exists public.profiles (
    id uuid primary key default gen_random_uuid(),
    player_name text not null,
    total_xp integer default 0,
    matches_played integer default 0,
    wins integer default 0,
    losses integer default 0,
    draws integer default 0,
    total_score integer default 0,
    best_streak integer default 0,
    created_at timestamp with time zone default now()
);

-- Verified foreign-key relationships:
-- answers.match_id      -> matches.id
-- answers.player_id     -> players.id
-- match_results.match_id -> matches.id
-- players.match_id      -> matches.id

-- Note:
-- The live project may contain additional indexes, unique constraints,
-- triggers, RLS policies, and grants that are not represented here.
