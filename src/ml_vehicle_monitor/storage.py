from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .ml_api import ListingRecord


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS monitor_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS listings_current (
    item_id TEXT PRIMARY KEY,
    target_brand TEXT NOT NULL,
    target_model TEXT NOT NULL,
    search_query TEXT NOT NULL,
    search_rank INTEGER NOT NULL,
    site_id TEXT,
    category_id TEXT,
    title TEXT,
    brand TEXT,
    model TEXT,
    year INTEGER,
    kilometraje INTEGER,
    descripcion TEXT,
    ubicacion TEXT,
    fecha_publicacion TEXT,
    cantidad_dias_publicada INTEGER,
    precio_publicacion_original REAL,
    ultimo_precio_relevado REAL,
    estado_publicacion TEXT,
    sigue_disponible INTEGER NOT NULL,
    permalink TEXT,
    currency_id TEXT,
    available_quantity INTEGER,
    condition TEXT,
    listing_type_id TEXT,
    seller_id INTEGER,
    seller_nickname TEXT,
    fetched_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listing_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    ultimo_precio_relevado REAL,
    estado_publicacion TEXT,
    sigue_disponible INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES listings_current(item_id)
);
"""


class MonitorStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def start_run(self, mode: str) -> int:
        started_at = datetime.now(timezone.utc).isoformat()
        cursor = self.connection.execute(
            "INSERT INTO monitor_runs(started_at, mode, status, summary) VALUES (?, ?, ?, ?)",
            (started_at, mode, "running", None),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, summary: str | None = None) -> None:
        finished_at = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            "UPDATE monitor_runs SET finished_at = ?, status = ?, summary = ? WHERE id = ?",
            (finished_at, status, summary, run_id),
        )
        self.connection.commit()

    def get_state(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM monitor_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO monitor_state(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, updated_at),
        )
        self.connection.commit()

    def upsert_listing(self, listing: ListingRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.connection.execute(
            "SELECT first_seen_at, seller_nickname FROM listings_current WHERE item_id = ?",
            (listing.item_id,),
        ).fetchone()
        first_seen_at = listing.first_seen_at or (existing["first_seen_at"] if existing else now)
        seller_nickname = listing.seller_nickname or (existing["seller_nickname"] if existing else None)

        payload = asdict(listing)
        payload["first_seen_at"] = first_seen_at
        payload["last_seen_at"] = now
        payload["seller_nickname"] = seller_nickname

        self.connection.execute(
            """
            INSERT INTO listings_current (
                item_id, target_brand, target_model, search_query, search_rank, site_id, category_id,
                title, brand, model, year, kilometraje, descripcion, ubicacion, fecha_publicacion,
                cantidad_dias_publicada, precio_publicacion_original, ultimo_precio_relevado,
                estado_publicacion, sigue_disponible, permalink, currency_id, available_quantity,
                condition, listing_type_id, seller_id, seller_nickname, fetched_at, first_seen_at,
                last_seen_at, raw_json
            ) VALUES (
                :item_id, :target_brand, :target_model, :search_query, :search_rank, :site_id, :category_id,
                :title, :brand, :model, :year, :kilometraje, :descripcion, :ubicacion, :fecha_publicacion,
                :cantidad_dias_publicada, :precio_publicacion_original, :ultimo_precio_relevado,
                :estado_publicacion, :sigue_disponible, :permalink, :currency_id, :available_quantity,
                :condition, :listing_type_id, :seller_id, :seller_nickname, :fetched_at, :first_seen_at,
                :last_seen_at, :raw_json
            )
            ON CONFLICT(item_id) DO UPDATE SET
                target_brand = excluded.target_brand,
                target_model = excluded.target_model,
                search_query = excluded.search_query,
                search_rank = excluded.search_rank,
                site_id = excluded.site_id,
                category_id = excluded.category_id,
                title = excluded.title,
                brand = excluded.brand,
                model = excluded.model,
                year = excluded.year,
                kilometraje = excluded.kilometraje,
                descripcion = excluded.descripcion,
                ubicacion = excluded.ubicacion,
                fecha_publicacion = excluded.fecha_publicacion,
                cantidad_dias_publicada = excluded.cantidad_dias_publicada,
                precio_publicacion_original = excluded.precio_publicacion_original,
                ultimo_precio_relevado = excluded.ultimo_precio_relevado,
                estado_publicacion = excluded.estado_publicacion,
                sigue_disponible = excluded.sigue_disponible,
                permalink = excluded.permalink,
                currency_id = excluded.currency_id,
                available_quantity = excluded.available_quantity,
                condition = excluded.condition,
                listing_type_id = excluded.listing_type_id,
                seller_id = excluded.seller_id,
                seller_nickname = excluded.seller_nickname,
                fetched_at = excluded.fetched_at,
                first_seen_at = excluded.first_seen_at,
                last_seen_at = excluded.last_seen_at,
                raw_json = excluded.raw_json
            """,
            payload,
        )

        self.connection.execute(
            """
            INSERT INTO listing_snapshots(item_id, captured_at, ultimo_precio_relevado, estado_publicacion, sigue_disponible, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                listing.item_id,
                now,
                listing.ultimo_precio_relevado,
                listing.estado_publicacion,
                1 if listing.sigue_disponible else 0,
                listing.raw_json,
            ),
        )
        self.connection.commit()

    def fetch_listings(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT *
            FROM listings_current
            ORDER BY target_model, estado_publicacion DESC, last_seen_at DESC, ultimo_precio_relevado DESC
            """
        )
        return list(cursor.fetchall())

    def fetch_summary(self) -> list[sqlite3.Row]:
        cursor = self.connection.execute(
            """
            SELECT
                target_model,
                COUNT(*) AS total_listings,
                SUM(CASE WHEN sigue_disponible = 1 THEN 1 ELSE 0 END) AS available_listings,
                SUM(CASE WHEN sigue_disponible = 0 THEN 1 ELSE 0 END) AS unavailable_listings,
                MIN(ultimo_precio_relevado) AS min_price,
                MAX(ultimo_precio_relevado) AS max_price,
                AVG(ultimo_precio_relevado) AS avg_price
            FROM listings_current
            GROUP BY target_model
            ORDER BY target_model
            """
        )
        return list(cursor.fetchall())
