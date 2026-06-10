# Relationship partner invite flow (qadam_bot)

Deep link format:

```
https://t.me/<BOT_USERNAME>?start=rel_invite_<session_token>
```

Legacy alias: `love_partner_<session_token>`

Partner WebApp entry (existing main app route):

```
<WEBAPP_BASE_URL>/start/<session_token>?partner_tg_id=<telegram_user_id>
```

Result page (user1 after partner completes):

```
<WEBAPP_BASE_URL>/result/<session_token>
```

## Bot-side events (automatic)

| Event | When |
|-------|------|
| `partner_deeplink_opened` | User opens `/start rel_invite_<token>` |
| `partner_start_clicked` | User taps inline **📝 Testni boshlash** (callback step) |
| `partner_test_completed` | WebApp calls admin API (below) |
| `result_ready` | Same API call as completion |

## WebApp → bot admin API

Base URL: `BOT_ADMIN_BASE_URL` (Railway admin service)  
Auth: `?token=<ADMIN_TOKEN>` on every request

### 1. Record any funnel event

`POST /api/relationship/funnel-event?token=<ADMIN_TOKEN>`

```json
{
  "invite_token": "<session_token>",
  "event_name": "invite_created",
  "telegram_id": 123456789,
  "role": "user1",
  "metadata": {"source": "share_page"}
}
```

Allowed `event_name` values:

- `invite_created` — call when user1 session is created or share link is generated
- `partner_test_started` — call when partner begins the quiz on `/start/<token>`
- `user1_result_opened` — call when user1 opens the result page

### 2. Partner completed + notify user1

`POST /api/relationship/partner-completed?token=<ADMIN_TOKEN>`

```json
{
  "invite_token": "<session_token>",
  "user1_telegram_id": 111111111,
  "partner_telegram_id": 222222222
}
```

This records `partner_test_completed` and `result_ready`, then sends user1:

> Sherigingiz testni yakunladi ✅ …

with WebApp button **📊 Natijani ko‘rish** (not shown on share page before completion).

### 3. User1 opened result (optional explicit track)

`POST /api/relationship/user1-result-opened?token=<ADMIN_TOKEN>`

```json
{
  "invite_token": "<session_token>",
  "event_name": "user1_result_opened",
  "telegram_id": 111111111,
  "role": "user1"
}
```

## Admin dashboard

Open:

```
<BOT_ADMIN_BASE_URL>/admin/bot-tracking?token=<ADMIN_TOKEN>
```

Shows relationship funnel counts and conversion rates.

## Manual test checklist

1. POST `invite_created` for a test token (or integrate from WebApp).
2. Open `https://t.me/<bot>?start=rel_invite_<token>` as user2.
3. Bot shows invite message; tap **📝 Testni boshlash**.
4. Tap WebApp button → partner test at `/start/<token>?partner_tg_id=...`.
5. POST `partner_test_started` from WebApp when quiz begins.
6. Complete partner test; POST `partner-completed` with user1 Telegram ID.
7. User1 receives **📊 Natijani ko‘rish** in Telegram.
8. Confirm admin dashboard funnel counts increased.
