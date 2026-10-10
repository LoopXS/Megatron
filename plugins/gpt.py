"""
✘ Commands Available -

• `{i}gpt <prompt>`
    Chat with AshnaAI (keeps conversation history).

• `{i}gptmodel` | `{i}gptmodel <id>`
    Show current model or switch model.

• `{i}gptmodels`
    List live AshnaAI models.

• `{i}gptnew`
    Start a fresh conversation.

• `{i}gptweb on|off`
    Toggle web search.

• `{i}gptdeep on|off`
    Toggle deep-think.

• `{i}gpteffort low|medium|high|xhigh|max`
    Set reasoning effort.

• `{i}gptinfo`
    Show current GPT config.

Cookie can be overridden with DB key `ASHNA_WEB`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from . import LOGS, eod, eor, get_pstring, udB, heartless_cmd

# ---------------------------------------------------------------------------
# CONFIG (AshnaAI / api.ashna.ai)
# ---------------------------------------------------------------------------
BASE_API = "https://api.ashna.ai"
BASE_APP = "https://app.ashna.ai"

_DEFAULT_ASHNA_WEB = (
    "eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwia2lkIjoiQnM5VERUUVVMby1wOFpPVWx2RThjcjlBc1ZQZzA5dGFxSkpaNk1xem9hOUk4WHVMdHhGNTBHUmZTYjlyUVNEWXBiV2lWRHVXVjRCTWtabnJFWnlYSUEifQ"
    "..dVdR_bNziay78Tb7Qfj4xw.gwjgY6R7Oq95n1vKTThKSL2mjkTX-YjQ42QlMuz5Atq5PDCu6oqo8rtTKTmEriSBO3UF-ztRn4DqjM1_ZCZIl_gFQoF2B1yZwtK3-hY3vbfp8H-13CX43DwTrCAHqEoVT_q_iaqp2vZl6N8XT7INTB3sYZH7WV8hwoWtp7W6z8jobC0Za5KZPi-TU7h-fD1Lx-GlLNGTP-0_1hbIeqObMuMN2roqioTGZbnFrSCIV27WRW4fZrlHhZq5yBr9oVlLQuuL6CnEpIyFMzV5z5fDMk2YNm7YEO-dGYM2giyU30l5a_bFfMbyUmXcT9uXAHFe5KfLtHUemE6pgRQ-J16o-N0sG3p7oWFby1cb4VtrJ6inenTvguz_RzbUUxsSiFmCq7Gp5hjtVLaWkEog2GCOCaXDSDndpEhN4nWTx4RafB4tkGBSwU3_s826R4P4a359oCHWU1xJXljiCPr35Z9aeV5YtKGRpkhp0FHO0lvlRzct383Wqcn2TVHndNbpRS8d98MjfYN05LH7tkDJ88SKZ8D8fmCmjzguUhlzYkcmFfPhTVYOT9RAQkCpjGRe9NoqIyas8fh3CDu23fIrZ7S4ny78IKOjGf-j9UophaEXVvNJ3OSN4-4rMbjIPumO-I9g.epMNfbdtYYiN6H4bBcKKu1fFZWzM8UNzCt2giB682kk"
)

USER_ID = "6aaecd4271e78d89dad0e185"
DESKTOP_LOGIN_INSTANCE_ID = "k73G2cB4CFDFLiZSBf1y0SvIzBHhCkAJvOaonKyMThw"
USER_NAME = "Akay"
USER_EMAIL = "akayonfire3@gmail.com"

FALLBACK_MODELS = [
    "ashna-x1",
    "gpt-6-astra",
    "gpt-5.5",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.4-thinking",
    "gpt-5.4",
    "gpt-5.3-codex",
    "gpt-5.2",
    "gpt-5.2-thinking",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4o",
    "gpt-4o-mini",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "kimi-k2.5-thinking",
    "grok-4.3",
]

WEB_MODE = {
    "id": "web",
    "rank": 12,
    "label": "Web",
    "icon": "<svg/>",
    "description": "Represents global web access and internet-related services.",
    "reasoningCapability": {
        "mode": "unsupported",
        "supportedEfforts": [],
        "canDisable": False,
        "defaultEnabled": False,
    },
}

# Per-owner runtime chat state
_STATE: Dict[str, Any] = {
    "history": [],
    "chat_id": uuid.uuid4().hex[:24],
    "model": "gpt-6-astra",
    "web": False,
    "deep": False,
    "effort": "low",
}


def _cookie() -> str:
    return (udB.get_key("ASHNA_WEB") or _DEFAULT_ASHNA_WEB).strip()


def _cookies() -> Dict[str, str]:
    return {"ashna-web": _cookie()}


def _common_headers() -> Dict[str, str]:
    return {
        "accept": "application/json",
        "origin": BASE_APP,
        "referer": f"{BASE_APP}/",
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
        ),
    }


def _build_model_obj(model_id: str, reasoning_effort: str = "low") -> Dict[str, Any]:
    return {
        "id": model_id,
        "rank": 3,
        "label": model_id,
        "category": "Tops",
        "isResponsesModel": True,
        "icon": "/images/gpt-4.webp",
        "description": f"{model_id} via AshnaAI",
        "reasoningNotice": "",
        "creatorName": "",
        "toolCallAllowed": True,
        "webSearchAllowed": True,
        "deepThinkAllowed": True,
        "reasoningEnabled": reasoning_effort not in (None, "none"),
        "reasoningEffort": reasoning_effort,
        "contextLimit": 1050000,
        "imageQueryAllowed": True,
        "keywords": [model_id],
        "chatApi": "/api/chat",
        "reasoningCapability": {
            "mode": "optional",
            "supportedEfforts": ["low", "medium", "high", "xhigh", "max"],
            "canDisable": False,
            "defaultEnabled": True,
            "defaultEffort": "low",
        },
    }


def _build_session_obj() -> Dict[str, Any]:
    return {
        "user": {
            "name": USER_NAME,
            "email": USER_EMAIL,
            "image": None,
            "id": USER_ID,
            "desktopLoginInstanceId": DESKTOP_LOGIN_INSTANCE_ID,
        },
        "expires": "2026-12-18T19:07:01.843Z",
        "desktopLoginInstanceId": DESKTOP_LOGIN_INSTANCE_ID,
    }


def _to_ai_sdk_messages(history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out = []
    for msg in history:
        out.append(
            {
                "role": msg["role"],
                "parts": [{"type": "text", "text": msg["content"]}],
                "id": uuid.uuid4().hex[:21],
            }
        )
    return out


def _build_chat_payload(
    chat_id: str,
    messages: List[Dict[str, Any]],
    model_id: str,
    web: bool = False,
    deep: bool = False,
    reasoning_effort: str = "low",
) -> Dict[str, Any]:
    model = _build_model_obj(model_id, reasoning_effort=reasoning_effort)
    return {
        "chatId": chat_id,
        "id": f"{chat_id}-https://api.ashna.ai/api/chat",
        "session": _build_session_obj(),
        "webAccessEnabled": web,
        "advanceModelEnabled": False,
        "temporaryChatEnabled": False,
        "deepThinkEnabled": deep,
        "countChatWithoutAuth": 0,
        "currentSelectedWebMode": WEB_MODE,
        "currentlySelectedBotModel": model,
        "favouriteModel": [],
        "messages": messages,
        "routePath": f"/chat/{chat_id}?agent={model_id}",
        "toolExecutionCapabilities": {
            "availableExecutionLocations": ["CLIENT_BROWSER"]
        },
    }


async def fetch_models() -> List[Tuple[str, str]]:
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(
            headers={**_common_headers(), "content-type": "application/json"},
            cookies=_cookies(),
            timeout=timeout,
        ) as session:
            async with session.post(
                f"{BASE_API}/api/health/ai-model/stats", json={}
            ) as resp:
                resp.raise_for_status()
                data = (await resp.json()).get("data") or []
                return [(m["modelId"], m.get("status", "?")) for m in data]
    except Exception as er:
        LOGS.exception(er)
        return [(m, "?") for m in FALLBACK_MODELS]


async def stream_chat(
    history: List[Dict[str, str]],
    model_id: str,
    web: bool = False,
    deep: bool = False,
    reasoning_effort: str = "low",
    chat_id: Optional[str] = None,
) -> str:
    chat_id = chat_id or uuid.uuid4().hex[:24]
    payload = _build_chat_payload(
        chat_id,
        _to_ai_sdk_messages(history),
        model_id,
        web=web,
        deep=deep,
        reasoning_effort=reasoning_effort,
    )
    headers = {
        "accept": "text/event-stream",
        "content-type": "text/plain",
        "origin": BASE_APP,
        "referer": f"{BASE_APP}/",
        "user-agent": "ai-sdk/6.0.20 runtime/browser",
    }
    timeout = aiohttp.ClientTimeout(total=300)
    chunks: List[str] = []
    async with aiohttp.ClientSession(
        headers=headers, cookies=_cookies(), timeout=timeout
    ) as session:
        async with session.post(
            f"{BASE_API}/api/chat", data=json.dumps(payload)
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body[:300]}")
            while True:
                raw = await resp.content.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") in ("text-delta", "text") and obj.get("delta"):
                    piece = obj["delta"]
                else:
                    piece = obj.get("delta") or obj.get("text") or obj.get("content")
                if piece:
                    chunks.append(str(piece))
    return "".join(chunks)


def _bool_arg(text: str) -> bool:
    return text.lower() in ("on", "1", "true", "yes", "enable", "enabled")


def _trim(text: str, limit: int = 3900) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n\n…(truncated)"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@heartless_cmd(pattern="gpt( (.*)|$)")
async def gpt_chat(event):
    query = (event.pattern_match.group(2) or "").strip()
    if not query and event.is_reply:
        reply = await event.get_reply_message()
        query = (reply.text or "").strip() if reply else ""
    if not query:
        hndlr = udB.get_key("HNDLR") or "."
        return await eod(
            event,
            f"`Usage:` `{hndlr}gpt <prompt>`\n"
            f"Also: `{hndlr}gptmodel`, `{hndlr}gptmodels`, `{hndlr}gptnew`, "
            f"`{hndlr}gptweb`, `{hndlr}gptdeep`, `{hndlr}gpteffort`, `{hndlr}gptinfo`",
        )

    status = await eor(event, get_pstring("com_1", "load"))
    history: List[Dict[str, str]] = _STATE["history"]
    history.append({"role": "user", "content": query})
    try:
        answer = await stream_chat(
            history,
            _STATE["model"],
            web=_STATE["web"],
            deep=_STATE["deep"],
            reasoning_effort=_STATE["effort"],
            chat_id=_STATE["chat_id"],
        )
        if not answer:
            raise RuntimeError("Empty response from AshnaAI.")
        history.append({"role": "assistant", "content": answer})
        # Keep history bounded
        if len(history) > 40:
            _STATE["history"] = history[-40:]
            history = _STATE["history"]
        text = (
            f"**Qᴜᴇʀʏ**\n`{query}`\n\n"
            f"**Gᴘᴛ** (`{_STATE['model']}`)\n{_trim(answer)}"
        )
        await status.edit(_trim(text), link_preview=False)
    except Exception as er:
        LOGS.exception(er)
        if history and history[-1].get("role") == "user":
            history.pop()
        await status.edit(f"**Gᴘᴛ Eʀʀᴏʀ:** `{er}`")


@heartless_cmd(pattern="gptmodels$")
async def gpt_models(event):
    status = await eor(event, "`Fetching models…`")
    models = await fetch_models()
    lines = ["**Aᴠᴀɪʟᴀʙʟᴇ Mᴏᴅᴇʟs**\n"]
    for mid, st in models[:60]:
        mark = "✅" if st == "healthy" else "•"
        lines.append(f"{mark} `{mid}` — `{st}`")
    await status.edit("\n".join(lines)[:4000])


@heartless_cmd(pattern="gptmodel( (.*)|$)")
async def gpt_model(event):
    arg = (event.pattern_match.group(2) or "").strip()
    hndlr = udB.get_key("HNDLR") or "."
    if not arg:
        return await eor(
            event,
            f"**Cᴜʀʀᴇɴᴛ Mᴏᴅᴇʟ:** `{_STATE['model']}`\n"
            f"Use `{hndlr}gptmodel <id>` to switch.\n"
            f"See `{hndlr}gptmodels` for the list.",
        )
    _STATE["model"] = arg
    await eor(event, f"**Mᴏᴅᴇʟ →** `{arg}`")


@heartless_cmd(pattern="gptnew$")
async def gpt_new(event):
    _STATE["history"] = []
    _STATE["chat_id"] = uuid.uuid4().hex[:24]
    await eor(event, "**Nᴇᴡ ᴄᴏɴᴠᴇʀsᴀᴛɪᴏɴ** started.")


@heartless_cmd(pattern="gptweb( (.*)|$)")
async def gpt_web(event):
    arg = (event.pattern_match.group(2) or "").strip()
    if not arg:
        return await eor(event, f"**Wᴇʙ:** `{_STATE['web']}` — use `on`/`off`")
    _STATE["web"] = _bool_arg(arg)
    await eor(event, f"**Wᴇʙ →** `{_STATE['web']}`")


@heartless_cmd(pattern="gptdeep( (.*)|$)")
async def gpt_deep(event):
    arg = (event.pattern_match.group(2) or "").strip()
    if not arg:
        return await eor(event, f"**Dᴇᴇᴘ:** `{_STATE['deep']}` — use `on`/`off`")
    _STATE["deep"] = _bool_arg(arg)
    await eor(event, f"**Dᴇᴇᴘ →** `{_STATE['deep']}`")


@heartless_cmd(pattern="gpteffort( (.*)|$)")
async def gpt_effort(event):
    arg = (event.pattern_match.group(2) or "").strip().lower()
    allowed = ("low", "medium", "high", "xhigh", "max")
    if arg not in allowed:
        return await eor(
            event,
            f"**Eғғᴏʀᴛ:** `{_STATE['effort']}`\n"
            f"Use one of: `{' | '.join(allowed)}`",
        )
    _STATE["effort"] = arg
    await eor(event, f"**Eғғᴏʀᴛ →** `{arg}`")


@heartless_cmd(pattern="gptinfo$")
async def gpt_info(event):
    await eor(
        event,
        "**Gᴘᴛ Cᴏɴғɪɢ**\n\n"
        f"**Model:** `{_STATE['model']}`\n"
        f"**Web:** `{_STATE['web']}`\n"
        f"**Deep:** `{_STATE['deep']}`\n"
        f"**Effort:** `{_STATE['effort']}`\n"
        f"**Chat ID:** `{_STATE['chat_id']}`\n"
        f"**History:** `{len(_STATE['history'])}` messages",
    )
