from __future__ import annotations

import csv
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable

import gspread
from google.oauth2.service_account import Credentials

from .config import AppConfig
from .storage import MonitorStorage


def _safe_text(value: object | None) -> str:
    return "" if value is None else str(value)


def _write_csv(rows: Iterable[dict[str, object]], destination: Path) -> None:
    rows = list(rows)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        destination.write_text("", encoding="utf-8")
        return

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _render_html_report(summary_rows: list[dict[str, object]], listing_rows: list[dict[str, object]]) -> str:
    summary_html = "".join(
        f"<tr><td>{row['target_model']}</td><td>{row['total_listings']}</td><td>{row['available_listings']}</td><td>{row['unavailable_listings']}</td><td>{row['min_price'] or ''}</td><td>{row['max_price'] or ''}</td><td>{row['avg_price'] or ''}</td></tr>"
        for row in summary_rows
    )
    columns = list(listing_rows[0].keys()) if listing_rows else []
    header_html = "".join(f"<th>{column}</th>" for column in columns)
    listings_html = "".join(
        "<tr>"
        + "".join(f"<td>{_safe_text(row.get(column))}</td>" for column in columns)
        + "</tr>"
        for row in listing_rows[:200]
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{ font-family: Arial, sans-serif; color: #1f2937; margin: 24px; }}
    h1, h2 {{ margin-bottom: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 32px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; vertical-align: top; text-align: left; }}
    th {{ background: #111827; color: white; }}
    tr:nth-child(even) td {{ background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>Reporte de publicaciones de vehiculos</h1>
  <p>Generado: {generated_at}</p>

  <h2>Resumen por modelo</h2>
  <table>
    <thead>
      <tr><th>Modelo</th><th>Total</th><th>Disponibles</th><th>No disponibles</th><th>Precio minimo</th><th>Precio maximo</th><th>Precio promedio</th></tr>
    </thead>
    <tbody>{summary_html}</tbody>
  </table>

  <h2>Detalle</h2>
  <table>
    <thead><tr>{header_html}</tr></thead>
    <tbody>{listings_html}</tbody>
  </table>
</body>
</html>
"""


def build_report(storage: MonitorStorage, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = [dict(row) for row in storage.fetch_summary()]
    listing_rows = [dict(row) for row in storage.fetch_listings()]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = report_dir / f"ml_vehicle_monitor_{timestamp}.csv"
    html_path = report_dir / f"ml_vehicle_monitor_{timestamp}.html"

    _write_csv(listing_rows, csv_path)
    html_path.write_text(_render_html_report(summary_rows, listing_rows), encoding="utf-8")
    return csv_path, html_path


def publish_to_google_sheets(config: AppConfig, storage: MonitorStorage) -> None:
    sheets = config.sheets
    if not sheets.enabled:
        return
    if not sheets.service_account_file or not sheets.service_account_file.exists():
        raise ValueError("Falta GOOGLE_SERVICE_ACCOUNT_FILE o no existe")
    if not sheets.spreadsheet_id:
        raise ValueError("Falta GOOGLE_SHEETS_SPREADSHEET_ID")

    summary_rows = [dict(row) for row in storage.fetch_summary()]
    listing_rows = [dict(row) for row in storage.fetch_listings()]

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_file(str(sheets.service_account_file), scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(sheets.spreadsheet_id)

    def _write_worksheet(title: str, rows: list[dict[str, object]]) -> None:
        try:
            worksheet = spreadsheet.worksheet(title)
            worksheet.clear()
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=title, rows="1000", cols="40")
        if not rows:
            worksheet.update([["sin datos"]])
            return
        headers = list(rows[0].keys())
        values = [headers]
        for row in rows:
            values.append([_safe_text(row.get(column)) for column in headers])
        worksheet.update(values)

    _write_worksheet("Resumen", summary_rows)
    _write_worksheet(sheets.worksheet_name, listing_rows)


def email_report(config: AppConfig, html_report: Path, csv_report: Path, subject_suffix: str = "") -> None:
    email = config.email
    if not email.enabled:
        return
    if not email.recipients:
        raise ValueError("EMAIL_TO no tiene destinatarios configurados")
    if not email.username or not email.password or not email.sender:
        raise ValueError("Faltan credenciales SMTP para enviar el reporte")

    message = MIMEMultipart()
    message["From"] = email.sender
    message["To"] = ", ".join(email.recipients)
    message["Subject"] = f"{email.subject}{subject_suffix}"

    html_body = html_report.read_text(encoding="utf-8")
    message.attach(MIMEText("Se adjunta el reporte diario de publicaciones de vehiculos.", "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    for attachment_path in (html_report, csv_report):
        with attachment_path.open("rb") as handle:
            part = MIMEApplication(handle.read(), Name=attachment_path.name)
        part["Content-Disposition"] = f'attachment; filename="{attachment_path.name}"'
        message.attach(part)

    with smtplib.SMTP(email.host, email.port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(email.username, email.password)
        smtp.sendmail(email.sender, email.recipients, message.as_string())
