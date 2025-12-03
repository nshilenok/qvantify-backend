# Project Scope & Features

This document outlines the current scope, features, and technical specifications of the Qvantify Fullstack project.

## Core Features

### 1. Shipment Tracking
-   **Multi-Carrier Support:** Ability to track shipments across different carriers using various methods.
-   **Tracking Methods:**
    -   **API/Standard:** Standard tracking via integrations.
    -   **Portal Automation (CUA):** Custom User Agent navigation for portals requiring login.
    -   **Stagehand:** AI-driven DOM extraction for complex tracking pages.
-   **Shipment Management:**
    -   CRUD operations for shipments.
    -   Status updates and timeline tracking.
    -   Automatic background checking (configurable intervals).
    -   Failure handling (retry logic, auto-disable after consecutive failures).

### 2. Intelligent Monitoring
-   **Flagging System:** Automatic detection of issues:
    -   Delays
    -   No updates for 24+ hours
    -   Missing signatures
    -   Customs holds
    -   ETA updates
-   **Alerts:** Configurable thresholds for user notifications.

### 3. Simulation & Testing
-   **Simulator Engine:** Built-in shipment simulator to test tracking logic without real carrier APIs.
-   **Scenarios:** Configurable simulation scenarios (`sim_scenarios`) defining event sequences.
-   **Portal Simulation:** Mock portals (`sim_portal_settings`) for testing CUA/Stagehand extraction.

### 4. Conversation & Interview Interface
-   **Chat Interface:** Interaction with users/respondents.
-   **Respondent Management:** storing respondent data and consent.
-   **Analysis:** Sentiment analysis and summarization of interviews.
-   **Vector Search:** Uses `pgvector` for semantic search over conversation records.

## Technical Stack

### Backend
-   **Python/Flask:** Core application server (`server.py`, `app.py`).
-   **PostgreSQL (Supabase):** Primary database.
    -   Extensions: `vector`, `pgcrypto`, `pg_stat_statements`.
-   **Celery/Async:** Asynchronous task processing for analysis (`async_analyze.py`).

### Database Schema
See `database_schema.sql` for the full DDL.

#### Key Tables
-   `shipments`: Central table for shipment data.
-   `tracking_attempts`: Log of all tracking executions.
-   `timeline_events`: History of shipment status changes.
-   `flags`: Issues identified during tracking.
-   `users`: User accounts and settings.
-   `sim_*`: Tables related to the simulation engine.
-   `records` & `respondents`: Tables for the interview/chat module.

### Frontend
-   **React:** (Implied from `static/` structure and standard practices).
-   **Static Files:** Served from `static/` directory.

## Deployment
-   **Supabase:** Database hosting.
-   **Procfile:** Heroku/Dokku deployment configuration.
-   **Scripts:** `deploy-to-do.sh` for deployment automation.

