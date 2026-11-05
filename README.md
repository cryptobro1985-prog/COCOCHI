# COCOCHI MVP

Базовый Telegram Mini App прототип COCOCHI.

Что уже есть:
- Telegram Mini App UI, адаптивный мобильный интерфейс.
- Первый запуск с выбором RU / EN.
- Кликабельные: собрать яйца, покормить, напоить, почистить, апгрейд.
- Демо-рынок с buy/sell limits.
- Реферальная ссылка и Telegram share.
- TON Connect (только подключение кошелька; реальные переводы отключены).
- Telegram webhook: `/start` и `/play` отправляют кнопку `Играть в COCOCHI`.
- Проверка подписи Telegram `initData`.
- GitHub Actions smoke test.
- Render blueprint.

## Важно

В коде НЕТ bot token. Он должен быть только в переменной окружения `BOT_TOKEN`.

Этот MVP не выполняет реальные покупки/продажи TON и не хранит реальные деньги.
Игровое состояние MVP хранится на устройстве пользователя (localStorage). Для production нужна серверная БД.

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export BOT_TOKEN="..."
export PUBLIC_BASE_URL="https://example.com"
export TELEGRAM_WEBHOOK_SECRET="..."
uvicorn server:app --reload --port 8000
```

Открыть: `http://127.0.0.1:8000/app`

## Render

1. Создать Web Service из репозитория либо применить `render.yaml`.
2. Задать `BOT_TOKEN`.
3. Задать `PUBLIC_BASE_URL` равным фактическому HTTPS URL сервиса.
4. Задать случайный `TELEGRAM_WEBHOOK_SECRET`.
5. После старта приложение само вызывает `setWebhook`.

## Следующий технический этап

- PostgreSQL: серверное состояние курицы, лимиты, рефералы, история.
- Server-authoritative production/egg accounting.
- Реальный marketplace только после отдельной модели расчётов и правил.
- Production TON transaction flow отдельно от wallet-connect.
