# 🏄 PaddleForecastAI

Telegram-бот с ИИ-рекомендациями для сап-сёрфинга. Получает прогноз погоды на 5 дней для выбранного места и подсказывает, когда лучше выходить на воду.

Также умеет учитывать рабочие графики друзей и находить общие выходные.

## Что понадобится

- Docker
- PostgreSQL — локальная или удалённая база данных
- Telegram-бот
- API-ключ OpenWeatherMap
- Доступ к AI API с интерфейсом, совместимым с OpenAI API

## 1. Подготовьте Telegram-бота

Создайте бота через [@BotFather](https://t.me/BotFather). Полученный токен укажите в `.env` в переменной `TG_TOKEN`.

## 2. Скачайте проект

Откройте терминал и выполните:

```bash
git clone https://github.com/ATAGAEV95/PaddleForecastAI.git
cd PaddleForecastAI
cp .env.example .env
```

## 3. Подготовьте PostgreSQL

Создайте базу PostgreSQL и укажите строку подключения в `.env` в переменной `DATABASE_URL`. Используется формат `postgresql+asyncpg://user:password@host:5432/database`.

Схема задаётся через `DATABASE_SCHEMA`, по умолчанию — `public`. Таблицы будут созданы автоматически при первом запуске. Если выбрана другая схема, создайте её заранее.

В `DATABASE_URL` укажите адрес БД, доступный из Docker-контейнера: `localhost` внутри контейнера указывает на сам контейнер.

## 4. Заполните `.env`

В файле [.env.example](.env.example) есть комментарии к настройкам:

- `TG_TOKEN` — токен Telegram-бота;
- `WEATHER_API` — ключ OpenWeatherMap;
- `WEATHER_CITY` — город или населённый пункт для прогноза;
- `AI_TOKEN` и `AI_PROVIDER_URL` — токен и адрес API выбранного ИИ-провайдера;
- `DATABASE_URL` и `DATABASE_SCHEMA` — подключение к PostgreSQL и схема.

Не публикуйте `.env`, токен Telegram и ключи API.

## 5. Соберите и запустите бота

Выполните команды из папки проекта:

```bash
docker build -t paddleforecastbot .
docker run -d --restart=unless-stopped --name paddlebot --env-file .env paddleforecastbot
```

После запуска откройте бота в Telegram и отправьте `/start`.

При первом входе бот запросит пароль доступа. Его SHA-256-хеш задаётся в `ACCESS_PASSWORD` в файле `app/core/handlers.py`.

Остановить контейнер можно командой:

```bash
docker stop paddlebot
```

## Команды

- `/start` — регистрация и вход;
- `/get` — ИИ-рекомендации по прогнозу на 5 дней;

