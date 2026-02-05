import os
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

REQUIRED_FIELDS = [
    "Дата",
    "Расчетные центры",
    "Раздел ДДС",
    "Дата Затраты (ОПУ)",
    "Стоимость",
    "Контрагент",
    "За что платим",
]

OPERATIONS_SHEET = "Операции"
SETTINGS_SHEET = "Настройка"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


class TemporarySheetsError(RuntimeError):
    """Raised when Google Sheets is temporarily unavailable."""


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret")


    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"}), 200

    @app.get("/")
    def index():
        try:
            dropdowns = load_dropdown_data()
            today = datetime.now().strftime("%Y-%m-%d")
            return render_template("index.html", dropdowns=dropdowns, today=today)
        except TemporarySheetsError:
            return render_template(
                "error.html",
                message=(
                    "Google Sheets временно недоступен. "
                    "Проверьте интернет/доступ и обновите страницу через минуту."
                ),
            ), 503
        except Exception as exc:
            return render_template("error.html", message=str(exc)), 500

    @app.post("/submit")
    def submit():
        try:
            payload = {field: request.form.get(field, "").strip() for field in REQUIRED_FIELDS}
            missing = [name for name, value in payload.items() if not value]
            if missing:
                flash(f"Заполните обязательные поля: {', '.join(missing)}", "error")
                return redirect(url_for("index"))

            error = validate_payload(payload)
            if error:
                flash(error, "error")
                return redirect(url_for("index"))

            append_operation(payload)
            flash("Операция успешно сохранена в Google Sheets.", "success")
            return redirect(url_for("index"))
        except TemporarySheetsError:
            flash(
                "Временная ошибка соединения с Google Sheets. "
                "Попробуйте повторить отправку через несколько секунд.",
                "error",
            )
            return redirect(url_for("index"))
        except Exception as exc:
            flash(f"Ошибка при сохранении: {exc}", "error")
            return redirect(url_for("index"))

    return app


def get_client() -> gspread.Client:
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

    if not spreadsheet_id:
        raise RuntimeError("Не задан GOOGLE_SHEETS_SPREADSHEET_ID.")

    if not os.path.exists(creds_path):
        raise RuntimeError(
            "Не найден файл сервисного аккаунта. "
            "Укажите путь в GOOGLE_APPLICATION_CREDENTIALS."
        )

    credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(credentials)


def load_dropdown_data() -> Dict[str, List[str]]:
    spreadsheet = get_spreadsheet()
    settings = execute_with_retry(lambda: spreadsheet.worksheet(SETTINGS_SHEET))

    headers = execute_with_retry(lambda: settings.row_values(1))
    header_to_index = {name.strip(): idx + 1 for idx, name in enumerate(headers)}

    center_col = header_to_index.get("Расчетные центры", 1)
    dds_col = header_to_index.get("Раздел ДДС", 2)

    centers = [v.strip() for v in execute_with_retry(lambda: settings.col_values(center_col))[1:] if v.strip()]
    dds_sections = [v.strip() for v in execute_with_retry(lambda: settings.col_values(dds_col))[1:] if v.strip()]

    return {
        "Расчетные центры": sorted(set(centers)),
        "Раздел ДДС": sorted(set(dds_sections)),
    }


def append_operation(data: Dict[str, str]) -> None:
    spreadsheet = get_spreadsheet()
    operations = execute_with_retry(lambda: spreadsheet.worksheet(OPERATIONS_SHEET))

    row = [
        data["Дата"],
        data["Расчетные центры"],
        data["Раздел ДДС"],
        data["Дата Затраты (ОПУ)"],
        data["Стоимость"],
        data["Контрагент"],
        data["За что платим"],
    ]
    execute_with_retry(lambda: operations.append_row(row, value_input_option="USER_ENTERED"))


def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_client()
    return execute_with_retry(lambda: client.open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]))


def validate_payload(data: Dict[str, str]) -> str:
    date_fields: List[Tuple[str, str]] = [
        ("Дата", data["Дата"]),
        ("Дата Затраты (ОПУ)", data["Дата Затраты (ОПУ)"]),
    ]
    for title, value in date_fields:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return f"Поле '{title}' должно быть датой в формате YYYY-MM-DD."

    try:
        amount = Decimal(data["Стоимость"])
    except InvalidOperation:
        return "Поле 'Стоимость' должно содержать число."

    if amount < 0:
        return "Поле 'Стоимость' не может быть меньше 0."

    return ""


def execute_with_retry(action):
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return action()
        except (RequestsConnectionError, RequestsTimeout, ConnectionResetError, APIError, OSError) as exc:
            last_error = exc
            if attempt == RETRY_ATTEMPTS:
                break
            time.sleep(RETRY_DELAY_SECONDS)

    raise TemporarySheetsError(str(last_error))


app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
