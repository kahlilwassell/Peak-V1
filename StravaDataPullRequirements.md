# Strava Integration MVP Implementation Checklist

## Goal
Allow each Peak user to connect their Strava account, sync activity data, and store it in Peak for fueling recommendations.

---

## 1. Strava App Setup
- [ ] Register a Strava application
- [ ] Save the Strava `client_id`
- [ ] Save the Strava `client_secret`
- [ ] Configure the Strava **Authorization Callback Domain**
- [ ] Add local and production callback URLs to the app setup

Notes:
- Strava requires app registration before OAuth can be used.
- The callback URL must be within the configured callback domain.
- The client secret must never be exposed publicly. :contentReference[oaicite:0]{index=0}

---

## 2. OAuth Flow
- [ ] Create backend endpoint: `GET /v1/strava/connect/start`
- [ ] Redirect the user to Strava OAuth authorize URL
- [ ] Request the scopes we need:
  - [ ] `activity:read`
  - [ ] `activity:read_all` (recommended)
  - [ ] `profile:read_all` (optional but useful)
- [ ] Create backend callback endpoint: `GET /v1/strava/connect/callback`
- [ ] Read `code`, `scope`, and `state` from Strava callback
- [ ] Exchange `code` for tokens using `POST https://www.strava.com/oauth/token`
- [ ] Validate which scopes the user actually approved

Notes:
- Strava uses OAuth 2.0.
- The authorization response includes a short-lived `code`.
- The token exchange returns an `access_token`, `refresh_token`, expiration, and athlete summary data. :contentReference[oaicite:1]{index=1}

---

## 3. Token Storage
- [ ] Store one Strava connection per Peak user
- [ ] Save:
  - [ ] `user_id`
  - [ ] `provider = 'strava'`
  - [ ] `provider_user_id`
  - [ ] `access_token`
  - [ ] `refresh_token`
  - [ ] `token_expires_at`
  - [ ] `scopes`
- [ ] Always persist the **latest** refresh token returned by Strava

Notes:
- Access tokens expire after 6 hours.
- Refresh tokens can rotate, so the newest one should always be stored. :contentReference[oaicite:2]{index=2}

---

## 4. Token Refresh Logic
- [ ] Before calling Strava, check whether the token is expired or close to expiry
- [ ] If needed, refresh using `POST https://www.strava.com/oauth/token`
- [ ] Update stored:
  - [ ] `access_token`
  - [ ] `refresh_token`
  - [ ] `token_expires_at`

Notes:
- Strava recommends refreshing when needed and always persisting the most recent refresh token. :contentReference[oaicite:3]{index=3}

---

## 5. Core Strava Sync Endpoints
- [ ] `POST /v1/strava/sync-profile`
  - Pull `GET /athlete`
- [ ] `POST /v1/strava/sync-activities`
  - Pull `GET /athlete/activities`
- [ ] `POST /v1/strava/sync-activity-details/{provider_workout_id}`
  - Pull `GET /activities/{id}`
- [ ] `POST /v1/strava/sync-activity-streams/{provider_workout_id}`
  - Pull `GET /activities/{id}/streams`

Notes:
- These are the main endpoints needed for profile, activity list, activity detail, and stream ingestion. :contentReference[oaicite:4]{index=4}

---

## 6. Data We Should Store
### Athlete / connection data
- [ ] Strava athlete ID
- [ ] accepted scopes
- [ ] tokens + expiry

### Workout summary data
- [ ] Strava activity ID
- [ ] name
- [ ] sport type
- [ ] start date
- [ ] distance
- [ ] moving time
- [ ] elapsed time
- [ ] elevation gain
- [ ] average / max heart rate if available
- [ ] calories if available
- [ ] raw activity JSON

### Optional detailed / stream data
- [ ] time stream
- [ ] distance stream
- [ ] heartrate stream
- [ ] velocity stream
- [ ] altitude stream
- [ ] cadence / watts when available

---

## 7. Database Requirements
- [ ] `users` table
- [ ] `user_connections` table
- [ ] `workouts` table
- [ ] unique constraint on `(provider, provider_workout_id)`
- [ ] `raw jsonb` column on workouts for original Strava payloads

Goal:
- Make ingestion idempotent so we can safely re-sync the same user without duplicates.

---

## 8. Multi-User Support
- [ ] Every Peak user must authorize Strava individually
- [ ] Never use one shared Strava token for all users
- [ ] Look up the connected user’s tokens before each sync
- [ ] Refresh that specific user’s token when needed
- [ ] Store data in Peak under that specific `user_id`

---

## 9. Webhooks (Recommended Soon After MVP)
- [ ] Implement Strava webhook subscription
- [ ] Handle new activity / update events
- [ ] Handle deauthorization events

Why:
- Avoid polling every user repeatedly
- Keep user data up to date
- Reduce risk of hitting Strava rate limits

Notes:
- Strava recommends webhooks for activity updates and deauthorization handling.
- Default app rate limits are 200 requests per 15 minutes and 2,000 per day. :contentReference[oaicite:5]{index=5}

---

## 10. MVP Order of Operations
- [ ] Register Strava app
- [ ] Build `connect/start`
- [ ] Build `connect/callback`
- [ ] Store tokens in `user_connections`
- [ ] Build `sync-profile`
- [ ] Build `sync-activities`
- [ ] Store workouts in Postgres
- [ ] Add token refresh logic
- [ ] Add activity detail sync
- [ ] Add streams for selected workouts
- [ ] Add webhooks

---

## Guiding Principle
Strava is the source of raw workout data.  
Peak is the source of user-facing product behavior and recommendations.