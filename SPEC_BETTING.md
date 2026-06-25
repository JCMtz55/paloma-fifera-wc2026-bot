# Betting Feature Spec — WC2026 Bot

## Overview

Users can place fake-money bets on match outcomes before each game kicks off.
Every user starts with a free wallet balance. Bets are settled automatically when
the admin logs a result via `/result`. A rich betting leaderboard runs alongside
the existing team leaderboard.

---

## Currency

- Name: **coins** (⚙️, displayed with 🪙 emoji)
- Starting balance: **500 coins** per user (granted on first `/balance` call or
  first `/bet` command — whichever comes first)
- No way to earn extra coins outside of winning bets (no daily bonus for now)

---

## Data Model (stored in `bot_data` via PicklePersistence)

```
bot_data
├── wallets:       { user_id (str) → int }         # current balance
├── bets:          { match_key (str) → {           # all bets per match
│                      user_id (str) → {
│                          outcome: "home" | "away" | "draw"  # resolved from team name + "win"/"draw"
│                          amount:  int
│                      }
│                  } }
└── bet_history:   [ {                             # settled bets log
        match_key: str,
        user_id:   str,
        outcome:   str,
        amount:    int,
        won:       bool,
        payout:    int,
        settled_at: ISO str
    }, ... ]
```

### Match Key

Format: `"{home} vs {away}"` (e.g. `"Mexico vs USA"`)

This matches the existing `match["home"]` / `match["away"]` fields and is what
`/result` already uses — so no new ID scheme is needed.

---

## Odds System — Parimutuel (Pool-Based)

Dynamic odds calculated from the live pool at the time of settlement.

```
total_pool    = sum of all bets on this match
winning_pool  = sum of bets on the correct outcome
payout_ratio  = total_pool / winning_pool   (rounded to 2 dp)
payout        = floor(bet_amount × payout_ratio)
```

A minimum payout ratio of **1.0x** is enforced (you always get at least your
stake back if you're the only one who bet correctly, edge-case protection).

The current live odds for each outcome are displayed as the implied payout ratio
before bets close, refreshed on `/odds`.

---

## Betting Window

| Event                     | Bet window state          |
|---------------------------|---------------------------|
| Match announced/exists    | OPEN                      |
| 10 minutes before kickoff | CLOSED (bets locked)      |
| Admin runs `/result`      | SETTLED                   |

Cutoff enforced in `/bet`: `if now >= match.kickoff - 10min → reject`.

---

## Commands

### `/balance`
Shows the user's current wallet balance.

```
🪙 Your balance: 420 coins
```

First-time users receive 500 coins and a welcome message.

---

### `/bet <team_name> <outcome> <amount>`

Place a bet on an upcoming match.

- `<team_name>`: the team you're betting on (uses existing `find_team()`)
- `<outcome>`: `win` or `draw`
- `<amount>`: positive integer, must be ≤ user's balance, minimum 10 coins

The match is the **next upcoming match** for that team. `win` means that team wins;
`draw` means the match ends level. To bet on the other team, use their name instead.
The bot resolves home/away internally.

**Success:**
```
✅ Bet placed!
Mexico vs USA  —  Group A
Your pick: 🟢 Mexico to win
Amount: 50 🪙
Balance: 370 🪙
```

**Failure cases:**
- Team not found → `❌ Team not found. Use /teams to see all team names.`
- Betting closed (<10min to kickoff or already played) → `❌ Bets for this match are closed.`
- Insufficient balance → `❌ Not enough coins. Your balance: 30 🪙`
- Amount < 10 → `❌ Minimum bet is 10 coins.`
- Already bet on this match → updates/replaces the bet with a warning:
  `⚠️ You already bet on this match. Your previous bet of 30 🪙 on Mexico to win has been replaced.`
  The old amount is refunded first, then the new bet is deducted.

---

### `/odds <team_name>`

Show live pool odds for the next upcoming match of a team.

```
📊 Live Odds — Mexico vs USA
Group A  •  Closes in 3h 40m

            Bets    Pool    Implied
🟢 Home      4      200 🪙   2.5x
🤝 Draw      2       80 🪙   6.3x
🔴 Away      3      120 🪙   3.3x
─────────────────────────────────
Total pool: 400 🪙 | 9 bettors
```

Outcome labels use the actual team names:
- Home → `🟢 Mexico`
- Away → `🔴 USA`
- Draw → `🤝 Draw`

If bets are closed: shows final odds snapshot with `🔒 Betting closed`.
If no bets placed yet: shows `No bets placed yet — be the first!`

---

### `/mybets`

Shows all of the user's open (unsettled) bets.

```
📋 Your open bets:

1. Mexico vs USA  (Group A, Jun 22)
   Pick: 🟢 Home  •  50 🪙  •  Current odds: 2.5x → est. 125 🪙

2. Brazil vs Argentina  (Group B, Jun 25)
   Pick: 🤝 Draw  •  100 🪙  •  Current odds: 4.1x → est. 410 🪙
```

If none: `You have no open bets. Use /bet Mexico home 50 to place one.`

---

### `/betleaderboard`

Standalone betting leaderboard ranked by wallet balance descending.

```
🪙 Betting Leaderboard:

🥇 Carlos — 1,240 🪙  (3 wins / 5 bets)
🥈 Ana     — 890 🪙   (2 wins / 4 bets)
🥉 Luis    — 500 🪙   (0 wins / 0 bets)
4. Javi    — 120 🪙   (1 win  / 6 bets)
```

Win/loss counts derived from `bet_history`.

---

## Admin Commands

### `/result` — unchanged signature, new side effect

When the admin runs `/result Mexico win 3`, after updating `team_results` the bot
now also:

1. Finds the **most recently passed** match for Mexico (kickoff < now, not already settled)
2. Determines the correct bet outcome (`home` or `away` based on which side Mexico was)
3. Calculates payouts using the parimutuel formula
4. Credits winners' wallets
5. Records all bets in `bet_history` with `won`/`payout` fields
6. Sends a settlement announcement to the group chat

**Settlement announcement:**
```
💰 Bet Results — Mexico vs USA

🏆 Mexico won! (home)
Winning outcome: 🟢 Home

Winners:
  🎉 Carlos +125 🪙  (was 50 🪙 @ 2.5x) → 1,240 🪙 total
  🎉 Ana     +62 🪙  (was 25 🪙 @ 2.5x) → 890 🪙 total

No winning bets — pool returned to bettors.   ← only shown if nobody picked correctly
```

If no bets were placed on this match, the settlement step is silently skipped.

### `/cancelbet <team_name>` (admin only)

Refunds all bets on the next upcoming match for a team and removes them.
Use case: match postponed or cancelled.

```
✅ All bets on Mexico vs USA have been refunded.
3 bets · 250 🪙 returned to bettors.
```

---

## Changes to Existing Commands

### `/help`
Add new betting section:
```
*Betting:*
/balance — Check your coin balance
/bet Mexico win 50 — Bet 50 coins on Mexico to win
/odds Mexico — See live pool odds for Mexico's next match
/mybets — Your open bets
/betleaderboard — Betting standings
```

### 1-hour alert (`fmt_alert` / `fmt_showdown`)
Append to each alert:
```
💰 Betting open — closes in 50 minutes!
Current odds: 🟢 Mexico 2.1x  🤝 Draw 4.5x  🔴 USA 3.0x
Place your bet: /bet Mexico home 50
```

The alert fires 1 hour out; bets are still open for ~50 more minutes (cutoff is 10 min
before kickoff). The copy reflects that, not "closes in 1 hour".

---

## Business Rules Summary

| Rule                              | Value / Behavior                         |
|-----------------------------------|------------------------------------------|
| Starting balance                  | 500 coins (lazy-init on first interaction)|
| Minimum bet                       | 10 coins                                 |
| Maximum bet                       | User's full balance                      |
| Bets per match per user           | 1 (replaceable before cutoff)            |
| Bet cutoff                        | 10 minutes before kickoff                |
| Odds model                        | Parimutuel (pool-based)                  |
| Minimum payout ratio              | 1.0x (can't lose on a solo-winner edge case)|
| Draw available                    | Yes, always (even in knockout rounds)    |
| Settlement trigger                | Admin `/result` command                  |
| Unclaimed pool (no correct bets)  | Full pool refunded pro-rata to all bettors|

---

## Implementation Notes

- No new persistence backend needed — `bot_data` via `PicklePersistence` handles everything
- `find_team()` is reused for bet target resolution
- Match key (`"{home} vs {away}"`) is deterministic from existing match dicts
- When placing a bet, `win` is stored as `"home"` or `"away"` depending on which side
  the named team is in that match; `draw` is stored as `"draw"`
- Settlement in `/result` resolves `win` → `"home"` or `"away"` the same way;
  a `"tie"` result maps to `"draw"`
- All balance mutations must be atomic within a single `bot_data` access to avoid
  race conditions (python-telegram-bot's async handlers are single-threaded per
  update, so PicklePersistence writes are safe)

---

## Out of Scope (for this version)

- Live in-play betting
- Handicap / spread betting
- Daily coin bonuses or coin transfers between users
- Cancelling your own bet after placing
- Per-match max bet caps
