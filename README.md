# COCOCHI

Telegram Mini App с интерактивной WebGL-курицей и серверной игровой экономикой.

- Уход, производство (с учётом офлайна до 6 часов), уровни, гардероб.
- Внутренний рынок: яйца → монеты; монеты → улучшение курятника и участие в Egg Rush.
- Ежедневные награды, проверяемые задания, ежедневное событие, приглашения.
- Постоянная БД, транзакции, ledger, идемпотентные команды и история.
- Telegram Stars: заказ → invoice → pre-checkout → подтверждённый платёж → начисление.
- TON Connect: подключение, восстановление сессии, адрес/сеть, отключение.

**Яйца и монеты — игровые единицы без денежного эквивалента. Вывод и mainnet-переводы не включены.**

## Локально

Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Откройте `/app` на локальном сервере. По умолчанию работает демосессия с серверным сохранением в `data/game.sqlite3`. SQLite используется только для разработки. Для PostgreSQL задайте `DATABASE_URL`. Файл `.env` сам по себе не загружается: используйте `uvicorn --env-file .env` либо экспортируйте переменные.

```bash
python -m unittest discover -s tests -v
TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/cocochi_qa python -m unittest discover -s tests -v
python scripts/simulate_economy.py
```

Тестовый PostgreSQL должен быть отдельной БД без рабочих данных. Тесты создают тестовые аккаунты.

## Render

`render.yaml` содержит Web Service и **платную постоянную PostgreSQL**. Blueprint не был применён автоматически: проверьте стоимость в Render. Для существующего сервиса можно вручную подключить собственную постоянную PostgreSQL без создания второго сервиса.

Build: `pip install -r requirements.txt`

Start: `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers`

Переменные:

| Имя | Значение |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Internal Connection String постоянной PostgreSQL |
| `BOT_TOKEN` | Токен бота, вводить только в настройках секретов Render |
| `TELEGRAM_WEBHOOK_SECRET` | Случайный секрет webhook; Blueprint генерирует его |
| `PUBLIC_BASE_URL` | Необязательно на Render: берётся `RENDER_EXTERNAL_URL`; для custom domain задать явно |
| `DEMO_ENABLED` | `false` |
| `STARS_ENABLED` | `false` до проверки реального Stars invoice и поддержки возвратов |
| `REAL_CASHOUT_ENABLED` | `false`; включение не поддерживается |

При первом запуске создаётся схема v1. Приложение отказывается запускать production на SQLite, без bot token, webhook secret или HTTPS URL. `/healthz` проверяет доступ к БД, а также показывает фактический результат настройки Telegram. Сам по себе `ok=true` не означает, что Telegram boot-флаги успешны.

На старте вызываются `getMe`, `setWebhook`, `setMyCommands`, `setChatMenuButton`. Разрешены updates `message` и `pre_checkout_query`. В BotFather настройте Main Mini App на HTTPS-адрес `/app` и при необходимости домен. Проверьте `/start`, `/play`, `/paysupport`, меню и `startapp=ref_<id>` на настоящем аккаунте. Эти внешние действия без токена здесь не выполнялись.

## Платежи и возвраты

Цифровые товары продаются только за XTR. Фронтенд никогда не начисляет покупку по callback invoice. Сверяются payload, владелец, валюта, сумма и уникальный charge ID. Повторный `successful_payment` не начисляет товар второй раз. История заказов доступна в профиле.

`python scripts/refund_order.py ORDER_ID` — операторский возврат через `refundStarPayment`. Сначала резервируются купленные яйца. Если яйца уже потрачены, нужен отдельный разбор обращения. При неизвестном результате Telegram заказ остаётся `refund_pending`: нельзя автоматически повторять или освобождать резерв без сверки с провайдером. Команда не является публичным endpoint. Перед включением продаж назначьте ответственного за `/paysupport` и обработку возвратов.

## Безопасность и ограничения

- Telegram initData проверяется HMAC, сроком и обязательным положительным Telegram ID. `initDataUnsafe` не используется.
- Авторизация: случайная HttpOnly cookie, хеш сессии в БД, 24 часа. В production cookie Secure. Мутации проверяют origin и пользовательский заголовок.
- Серверные транзакции и блокировки защищают баланс. До 30 успешных игровых команд в минуту, 10 заказов в сутки, 200 проданных яиц в сутки UTC.
- Ссылку приглашения фиксируем только при первом подтверждённом запуске. Self-referral, изменение родителя и циклы исключены. Приглашения по `/start` фиксируются доверенным webhook; `startapp` — подписанным initData.
- Клиентское подключение TON — не доказательство владения адресом для сервера. Нет серверного `ton_proof`, treasury и blockchain settlement. Есть добровольный перевод 0.01 тестового TON себе через TON Connect: разрешён только chain −3 и требует подписи кошелька. Подтверждение блокчейна не отслеживается; возврат BOC не отображается как финальное подтверждение. Этот flow не проверялся на настоящем кошельке.
- Для production дополнительно нужны резервные копии PostgreSQL, мониторинг, платёжная поддержка и внешняя проверка Telegram/Stars/wallet. Антифрод сейчас ограничен валидацией, лимитами и аудитом; полноценного Sybil detection нет.
- Первый schema bootstrap рассчитан на один процесс. Для следующих изменений схемы нужны явные версии миграций и резервная копия. Горизонтальный запуск первого bootstrap не предусмотрен.
- WebGL имеет статический fallback и ограниченный pixel ratio; Telegram SDK и TON Connect используют внешние официальные/CDN ресурсы. Three.js закреплён и включён локально с MIT license.

Расчёты: [ECONOMY.md](ECONOMY.md). Выполненные проверки: [VALIDATION.md](VALIDATION.md).
