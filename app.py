import os
from datetime import datetime
from typing import Dict, List

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
import gspread
from google.oauth2.service_account import Credentials

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


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret")

    @app.get("/")
    def index():
        try:
            dropdowns = load_dropdown_data()
            today = datetime.now().strftime("%Y-%m-%d")
            return render_template("index.html", dropdowns=dropdowns, today=today)
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

            append_operation(payload)
            flash("Операция успешно сохранена в Google Sheets.", "success")
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
    client = get_client()
    spreadsheet = client.open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
    settings = spreadsheet.worksheet(SETTINGS_SHEET)

    headers = settings.row_values(1)
    header_to_index = {name.strip(): idx + 1 for idx, name in enumerate(headers)}

    center_col = header_to_index.get("Расчетные центры", 1)
    dds_col = header_to_index.get("Раздел ДДС", 2)

    centers = [v.strip() for v in settings.col_values(center_col)[1:] if v.strip()]
    dds_sections = [v.strip() for v in settings.col_values(dds_col)[1:] if v.strip()]

    return {
        "Расчетные центры": sorted(set(centers)),
        "Раздел ДДС": sorted(set(dds_sections)),
    }


def append_operation(data: Dict[str, str]) -> None:
    client = get_client()
    spreadsheet = client.open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
    operations = spreadsheet.worksheet(OPERATIONS_SHEET)

    row = [
        data["Дата"],
        data["Расчетные центры"],
        data["Раздел ДДС"],
        data["Дата Затраты (ОПУ)"],
        data["Стоимость"],
        data["Контрагент"],
        data["За что платим"],
    ]
    operations.append_row(row, value_input_option="USER_ENTERED")


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
