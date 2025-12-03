-- Enable necessary extensions
-- CREATE EXTENSION IF NOT EXISTS "vector"; -- Removed as requested
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_graphql";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "supabase_vault";

-- Create Enum Types
CREATE TYPE shipment_status AS ENUM (
    'pending', 'in_transit', 'out_for_delivery', 'delivered', 'delayed', 
    'customs', 'exception', 'NotFound', 'InfoReceived', 'InTransit', 
    'OutForDelivery', 'FailedAttempt', 'Delivered', 'AvailableForPickup', 
    'Exception', 'Expired'
);

CREATE TYPE shipment_type AS ENUM ('parcel', 'part_load', 'full_load');

CREATE TYPE flag_type AS ENUM (
    'delay', 'no_update', 'missing_signature', 'customs', 'eta_update', 'other'
);

CREATE TYPE flag_severity AS ENUM ('low', 'medium', 'high');

CREATE TYPE error_type AS ENUM (
    'browser_error', 'ai_error', 'validation_error', 'timeout', 
    'rate_limit', 'network_error', 'unknown'
);

-- Create Tables

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    email VARCHAR UNIQUE NOT NULL,
    name VARCHAR,
    is_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    settings JSONB DEFAULT '{"alertThresholds": {"delayAlert": true, "noUpdateHours": 24}, "defaultCheckInterval": 60, "priorityCheckInterval": 10}'::jsonb
);

CREATE TABLE IF NOT EXISTS user_api_keys (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    key_hash TEXT NOT NULL,
    key_prefix VARCHAR NOT NULL,
    label VARCHAR,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS shipments (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    reference VARCHAR,
    carrier_id VARCHAR,
    carrier_name VARCHAR,
    tracking_number VARCHAR,
    tracking_link TEXT,
    status shipment_status DEFAULT 'NotFound'::shipment_status,
    shipment_type shipment_type DEFAULT 'parcel'::shipment_type,
    origin TEXT,
    destination TEXT,
    estimated_delivery TIMESTAMPTZ,
    actual_delivery TIMESTAMPTZ,
    last_update TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    description TEXT,
    is_starred BOOLEAN DEFAULT false,
    is_archived BOOLEAN DEFAULT false,
    check_interval_minutes INTEGER DEFAULT 60,
    next_check_at TIMESTAMPTZ,
    check_enabled BOOLEAN DEFAULT true,
    check_in_progress BOOLEAN DEFAULT false,
    previous_eta TIMESTAMPTZ,
    eta_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    credentials JSONB, -- User-provided credentials for carrier portal access
    consecutive_failures INTEGER DEFAULT 0,
    last_tracking_error TEXT,
    last_tracking_reason TEXT,
    last_tracking_method TEXT
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    shipment_id UUID REFERENCES shipments(id),
    timestamp TIMESTAMPTZ,
    location TEXT,
    status VARCHAR,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS flags (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    shipment_id UUID REFERENCES shipments(id),
    type flag_type NOT NULL,
    message TEXT NOT NULL,
    severity flag_severity NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved BOOLEAN DEFAULT false,
    resolved_by UUID REFERENCES users(id),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT
);

CREATE TABLE IF NOT EXISTS tracking_attempts (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    shipment_id UUID REFERENCES shipments(id),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    success BOOLEAN,
    error_message TEXT,
    error_type error_type,
    status_changed BOOLEAN DEFAULT false,
    new_status shipment_status,
    flags_added INTEGER DEFAULT 0,
    timeline_events_added INTEGER DEFAULT 0,
    screenshot_url TEXT,
    ai_prompt TEXT,
    ai_response JSONB,
    ai_raw_response TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    browserbase_session_id TEXT,
    tracking_method TEXT
);

CREATE TABLE IF NOT EXISTS portal_selectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portal_pattern TEXT UNIQUE,
    status_selector TEXT,
    timeline_selector TEXT,
    last_verified_at TIMESTAMPTZ,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portal_workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portal_pattern TEXT UNIQUE,
    actions JSONB DEFAULT '[]'::jsonb,
    expected_status_selector TEXT,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sim_scenarios (
    id TEXT PRIMARY KEY,
    name TEXT,
    speed_factor INTEGER DEFAULT 60,
    events JSONB DEFAULT '[]'::jsonb,
    loop BOOLEAN DEFAULT false,
    stuck_at_index INTEGER,
    error_at_index INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sim_shipments (
    id TEXT PRIMARY KEY,
    tracking_number TEXT,
    customer_ref TEXT,
    postal_code TEXT,
    email TEXT,
    shipper_account TEXT,
    carrier_code TEXT,
    carrier_name TEXT,
    origin TEXT,
    destination TEXT,
    service_type TEXT,
    scenario_id TEXT REFERENCES sim_scenarios(id),
    scenario_start_time BIGINT,
    frozen_at_event_index INTEGER,
    portal_only BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sim_portal_settings (
    id TEXT PRIMARY KEY DEFAULT 'portal',
    username TEXT DEFAULT 'shipper',
    password TEXT DEFAULT 'Shipper2025!',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Inferred Tables (Reconstructed from code usage)

CREATE TABLE IF NOT EXISTS records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID, -- In code: g.uuid
    project TEXT, -- In code: g.projectId
    role TEXT,    -- 'user' or 'assistant'
    content TEXT,
    topic TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS respondents (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ,
    project TEXT,
    email TEXT,
    consent BOOLEAN, 
    external_id TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT,
    logo TEXT,
    colour TEXT,
    welcome_title TEXT,
    welcome_message TEXT,
    success_title TEXT,
    success_message TEXT,
    welcome_second_title TEXT,
    welcome_second_message TEXT,
    consent TEXT,
    cta_next TEXT,
    cta_reply TEXT,
    cta_abort TEXT,
    cta_restart TEXT,
    question_title TEXT,
    answer_title TEXT,
    answer_placeholder TEXT,
    loading TEXT,
    collect_email BOOLEAN,
    email_title TEXT,
    email_placeholder TEXT,
    consent_link TEXT,
    skip_welcome BOOLEAN,
    dark_mode BOOLEAN,
    inline_consent BOOLEAN,
    model TEXT,
    temperature FLOAT,
    max_tokens INTEGER,
    top_p FLOAT,
    api TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    project TEXT,
    system TEXT,
    lenght INTEGER, -- Note: Typo in code 'lenght'
    sequence INTEGER,
    topic_type TEXT,
    expiration_strategy TEXT
);

CREATE TABLE IF NOT EXISTS topics_log (
    id SERIAL PRIMARY KEY, -- inferred serial
    topic_id TEXT,
    user_id UUID,
    started_at TIMESTAMPTZ,
    status INTEGER,
    responses INTEGER
);

CREATE TABLE IF NOT EXISTS usage_stats (
    id SERIAL PRIMARY KEY, -- inferred
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    user_id UUID,
    project TEXT,
    topic TEXT,
    api TEXT,
    model TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    respondent UUID,
    project TEXT,
    title TEXT,
    summary TEXT,
    sentiment TEXT,
    facts TEXT
);

CREATE TABLE IF NOT EXISTS interviews_sentences (
    id SERIAL PRIMARY KEY, -- inferred
    respondent UUID,
    project TEXT,
    sentence TEXT,
    label TEXT,
    sub_cluster INTEGER
);
