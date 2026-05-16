from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _json_env(name: str, default: Any) -> Any:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return json.loads(raw_value)


@dataclass(frozen=True)
class VehicleTarget:
    brand: str
    model: str
    query: str
    site_id: str = "MLA"
    category_id: str | None = None


@dataclass(frozen=True)
class EmailConfig:
    enabled: bool
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipients: list[str]
    subject: str


@dataclass(frozen=True)
class SheetsConfig:
    enabled: bool
    service_account_file: Path | None
    spreadsheet_id: str | None
    worksheet_name: str


@dataclass(frozen=True)
class AppConfig:
    site_id: str
    access_token: str | None
    vehicles: list[VehicleTarget]
    update_interval_hours: int
    report_interval_hours: int
    db_path: Path
    report_dir: Path
    search_limit: int
    email: EmailConfig
    sheets: SheetsConfig


def load_config(project_root: Path | None = None) -> AppConfig:
    load_dotenv()

    root = project_root or Path(__file__).resolve().parents[2]
    default_vehicles = [
        {"brand": "Nissan", "model": "X-Trail Acenta", "query": "nissan xtrail acenta"},
        {"brand": "Nissan", "model": "Xterra", "query": "nissan xterra"},
    ]
    vehicles_raw = _json_env("VEHICLES_JSON", default_vehicles)
    vehicles = [
        VehicleTarget(
            brand=item["brand"],
            model=item["model"],
            query=item["query"],
            site_id=item.get("site_id", os.getenv("ML_SITE_ID", "MLA")),
            category_id=item.get("category_id"),
        )
        for item in vehicles_raw
    ]

    email = EmailConfig(
        enabled=_bool_env("EMAIL_ENABLED", False),
        host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USERNAME", ""),
        password=os.getenv("SMTP_PASSWORD", ""),
        sender=os.getenv("EMAIL_FROM", os.getenv("SMTP_USERNAME", "")),
        recipients=[value.strip() for value in os.getenv("EMAIL_TO", "").split(",") if value.strip()],
        subject=os.getenv("EMAIL_SUBJECT", "Reporte diario de publicaciones de vehiculos en Mercado Libre"),
    )

    sheets_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    sheets = SheetsConfig(
        enabled=_bool_env("SHEETS_ENABLED", False),
        service_account_file=Path(sheets_file) if sheets_file else None,
        spreadsheet_id=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip() or None,
        worksheet_name=os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "Reporte diario"),
    )

    return AppConfig(
        site_id=os.getenv("ML_SITE_ID", "MLA"),
        access_token=os.getenv("ML_ACCESS_TOKEN") or None,
        vehicles=vehicles,
        update_interval_hours=int(os.getenv("UPDATE_INTERVAL_HOURS", "24")),
        report_interval_hours=int(os.getenv("REPORT_INTERVAL_HOURS", "24")),
        db_path=Path(os.getenv("DB_PATH", str(root / "data" / "ml_vehicle_monitor.sqlite3"))),
        report_dir=Path(os.getenv("REPORT_DIR", str(root / "reports"))),
        search_limit=int(os.getenv("SEARCH_LIMIT", "50")),
        email=email,
        sheets=sheets,
    )
