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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
APP_NAME = os.getenv("APP_NAME", "COCOCHI")
APP_VERSION = "7"

BOT_USERNAME = ""
BOOT_STATUS = {
    "bot_identity": False,
    "webhook": False,
    "commands": False,
    "menu_button": False,
}
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
            raise RuntimeError("Telegram API returned ok=false")
        return body


async def refresh_bot_identity() -> None:
    global BOT_USERNAME
    if not BOT_TOKEN:
        print("COCOCHI_BOOT bot_identity=SKIP no_token", flush=True)
        return
    try:
        body = await tg_call("getMe")
        BOT_USERNAME = body.get("result", {}).get("username", "") or ""
        BOOT_STATUS["bot_identity"] = bool(BOT_USERNAME)
        print(
            f"COCOCHI_BOOT bot_identity={'OK' if BOT_USERNAME else 'EMPTY'} "
            f"username=@{BOT_USERNAME or 'unknown'}",
            flush=True,
        )
    except Exception:
        BOT_USERNAME = ""
        print("COCOCHI_BOOT bot_identity=FAILED", flush=True)


async def configure_webhook() -> None:
    if not BOT_TOKEN or not PUBLIC_BASE_URL:
        print("COCOCHI_BOOT webhook=SKIP missing_config", flush=True)
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
        BOOT_STATUS["webhook"] = True
        print(
            f"COCOCHI_BOOT webhook=OK url={PUBLIC_BASE_URL}/telegram/webhook",
            flush=True,
        )
    except Exception:
        print("COCOCHI_BOOT webhook=FAILED", flush=True)


def app_url(base: str) -> str:
    return f"{base}/app?v={APP_VERSION}"


async def configure_bot_ui() -> None:
    if not BOT_TOKEN:
        print("COCOCHI_BOOT commands=SKIP no_token", flush=True)
        return
    try:
        await tg_call(
            "setMyCommands",
            {
                "commands": [
                    {"command": "start", "description": "Открыть COCOCHI"},
                    {"command": "play", "description": "Играть в COCOCHI"},
                ]
            },
        )
        BOOT_STATUS["commands"] = True
        print("COCOCHI_BOOT commands=OK", flush=True)
    except Exception:
        print("COCOCHI_BOOT commands=FAILED", flush=True)

    if not PUBLIC_BASE_URL:
        print("COCOCHI_BOOT menu_button=SKIP no_public_url", flush=True)
        return

    try:
        await tg_call(
            "setChatMenuButton",
            {
                "menu_button": {
                    "type": "web_app",
                    "text": "Играть в COCOCHI",
                    "web_app": {"url": app_url(PUBLIC_BASE_URL)},
                }
            },
        )
        BOOT_STATUS["menu_button"] = True
        print(f"COCOCHI_BOOT menu_button=OK url={app_url(PUBLIC_BASE_URL)}", flush=True)
    except Exception:
        print("COCOCHI_BOOT menu_button=FAILED", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await refresh_bot_identity()
    await configure_webhook()
    await configure_bot_ui()
    print(
        "COCOCHI_BOOT ready "
        f"bot={BOOT_STATUS['bot_identity']} "
        f"webhook={BOOT_STATUS['webhook']} "
        f"commands={BOOT_STATUS['commands']} "
        f"menu={BOOT_STATUS['menu_button']} version={APP_VERSION}",
        flush=True,
    )
    yield


app = FastAPI(title="COCOCHI MVP", version="0.1.4", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    return RedirectResponse(f"/app?v={APP_VERSION}")


@app.api_route("/app", methods=["GET", "HEAD"])
async def mini_app(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/html")
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/healthz")
async def health():
    home = STATIC_DIR / "cocochi-home.webp"
    market = STATIC_DIR / "cocochi-market.webp"
    return {
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "bot_configured": bool(BOT_TOKEN),
        "public_base_url_configured": bool(PUBLIC_BASE_URL),
        "bot_username": BOT_USERNAME or None,
        "telegram": BOOT_STATUS,
        "assets": {
            "home_bytes": home.stat().st_size if home.exists() else 0,
            "market_bytes": market.stat().st_size if market.exists() else 0,
        },
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
            "termsOfUseUrl": app_url(base),
            "privacyPolicyUrl": app_url(base),
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
                        "web_app": {"url": app_url(base)},
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
