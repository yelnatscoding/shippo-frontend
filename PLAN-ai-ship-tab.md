# Plan: Gemini AI Chatbot Tab for Shipping Tool

## Context
The frontend currently requires manual form entry for the "to" address and has a **hardcoded** from-address. The user wants a new "AI Ship" tab where they can type natural language like "Ship from Miami FL 33122 to Ontario CA 91761, 43x34x34cm 30kg" and have Gemini parse it, fetch rates, and allow label purchase — all in one flow.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shippo-frontend/api/chat.py` | CREATE | Gemini REST API endpoint — parses natural language into structured shipping data |
| `shippo-frontend/public/index.html` | MODIFY | Add 4th "AI Ship" tab with chat UI |
| `shippo-frontend/public/app.js` | MODIFY | Add chat methods, make from-address dynamic |
| `shippo-frontend/public/style.css` | MODIFY | Chat bubble styles |
| `shippo-frontend/.env.example` | MODIFY | Add GEMINI_API_KEY placeholder |

## Implementation Steps

### Step 1: Create `api/chat.py`
- New Vercel serverless function following existing pattern (BaseHTTPRequestHandler + CORS)
- POST endpoint receives `{ "message": "user text" }`
- Calls Gemini REST API (`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`) using `requests` (already a dependency)
- Prompt instructs Gemini to return JSON with `from_address`, `to_address`, `parcel` (dimensions in inches, weight in lbs — Gemini handles cm/kg conversion)
- Validates response, returns structured data or error
- Uses `GEMINI_API_KEY` env var

### Step 2: Add "AI Ship" tab to `index.html`
- Add tab button after existing 3 tabs (line ~44)
- Add tab pane with:
  - Chat messages area (scrollable div)
  - Initial bot greeting with example input
  - Textarea + Send button
  - Parsed data confirmation area (hidden initially)
  - Rates results area (hidden initially)

### Step 3: Add chat logic to `app.js`
New methods on ShippingApp:
- `sendChatMessage()` — sends user text to `/api/chat`, displays parsed result
- `addChatMessage(sender, content)` — appends message bubble to chat UI
- `formatParsedDataMessage(parsed)` — formats parsed data as readable HTML
- `renderParsedData(parsed)` — shows confirmation card with "Get Rates" button
- `getChatRates()` — calls `/api/rates` with parsed data, renders rates in chat tab reusing existing `renderRates()`, stores state for `purchaseLabel()`

Also: bind Enter key and send button in `bindEvents()`.

### Step 4: Add chat styles to `style.css`
- `.chat-messages` container (scrollable, gray background)
- `.chat-message` with `.bot-message` / `.user-message` variants
- Message bubbles with icons
- Responsive adjustments

### Step 5: Environment setup
- Add `GEMINI_API_KEY` to `.env.example`
- User adds key to `.env.local` and Vercel env vars
- No new pip dependencies needed

## Key Design Decisions
- **Gemini REST API** via `requests` — no new dependencies
- **gemini-2.0-flash** model — fast, cheap, sufficient for structured extraction
- **Gemini handles unit conversion** in prompt (cm→in, kg→lbs)
- **Rates render in chat tab** — user stays in context, reuses existing `renderRates()`
- **Purchase works from chat tab** — reuses existing `purchaseLabel()` via stored state
- **From-address becomes dynamic** — parsed from chat input instead of hardcoded

## Verification
1. Deploy locally: `cd shippo-frontend && vercel dev --listen 3000`
2. Open AI Ship tab, type: "Ship from 3006 NW 72nd Ave Miami FL 33122 to 2755 E Philadelphia St Ontario CA 91761, 43x34x34cm 30kg"
3. Verify: parsed addresses display correctly, dimensions converted to inches/lbs
4. Click "Get Rates" — verify rates from all providers appear
5. Click "Buy" on a rate — verify label purchase and history save work
6. Deploy to Vercel: `vercel --prod`
7. Add `GEMINI_API_KEY` to Vercel env vars
8. Test on production URL
