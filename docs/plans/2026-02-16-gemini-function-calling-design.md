# Discord Bot Intelligence Overhaul: Gemini Function Calling

**Date:** 2026-02-16
**Status:** Approved
**Scope:** `discord-bot/services/gemini_client.py`, `discord-bot/cogs/shipping.py`

## Problem

The Discord shipping bot's "brains" rely on a single Gemini prompt that returns raw JSON. This causes:

1. **From/to confusion** — Gemini misclassifies addresses regardless of prompt instructions
2. **No conversation memory** — each message is parsed independently with no history
3. **Fragile heuristics** — a `"from" in content_lower` code guard patches symptoms, not root cause
4. **No error recovery** — users can't correct misclassified fields naturally
5. **JSON parsing failures** — freeform text output sometimes breaks `json.loads()`

## Solution

Replace prompt-based JSON extraction with **Gemini Function Calling** + full **conversation history**.

### Architecture

```
User message
  → Append to session conversation history
  → Send history + tool declarations to Gemini
  → Gemini returns function call(s): set_to_address(), set_from_address(), set_package(), etc.
  → Execute function calls (update session state)
  → Feed results back to Gemini
  → Gemini responds with natural text (follow-up question or confirmation)
```

### Tool Declarations

| Tool | Purpose | When called |
|------|---------|-------------|
| `set_to_address` | Set/update destination address fields | User provides recipient info |
| `set_from_address` | Set/update origin address fields | User explicitly says "from" or "ship from" |
| `set_package` | Set/update weight and dimensions | User provides package info |
| `update_field` | Correct a specific field | User says "change the zip to 78702" |
| `ask_clarification` | Ask user to clarify ambiguous input | Input is ambiguous |

All tools use optional parameters so partial updates work (e.g., only updating zip).

### Conversation History

Each session stores messages sent to Gemini:
- System context injected at session start (default origin address, instructions)
- User messages appended on each turn
- Model responses (function calls) preserved for context
- Function execution results fed back
- Window: last 20 messages max (10 user turns)

### System Prompt (injected at session start)

```
You are a shipping assistant helping create shipping labels.

Default origin (from) address:
  {name}, {street}, {city}, {state} {zip}, {phone}

Rules:
- The user is providing DESTINATION (to) address info unless they explicitly say "from" or "ship from"
- Use set_to_address for destination info, set_from_address ONLY when user explicitly provides origin
- Use set_package for weight and dimensions
- Use update_field when user wants to correct a specific field
- Use ask_clarification when input is genuinely ambiguous
- Phone numbers: 10 digits only, strip formatting
- State: 2-letter abbreviation
- ZIP: 5 digits
- Weight: convert oz to lbs if needed (16oz = 1lb)
- Separate apt/suite/unit into street2
```

## Files Changed

| File | Change |
|------|--------|
| `discord-bot/services/gemini_client.py` | Replace `parse_shipping_info()` with `process_shipping_message()`. Add tool declarations. Add conversation history management. Keep `parse_shipping_request()` and `_fallback_parse_shipping()` for web frontend compatibility. |
| `discord-bot/cogs/shipping.py` | Session stores `messages` list. Remove `"from" in content_lower` hack. Process function call results instead of raw JSON. Handle `ask_clarification` tool calls. |

## What Gets Removed

- `shipping.py:503-518` — the `"from" in content_lower` guard block
- `gemini_client.py:322-345` — `generate_follow_up_question()` (Gemini generates these naturally now)

## What Stays the Same

- Address validation flow (EasyPost)
- Package type selection (envelope/box)
- Delivery options view
- Rate fetching (ThreadPoolExecutor, multi-provider)
- Label purchase flow
- Database schema
- All slash commands (/track, /pickup, /preset)

## Cost Impact

Gemini 2.0 Flash free tier: 1,000 requests/day, 15 RPM.
Typical shipping session: 3-5 Gemini calls (initial parse + follow-ups).
At ~500 tokens/call with history, well within free tier for a Discord bot.
