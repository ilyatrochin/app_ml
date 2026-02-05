# Web UI для записи операций в Google Sheets

Приложение поднимает веб-форму и сохраняет данные на лист **"Операции"** в Google Sheets.

## Поля формы
- Дата
- Расчетные центры *(выпадающий список с листа "Настройка")*
- Раздел ДДС *(выпадающий список с листа "Настройка")*
- Дата Затраты (ОПУ)
- Стоимость
- Контрагент
- За что платим

## Подготовка Google Sheets
1. В таблице создайте лист `Операции` с колонками в таком порядке:
   `Дата;Расчетные центры;Раздел ДДС;Дата Затраты (ОПУ);Стоимость;Контрагент;За что платим`
2. Создайте лист `Настройка`.
3. На первой строке листа `Настройка` добавьте заголовки:
   - `Расчетные центры`
   - `Раздел ДДС`
4. Ниже заполните списки значений для выпадающих полей.
5. Создайте Service Account в Google Cloud, скачайте JSON-ключ и поделитесь таблицей с email сервисного аккаунта (доступ Editor).

## Локальный запуск
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# укажите GOOGLE_SHEETS_SPREADSHEET_ID и путь к credentials.json
python app.py
```

Откройте: `http://localhost:8000`

## Запуск на сервере (production)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# укажите GOOGLE_SHEETS_SPREADSHEET_ID и путь к credentials.json

# запуск через gunicorn
PORT=8000 gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wsgi:application
```

Если платформа читает `Procfile`, используйте его как entrypoint (уже добавлен в репозиторий).

## Проверка, что сервис поднялся
- Health-check endpoint: `GET /healthz`
- Пример: `curl http://127.0.0.1:8000/healthz`

## Устойчивость к временным ошибкам сети
- Для операций с Google Sheets добавлены повторные попытки (retry).
- При временных сетевых сбоях (например, `Connection reset by peer`) приложение показывает понятное сообщение и предлагает повторить отправку.
