import hashlib
import hmac
import json
import os
import time
import secrets

import database as db
import game_service as game
from sqlalchemy import select, insert
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictInt, StrictStr

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
APP_NAME = os.getenv("APP_NAME", "COCOCHI")
APP_VERSION = "8"
PRODUCTION = os.getenv("APP_ENV") == "production"
DEMO_ENABLED = not PRODUCTION and os.getenv("DEMO_ENABLED", "true").lower() == "true"
STARS_ENABLED = os.getenv("STARS_ENABLED", "false").lower() == "true"
if PRODUCTION and (not BOT_TOKEN or not WEBHOOK_SECRET or not PUBLIC_BASE_URL.startswith("https://")):
    raise RuntimeError("Production requires BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET and HTTPS PUBLIC_BASE_URL")
if os.getenv("REAL_CASHOUT_ENABLED", "false").lower() == "true":
    raise RuntimeError("Real cash-out has no approved settlement implementation")

BOT_USERNAME = ""
BOOT_STATUS = {
    "bot_identity": False,
    "webhook": False,
    "commands": False,
    "menu_button": False,
}



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
        "allowed_updates": ["message", "pre_checkout_query"],
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
                    {"command": "paysupport", "description": "Помощь с оплатой"},
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
    game.initialize()
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


app = FastAPI(title="COCOCHI", version="0.2.0", lifespan=lifespan)

@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

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
    try:
        with db.engine.connect() as conn:
            conn.execute(select(1))
    except Exception:
        raise HTTPException(503, 'Database unavailable') from None
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
        "marketMode": "internal",
        "starsEnabled": STARS_ENABLED,
        "demoEnabled": DEMO_ENABLED,
        "realCashoutEnabled": False,
        "realPaymentsEnabled": False,
    }


class SessionInput(BaseModel):
    initData: str = ""


def validate_init_data(init_data: str, max_age_seconds: int = 3600) -> dict:
    if not init_data:
        if DEMO_ENABLED:
            return {"demo": True, "user": None}
        raise HTTPException(401, "Open this app inside Telegram")
    if not BOT_TOKEN:
        raise HTTPException(503, "Bot token is not configured")
    if len(init_data) > 16384:
        raise HTTPException(401, "Invalid Telegram data")
    entries = parse_qsl(init_data, keep_blank_values=True)
    pairs = dict(entries)
    if len(entries) != len(pairs):
        raise HTTPException(401, "Duplicate Telegram fields")
    received_hash = pairs.pop("hash", "")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not received_hash or not hmac.compare_digest(expected, received_hash):
        raise HTTPException(401, "Invalid Telegram signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if auth_date <= 0 or auth_date > int(time.time()) + 30 or int(time.time()) - auth_date > max_age_seconds:
            raise ValueError()
        user = json.loads(pairs.get("user", "null"))
        if not isinstance(user, dict) or type(user.get("id")) is not int or not 0 < user["id"] < 2**63:
            raise ValueError()
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid Telegram identity or auth date") from None
    # Ignore initDataUnsafe; only signed fields reach this point.
    return {"demo": False, "user": user, "startParam": pairs.get("start_param", "")}


def authenticated(request: Request) -> int:
    token = request.cookies.get("cocochi_session", "")
    digest = hashlib.sha256(token.encode()).hexdigest()
    with db.engine.connect() as conn:
        session = conn.execute(select(db.sessions).where(db.sessions.c.token_hash == digest)).mappings().first()
    if not session or session['expires_at'] < int(time.time()):
        raise HTTPException(401, "Session expired; reopen the app")
    if request.method != 'GET':
        # Browser cross-site requests cannot supply this header without preflight;
        # no CORS middleware permits a foreign origin.
        if request.headers.get('x-cocochi-request') != '1':
            raise HTTPException(403, "Missing request guard")
        origin = request.headers.get('origin')
        expected = PUBLIC_BASE_URL or str(request.base_url).rstrip('/')
        if origin and origin.rstrip('/') != expected:
            raise HTTPException(403, "Invalid origin")
    return session['user_id']


@app.post("/api/session")
async def session(data: SessionInput, request: Request):
    result = validate_init_data(data.initData)
    token = secrets.token_urlsafe(32)
    ts = int(time.time())
    user = result['user']
    if result['demo']:
        try:
            uid = authenticated(request)
        except HTTPException:
            uid = -secrets.randbelow(2**52) - 1
        if uid > 0:
            uid = -secrets.randbelow(2**52) - 1
        user = {'id': uid, 'first_name': 'Demo Player'}
    with db.transaction() as conn:
        game.ensure_user(conn, user, result.get('startParam', ''))
        conn.execute(insert(db.sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user['id'], expires_at=ts + 86400))
    response = JSONResponse(result)
    response.set_cookie('cocochi_session', token, max_age=86400, httponly=True, secure=PRODUCTION, samesite='lax')
    response.headers['Cache-Control'] = 'no-store'
    return response


class ActionInput(BaseModel):
    action: str
    value: StrictStr | StrictInt | None = None


def idempotency(request):
    key = request.headers.get('idempotency-key', '')
    if not 16 <= len(key) <= 80 or not all(c.isalnum() or c in '-_' for c in key):
        raise HTTPException(400, 'Valid Idempotency-Key required')
    return key


@app.get('/api/game')
def game_state(request: Request):
    uid = authenticated(request)
    with db.transaction() as conn:
        game.row(conn, db.balances, uid, True)
        return game.snapshot(conn, uid, int(time.time()))


@app.post('/api/game/action')
def game_action(data: ActionInput, request: Request):
    return game.act(authenticated(request), data.action, data.value, idempotency(request))


class OrderInput(BaseModel):
    sku: str


@app.post('/api/orders')
async def create_order(data: OrderInput, request: Request):
    uid = authenticated(request)
    if not STARS_ENABLED or not BOT_TOKEN:
        raise HTTPException(503, 'Stars payments are not enabled')
    order = game.new_order(uid, data.sku, idempotency(request))
    if order['status'] != 'pending':
        raise HTTPException(409, 'Order already paid')
    try:
        result = await tg_call('createInvoiceLink', {'title': 'COCOCHI Eggs', 'description': str(order['eggs']) + ' internal game eggs. No cash value.', 'payload': order['payload'], 'provider_token': '', 'currency': 'XTR', 'prices': [{'label': order['sku'], 'amount': order['stars']}]})
    except Exception:
        raise HTTPException(502, 'Invoice service unavailable; retry with the same request key') from None
    return {'orderId': order['id'], 'invoiceUrl': result['result']}


@app.get('/api/orders')
def order_history(request: Request):
    uid = authenticated(request)
    with db.engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(db.orders).where(db.orders.c.user_id == uid).order_by(db.orders.c.created_at.desc()).limit(50)).mappings()]


@app.post('/api/withdrawals')
def withdrawal(request: Request):
    authenticated(request)
    raise HTTPException(403, 'Real cash-out is disabled. Eggs and coins have no redeemable value.')


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
    if not WEBHOOK_SECRET or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Bad webhook secret")

    update = await request.json()
    checkout = update.get('pre_checkout_query')
    if checkout:
        ok = False
        try:
            if not STARS_ENABLED:
                raise HTTPException(403, 'Payments disabled')
            game.reserve_checkout(checkout.get('from', {}).get('id'), checkout)
            ok = True
        except HTTPException:
            pass
        payload = {'pre_checkout_query_id': checkout['id'], 'ok': ok}
        if not ok:
            payload['error_message'] = 'Order unavailable. Please create a new order.'
        await tg_call('answerPreCheckoutQuery', payload)
        return {'ok': True}
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = user.get("id")

    if message.get('successful_payment'):
        game.credit_payment(user_id, message['successful_payment'])
        return {'ok': True}
    if text == '/paysupport' and chat_id:
        await tg_call('sendMessage', {'chat_id': chat_id, 'text': 'Payment support: send your order ID from the COCOCHI payment history to the bot owner. Never send private keys or passwords.'})
        return {'ok': True}

    if not chat_id:
        return {"ok": True}

    if text.startswith("/start") or text.startswith("/play"):
        referrer = extract_referrer(text)
        if referrer and user_id and referrer != user_id:
            with db.transaction() as conn:
                if db.engine.dialect.name == 'postgresql':
                    from sqlalchemy import func
                    conn.execute(select(func.pg_advisory_xact_lock(user_id)))
                if not conn.execute(select(db.users.c.id).where(db.users.c.id == user_id)).first() and not conn.execute(select(db.referral_intents.c.user_id).where(db.referral_intents.c.user_id == user_id)).first():
                    conn.execute(insert(db.referral_intents).values(user_id=user_id, referrer_id=referrer, created_at=int(time.time())))
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
