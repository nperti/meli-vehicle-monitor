from __future__ import annotations

import argparse
import time
from dataclasses import replace
from datetime import datetime, timezone

from .config import AppConfig, load_config
from .ml_api import MercadoLibreClient, build_listing_record
from .reporting import build_report, email_report, publish_to_google_sheets
from .storage import MonitorStorage


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_due(last_run_at: str | None, interval_hours: int) -> bool:
    parsed = _parse_iso_datetime(last_run_at)
    if parsed is None:
        return True
    elapsed = datetime.now(timezone.utc) - parsed
    return elapsed.total_seconds() >= max(interval_hours, 1) * 3600


def _run_sync(config: AppConfig, storage: MonitorStorage, client: MercadoLibreClient) -> list[str]:
    fetched_at = datetime.now(timezone.utc)
    touched_items: list[str] = []

    for target in config.vehicles:
        search_results = client.search_items(target, limit=config.search_limit)
        item_ids = [str(result["id"]) for result in search_results if result.get("id")]
        items = client.fetch_items(item_ids)

        seller_nicknames: dict[int, str | None] = {}
        for item in items.values():
            seller_id = item.get("seller_id")
            if isinstance(seller_id, int) and seller_id not in seller_nicknames:
                seller_nicknames[seller_id] = client.fetch_seller_nickname(seller_id)

        for result in search_results:
            item_id = str(result["id"])
            item = items.get(item_id)
            if not item:
                continue
            description = client.fetch_description(item_id)
            previous_row = storage.connection.execute(
                "SELECT first_seen_at, last_seen_at, seller_nickname FROM listings_current WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            record = build_listing_record(
                target=target,
                item=item,
                description=description,
                search_rank=int(result.get("search_rank", 0)),
                fetched_at=fetched_at,
                previous_first_seen_at=previous_row["first_seen_at"] if previous_row else None,
                previous_last_seen_at=previous_row["last_seen_at"] if previous_row else None,
            )
            if record.seller_id is not None and record.seller_id in seller_nicknames:
                record = replace(record, seller_nickname=seller_nicknames[record.seller_id])
            elif previous_row and previous_row["seller_nickname"]:
                record = replace(record, seller_nickname=previous_row["seller_nickname"])
            storage.upsert_listing(record)
            touched_items.append(item_id)

    return touched_items


def _run_report(config: AppConfig, storage: MonitorStorage) -> tuple[str, str]:
    report_csv, report_html = build_report(storage, config.report_dir)
    publish_to_google_sheets(config, storage)
    email_report(config, report_html, report_csv)
    storage.set_state("last_report_at", datetime.now(timezone.utc).isoformat())
    return report_csv.name, report_html.name


def _run_pipeline(
    config: AppConfig,
    storage: MonitorStorage,
    client: MercadoLibreClient,
    mode: str,
    run_update: bool = True,
    run_report: bool = True,
) -> dict[str, str]:
    run_id = storage.start_run(mode)
    report_csv_name = ""
    report_html_name = ""
    try:
        summary_parts: list[str] = []
        if run_update:
            touched_items = _run_sync(config, storage, client)
            storage.set_state("last_update_at", datetime.now(timezone.utc).isoformat())
            summary_parts.append(f"items_actualizados={len(touched_items)}")
        if run_report:
            report_csv_name, report_html_name = _run_report(config, storage)
            summary_parts.append(f"reporte_csv={report_csv_name} reporte_html={report_html_name}")
        summary = " ".join(summary_parts) if summary_parts else "sin_tareas"
        storage.finish_run(run_id, "success", summary)
        return {"status": "success", "summary": summary, "report_csv": report_csv_name, "report_html": report_html_name}
    except Exception as error:
        storage.finish_run(run_id, "error", str(error))
        raise


def run_once(config: AppConfig, mode: str = "once") -> dict[str, str]:
    storage = MonitorStorage(config.db_path)
    client = MercadoLibreClient(config.access_token)
    try:
        return _run_pipeline(config, storage, client, mode)
    finally:
        storage.close()


def run_loop(config: AppConfig) -> None:
    storage = MonitorStorage(config.db_path)
    client = MercadoLibreClient(config.access_token)
    try:
        while True:
            last_update_at = storage.get_state("last_update_at")
            last_report_at = storage.get_state("last_report_at")
            update_due = _is_due(last_update_at, config.update_interval_hours)
            report_due = _is_due(last_report_at, config.report_interval_hours)
            if update_due or report_due:
                _run_pipeline(
                    config,
                    storage,
                    client,
                    mode="loop",
                    run_update=update_due,
                    run_report=report_due,
                )
            time.sleep(300)
    finally:
        storage.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitoreo de publicaciones de vehiculos en Mercado Libre")
    parser.add_argument("--once", action="store_true", help="Ejecuta una corrida completa y termina")
    parser.add_argument("--loop", action="store_true", help="Ejecuta en bucle respetando los intervalos configurados")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config()

    if args.loop:
        run_loop(config)
        return

    run_once(config, mode="once")


if __name__ == "__main__":
    main()
