import hashlib
import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
APP_NAME = os.getenv("APP_NAME", "COCOCHI")

BOT_USERNAME = ""
PENDING_REFERRALS: dict[int, int] = {}

def telegram_api(method: str) -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

async def tg_call(method: str, payload: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(telegram_api(method), json=payload or {})
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body}")
        return body

async def refresh_bot_identity() -> None:
    global BOT_USERNAME
    if not BOT_TOKEN:
        return
    try:
        body = await tg_call("getMe")
        BOT_USERNAME = body.get("result", {}).get("username", "") or ""
    except Exception:
        BOT_USERNAME = ""

async def configure_webhook() -> None:
    if not BOT_TOKEN or not PUBLIC_BASE_URL:
        return
    payload = {
        "url": f"{PUBLIC_BASE_URL}/telegram/webhook",
        "allowed_updates": ["message"],
        "drop_pending_updates": False,
    }
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    try:
        await tg_call("setWebhook", payload)
    except Exception:
        pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh_bot_identity()
    await configure_webhook()
    yield

app = FastAPI(title="COCOCHI MVP", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    return RedirectResponse("/app")

@app.get("/app")
async def mini_app():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/healthz")
async def health():
    return {
        "ok": True,
        "app": APP_NAME,
        "bot_configured": bool(BOT_TOKEN),
        "public_base_url_configured": bool(PUBLIC_BASE_URL),
    }

@app.get("/api/config")
async def config(request: Request):
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return {
        "appName": APP_NAME,
        "botUsername": BOT_USERNAME,
        "baseUrl": base,
        "marketMode": "demo",
        "realPaymentsEnabled": False,
    }

class SessionInput(BaseModel):
    initData: str = ""

def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> dict:
    if not init_data:
        return {"demo": True, "user": None}
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Bot token is not configured")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing Telegram hash")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram signature")

    auth_date = int(pairs.get("auth_date", "0") or "0")
    if auth_date and abs(int(time.time()) - auth_date) > max_age_seconds:
        raise HTTPException(status_code=401, detail="Telegram session expired")

    user = None
    if pairs.get("user"):
        try:
            user = json.loads(pairs["user"])
        except json.JSONDecodeError:
            user = None

    return {
        "demo": False,
        "user": user,
        "queryId": pairs.get("query_id"),
        "startParam": pairs.get("start_param"),
    }

@app.post("/api/session")
async def session(data: SessionInput):
    result = validate_init_data(data.initData)
    user = result.get("user") or {}
    user_id = user.get("id")
    if user_id and user_id in PENDING_REFERRALS:
        result["referrerId"] = PENDING_REFERRALS.get(user_id)
    return result

@app.get("/tonconnect-manifest.json")
async def ton_manifest(request: Request):
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "url": base,
            "name": APP_NAME,
            "iconUrl": f"{base}/static/cocochi-icon.svg",
            "termsOfUseUrl": f"{base}/app",
            "privacyPolicyUrl": f"{base}/app",
        }
    )

def extract_referrer(text: str) -> int | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    arg = parts[1].strip()
    if not arg.startswith("ref_"):
        return None
    try:
        return int(arg[4:])
    except ValueError:
        return None

@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Bad webhook secret")

    update = await request.json()
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = user.get("id")

    if not chat_id:
        return {"ok": True}

    if text.startswith("/start") or text.startswith("/play"):
        referrer = extract_referrer(text)
        if referrer and user_id and referrer != user_id:
            PENDING_REFERRALS[int(user_id)] = int(referrer)

        base = PUBLIC_BASE_URL
        if not base:
            await tg_call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "COCOCHI ещё не получила PUBLIC_BASE_URL на сервере.",
                },
            )
            return {"ok": True}

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🐔 Играть в COCOCHI",
                        "web_app": {"url": f"{base}/app"},
                    }
                ]
            ]
        }
        await tg_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": (
                    "🐔 COCOCHI — твоя экономическая тамагочи-курица.\n\n"
                    "Корми, пои, чисти, собирай яйца и прокачивай её.\n"
                    "Это MVP: реальные покупки и продажи пока отключены."
                ),
                "reply_markup": keyboard,
            },
        )
    return {"ok": True}
