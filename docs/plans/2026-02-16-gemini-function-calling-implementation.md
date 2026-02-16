# Gemini Function Calling Intelligence Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Discord bot's prompt-based JSON extraction with Gemini Function Calling + conversation history to fix from/to address confusion and enable natural multi-turn corrections.

**Architecture:** Migrate from deprecated `google-generativeai` SDK to new `google-genai` SDK. Define shipping tools as Python function declarations. Send full conversation history to Gemini on each turn. Gemini returns structured function calls instead of freeform JSON. Session state updated from function call args.

**Tech Stack:** `google-genai` SDK, `google.genai.types` for tool/config definitions, Gemini 2.0 Flash model

---

### Task 1: Migrate to new google-genai SDK

**Files:**
- Modify: `discord-bot/requirements.txt`
- Modify: `discord-bot/services/gemini_client.py:1-22` (imports + __init__)
- Modify: `discord-bot/services/gemini_client.py:227-265` (parse_calendar_text)
- Modify: `discord-bot/services/gemini_client.py:267-320` (chat_with_context)

**Step 1: Update requirements.txt**

Replace `google-generativeai>=0.3.0` with `google-genai>=1.0.0` in `discord-bot/requirements.txt`.

**Step 2: Install new SDK**

Run: `pip install google-genai`

**Step 3: Update imports and __init__ in gemini_client.py**

Replace lines 1-22:
```python
"""Gemini AI client for natural language processing"""

import os
from google import genai
from google.genai import types
from typing import Optional, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API"""

    MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        self.client = genai.Client(api_key=self.api_key)
        logger.info("Gemini client initialized")
```

**Step 4: Migrate parse_calendar_text (lines 227-265)**

Replace `self.model.generate_content_async(prompt)` with:
```python
response = await self.client.aio.models.generate_content(
    model=self.MODEL,
    contents=prompt,
)
```

**Step 5: Migrate chat_with_context (lines 267-320)**

Same pattern — replace `self.model.generate_content_async(prompt)` with:
```python
response = await self.client.aio.models.generate_content(
    model=self.MODEL,
    contents=prompt,
)
```

**Step 6: Verify bot starts without errors**

Run: `cd discord-bot && python -c "from services.gemini_client import GeminiClient; print('import ok')"`

**Step 7: Commit**

```bash
git add discord-bot/requirements.txt discord-bot/services/gemini_client.py
git commit -m "refactor: migrate gemini_client to new google-genai SDK"
```

---

### Task 2: Add shipping tool declarations

**Files:**
- Modify: `discord-bot/services/gemini_client.py` (add after __init__, before parse_calendar_text)

**Step 1: Add tool function declarations as a class constant**

Add this after the `__init__` method (before any other methods):

```python
    # --- Shipping tool declarations for function calling ---
    SHIPPING_TOOLS = [
        {
            "name": "set_to_address",
            "description": (
                "Set or update the DESTINATION (recipient) address. "
                "Call this when the user provides recipient/destination info. "
                "All addresses are destination unless user explicitly says 'from' or 'ship from'."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Recipient full name"},
                    "street": {"type": "STRING", "description": "Street address (no apt/suite/unit)"},
                    "street2": {"type": "STRING", "description": "Apt, suite, unit, floor (e.g. 'Apt 4B')"},
                    "city": {"type": "STRING", "description": "City name"},
                    "state": {"type": "STRING", "description": "2-letter state code (e.g. CA, TX)"},
                    "zip": {"type": "STRING", "description": "5-digit ZIP code"},
                    "phone": {"type": "STRING", "description": "10-digit phone (digits only, no formatting)"},
                    "email": {"type": "STRING", "description": "Email address"},
                },
            },
        },
        {
            "name": "set_from_address",
            "description": (
                "Set or update the ORIGIN (sender) address. "
                "ONLY call this when the user EXPLICITLY says 'from', 'ship from', or 'sending from'. "
                "The default origin is already pre-filled — do NOT call this unless user provides a different origin."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Sender full name"},
                    "street": {"type": "STRING", "description": "Origin street address"},
                    "city": {"type": "STRING", "description": "Origin city"},
                    "state": {"type": "STRING", "description": "2-letter state code"},
                    "zip": {"type": "STRING", "description": "5-digit ZIP code"},
                    "phone": {"type": "STRING", "description": "10-digit phone (digits only)"},
                },
            },
        },
        {
            "name": "set_package",
            "description": "Set or update package weight and/or dimensions.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "weight": {"type": "NUMBER", "description": "Weight in pounds (convert oz: 16oz=1lb)"},
                    "length": {"type": "NUMBER", "description": "Length in inches"},
                    "width": {"type": "NUMBER", "description": "Width in inches"},
                    "height": {"type": "NUMBER", "description": "Height in inches"},
                },
            },
        },
        {
            "name": "update_field",
            "description": (
                "Update a single specific field when the user wants to correct something. "
                "Use this for corrections like 'change the zip to 78702' or 'the name is actually Jane'."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "field": {
                        "type": "STRING",
                        "description": "Field to update: to_name, to_street, to_street2, to_city, to_state, to_zip, to_phone, to_email, from_name, from_street, from_city, from_state, from_zip, from_phone, weight, length, width, height",
                    },
                    "value": {"type": "STRING", "description": "New value for the field"},
                },
                "required": ["field", "value"],
            },
        },
        {
            "name": "ask_clarification",
            "description": (
                "Ask the user a clarifying question when their input is genuinely ambiguous. "
                "Only use when you truly cannot determine intent from context."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING", "description": "The question to ask the user"},
                },
                "required": ["question"],
            },
        },
    ]
```

**Step 2: Verify syntax**

Run: `cd discord-bot && python -c "from services.gemini_client import GeminiClient; print(len(GeminiClient.SHIPPING_TOOLS), 'tools defined')"`
Expected: `5 tools defined`

**Step 3: Commit**

```bash
git add discord-bot/services/gemini_client.py
git commit -m "feat: add shipping tool declarations for Gemini function calling"
```

---

### Task 3: Add process_shipping_message() method

**Files:**
- Modify: `discord-bot/services/gemini_client.py` (add new method after SHIPPING_TOOLS)

**Step 1: Add the new method**

Add after `SHIPPING_TOOLS` and before `parse_calendar_text`:

```python
    def _build_shipping_system_context(self, default_origin: Dict[str, str]) -> str:
        """Build system context for shipping conversation."""
        origin_parts = [
            default_origin.get("name", "Sender"),
            default_origin.get("street1", ""),
            f"{default_origin.get('city', '')}, {default_origin.get('state', '')} {default_origin.get('zip', '')}",
            default_origin.get("phone", ""),
        ]
        origin_text = ", ".join(p for p in origin_parts if p)

        return (
            "You are a shipping assistant helping create shipping labels.\n\n"
            f"Default origin (from) address:\n  {origin_text}\n\n"
            "Rules:\n"
            "- The user is providing DESTINATION (to) address info unless they explicitly say 'from' or 'ship from'\n"
            "- Use set_to_address for destination info, set_from_address ONLY when user explicitly provides origin\n"
            "- Use set_package for weight and dimensions\n"
            "- Use update_field when user wants to correct a specific previously-set field\n"
            "- Use ask_clarification when input is genuinely ambiguous\n"
            "- You can call multiple tools in one response (e.g. set_to_address AND set_package)\n"
            "- Phone numbers: 10 digits only, strip all formatting\n"
            "- State: always 2-letter abbreviation (e.g. CA, TX, NY)\n"
            "- ZIP: always 5 digits\n"
            "- Weight: convert ounces to pounds if needed (16oz = 1lb)\n"
            "- Separate apt/suite/unit into street2 field\n"
            "- If user says '12x8x4' that means length=12, width=8, height=4"
        )

    async def process_shipping_message(
        self,
        message: str,
        history: List[types.Content],
    ) -> Dict[str, Any]:
        """
        Process a shipping message using function calling.
        Returns dict with 'function_calls' list and 'model_response' Content for history.
        """
        # Build the tools config
        tool = types.Tool(function_declarations=[
            types.FunctionDeclaration(**decl) for decl in self.SHIPPING_TOOLS
        ])
        config = types.GenerateContentConfig(
            tools=[tool],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        # Append user message to history
        contents = list(history) + [
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        ]

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini function calling error: {e}")
            return {"function_calls": [], "model_response": None, "error": str(e)}

        # Extract function calls and text from response
        function_calls = []
        text_parts = []

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    function_calls.append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    })
                elif part.text:
                    text_parts.append(part.text)

        return {
            "function_calls": function_calls,
            "text": " ".join(text_parts) if text_parts else None,
            "model_response": response.candidates[0].content if response.candidates else None,
        }

    def build_function_responses(self, function_calls: List[Dict]) -> types.Content:
        """Build a Content with function responses to append to history."""
        parts = []
        for fc in function_calls:
            parts.append(types.Part.from_function_response(
                name=fc["name"],
                response={"status": "ok"},
            ))
        return types.Content(role="user", parts=parts)
```

**Step 2: Verify syntax**

Run: `cd discord-bot && python -c "from services.gemini_client import GeminiClient; print('process_shipping_message' in dir(GeminiClient))"`
Expected: `True`

**Step 3: Commit**

```bash
git add discord-bot/services/gemini_client.py
git commit -m "feat: add process_shipping_message with function calling support"
```

---

### Task 4: Update session initialization in shipping.py

**Files:**
- Modify: `discord-bot/cogs/shipping.py:460-490` (session init + "New Shipment" embed)

**Step 1: Add import for types at top of file**

Add after line 21 (`from services.gemini_client import GeminiClient`):
```python
from google.genai import types as genai_types
```

**Step 2: Update session initialization (lines 460-465)**

Replace the session dict to include `messages` and system context:
```python
        if content_lower in ["ship", "shipping", "new shipment", "create label", "new label"]:
            default_origin = self.config.get("default_origin_address", {})
            system_context = self.gemini._build_shipping_system_context(default_origin) if self.gemini else ""

            self.sessions[user_id] = {
                "step": "awaiting_info",
                "collected": {},
                "missing": [],
                "messages": [
                    genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=system_context)]),
                    genai_types.Content(role="model", parts=[genai_types.Part.from_text(text="Ready to help with your shipment! Tell me the recipient details and package info.")]),
                ],
            }
```

Note: the existing `default_origin` variable assignment that was at line 467 moves up into the session init block since we use it earlier.

**Step 3: Commit**

```bash
git add discord-bot/cogs/shipping.py
git commit -m "feat: add conversation history to shipping session initialization"
```

---

### Task 5: Replace on_message AI parse logic

**Files:**
- Modify: `discord-bot/cogs/shipping.py:492-557` (the `awaiting_info` handler)

This is the core change. Replace the entire `parse_shipping_info` + `"from" in content_lower` block with function calling.

**Step 1: Replace lines 492-557**

Replace from `# Handle active session — AI parse loop` through the `await message.reply(embed=embed)` / `return` for missing fields, with:

```python
        # Handle active session — AI parse loop
        if session and session.get("step") == "awaiting_info":
            if not self.gemini:
                await message.reply("\u274c AI service not available. Please try again later.")
                return

            async with message.channel.typing():
                result = await self.gemini.process_shipping_message(
                    content, session["messages"]
                )

            if result.get("error"):
                await message.reply(f"\u274c AI error: {result['error']}. Please try again.")
                return

            function_calls = result["function_calls"]
            model_response = result["model_response"]

            # Append user message + model response to history
            session["messages"].append(
                genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=content)])
            )
            if model_response:
                session["messages"].append(model_response)

            # Handle ask_clarification — relay question to user
            for fc in function_calls:
                if fc["name"] == "ask_clarification":
                    question = fc["args"].get("question", "Could you clarify?")
                    await message.reply(f"\U0001f914 {question}")
                    # Add function response to history
                    if function_calls:
                        session["messages"].append(
                            self.gemini.build_function_responses(function_calls)
                        )
                    return

            # Process function calls to update session state
            collected = session["collected"]
            for fc in function_calls:
                if fc["name"] == "set_to_address":
                    for key, value in fc["args"].items():
                        collected[f"to_{key}"] = value
                elif fc["name"] == "set_from_address":
                    for key, value in fc["args"].items():
                        collected[f"from_{key}"] = value
                elif fc["name"] == "set_package":
                    for key, value in fc["args"].items():
                        collected[key] = value
                elif fc["name"] == "update_field":
                    field = fc["args"].get("field", "")
                    value = fc["args"].get("value", "")
                    if field in collected or field.startswith(("to_", "from_")) or field in ("weight", "length", "width", "height"):
                        # Convert numeric fields
                        if field in ("weight", "length", "width", "height"):
                            try:
                                value = float(value)
                            except (ValueError, TypeError):
                                pass
                        collected[field] = value

            # Add function responses to history
            if function_calls:
                session["messages"].append(
                    self.gemini.build_function_responses(function_calls)
                )

            # Trim history to last 20 entries to control token cost
            if len(session["messages"]) > 20:
                # Keep first 2 (system context) + last 18
                session["messages"] = session["messages"][:2] + session["messages"][-18:]

            # Determine missing required fields
            required = ["to_name", "to_street", "to_city", "to_state", "to_zip", "to_phone", "weight"]
            missing = [f for f in required if not collected.get(f)]
            has_dimensions = all(collected.get(d) for d in ["length", "width", "height"])

            session["collected"] = collected
            session["missing"] = missing

            if missing:
                prompt_text = self._build_missing_prompt(missing, has_dimensions)
                # Show what we've collected so far
                collected_display = []
                if collected.get("to_name"):
                    collected_display.append(f"**Name:** {collected['to_name']}")
                if collected.get("to_street"):
                    street_display = collected['to_street']
                    if collected.get("to_street2"):
                        street_display += f", {collected['to_street2']}"
                    collected_display.append(f"**Street:** {street_display}")
                if collected.get("to_city") or collected.get("to_state"):
                    city_state = f"{collected.get('to_city', '?')}, {collected.get('to_state', '?')} {collected.get('to_zip', '')}".strip()
                    collected_display.append(f"**Location:** {city_state}")
                if collected.get("to_phone"):
                    collected_display.append(f"**Phone:** {collected['to_phone']}")
                if collected.get("to_email"):
                    collected_display.append(f"**Email:** {collected['to_email']}")
                if collected.get("weight"):
                    collected_display.append(f"**Weight:** {collected['weight']} lbs")
                if has_dimensions:
                    collected_display.append(f"**Dimensions:** {collected.get('length')}x{collected.get('width')}x{collected.get('height')} in")

                # Show from-address if user provided one
                if collected.get("from_street"):
                    from_parts = [collected.get("from_name", ""), collected["from_street"]]
                    if collected.get("from_city"):
                        from_parts.append(f"{collected['from_city']}, {collected.get('from_state', '')} {collected.get('from_zip', '')}")
                    collected_display.append(f"**From:** {', '.join(p for p in from_parts if p)}")

                embed = discord.Embed(
                    title="\U0001f4cb Shipment Info",
                    color=discord.Color.orange()
                )
                if collected_display:
                    embed.add_field(name="Collected so far", value="\n".join(collected_display), inline=False)
                embed.add_field(name="What's missing", value=prompt_text, inline=False)

                await message.reply(embed=embed)
                return
```

The code from `# All required fields collected — move to confirmation` (line 559 onward) stays exactly the same.

**Step 2: Verify no syntax errors**

Run: `cd discord-bot && python -c "from cogs.shipping import ShippingCog; print('import ok')"`

**Step 3: Commit**

```bash
git add discord-bot/cogs/shipping.py
git commit -m "feat: replace JSON extraction with Gemini function calling in on_message handler

Removes the 'from in content_lower' heuristic hack. Gemini now decides which
function to call (set_to_address vs set_from_address) based on full conversation
context. Supports corrections via update_field and ambiguity via ask_clarification."
```

---

### Task 6: Remove dead code from gemini_client.py

**Files:**
- Modify: `discord-bot/services/gemini_client.py`

**Step 1: Remove these methods (they are now unused):**

- `parse_shipping_request()` (lines 24-68) — never called anywhere
- `_fallback_parse_shipping()` (lines 70-128) — only called from parse_shipping_request
- `parse_shipping_info()` (lines 130-225) — replaced by process_shipping_message
- `generate_follow_up_question()` (lines 322-345) — never called anywhere

Keep: `parse_calendar_text()`, `chat_with_context()`, the new `process_shipping_message()`, `build_function_responses()`, `_build_shipping_system_context()`, `SHIPPING_TOOLS`.

**Step 2: Verify nothing breaks**

Run: `cd discord-bot && python -c "from services.gemini_client import GeminiClient; from cogs.shipping import ShippingCog; print('all imports ok')"`

**Step 3: Commit**

```bash
git add discord-bot/services/gemini_client.py
git commit -m "refactor: remove dead code from gemini_client (old JSON parsing methods)"
```

---

### Task 7: Manual smoke test

**Steps:**

1. Start the bot: `cd discord-bot && python bot.py`
2. In the shipping Discord channel, test these scenarios:

**Test A — Basic to-address (should work like before):**
```
User: ship
User: John Doe, 123 Main St, Austin TX 78701, 5125551234, 5lbs 12x8x4
→ Expect: Confirm Shipment Details embed with all fields filled
```

**Test B — To-address first, then from-address (the bug scenario):**
```
User: ship
User: Jane Smith, 456 Oak Ave, Portland OR 97201, 5035551234, 3lbs
User: ship from 789 Pine St, Seattle WA 98101
→ Expect: Jane Smith stays as to-address, Seattle becomes from-address
```

**Test C — Correction:**
```
User: ship
User: John Doe, 123 Main St, Austin TX 78701, 5125551234, 5lbs
→ (before confirming, type:)
User: actually change the zip to 78702
→ Expect: ZIP updates to 78702, all other fields preserved
```

**Test D — Ambiguous input:**
```
User: ship
User: Austin
→ Expect: Either ask_clarification question OR set_to_address with city=Austin and ask for remaining fields
```

**Test E — Piece by piece:**
```
User: ship
User: John Doe
User: 123 Main St Apt 4B
User: Austin TX 78701
User: 5125551234
User: 5 lbs
→ Expect: Each message adds to collected fields, eventually shows confirmation
```

If any test fails, debug and fix before proceeding.

**Step: Commit any fixes**

```bash
git add -A
git commit -m "fix: address issues found during smoke testing"
```
