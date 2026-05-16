from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import requests

from .config import VehicleTarget


API_BASE_URL = "https://api.mercadolibre.com"


@dataclass(frozen=True)
class ListingRecord:
    item_id: str
    target_brand: str
    target_model: str
    search_query: str
    search_rank: int
    site_id: str | None
    category_id: str | None
    title: str | None
    brand: str | None
    model: str | None
    year: int | None
    kilometraje: int | None
    descripcion: str | None
    ubicacion: str | None
    fecha_publicacion: str | None
    cantidad_dias_publicada: int | None
    precio_publicacion_original: float | None
    ultimo_precio_relevado: float | None
    estado_publicacion: str | None
    sigue_disponible: bool
    permalink: str | None
    currency_id: str | None
    available_quantity: int | None
    condition: str | None
    listing_type_id: str | None
    seller_id: int | None
    seller_nickname: str | None
    fetched_at: str
    first_seen_at: str | None
    last_seen_at: str | None
    raw_json: str


def _parse_datetime(value: str | None) -> datetime | None:
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


def _days_since(value: str | None, now: datetime) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    delta = now - parsed
    return max(delta.days, 0)


def _find_attribute(attributes: list[dict[str, Any]], keys: Iterable[str]) -> dict[str, Any] | None:
    normalized_keys = {key.upper() for key in keys}
    for attribute in attributes:
        attribute_id = str(attribute.get("id", "")).upper()
        attribute_name = str(attribute.get("name", "")).upper()
        if attribute_id in normalized_keys or attribute_name in normalized_keys:
            return attribute
    return None


def _attribute_value(attribute: dict[str, Any] | None) -> tuple[Any, str | None]:
    if not attribute:
        return None, None
    if attribute.get("value_struct") and attribute["value_struct"].get("number") is not None:
        return attribute["value_struct"].get("number"), attribute["value_struct"].get("unit")
    return attribute.get("value_name"), None


def _int_from_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text_value = str(value)
    digits = "".join(character for character in text_value if character.isdigit())
    return int(digits) if digits else None


def _location_from_item(item: dict[str, Any]) -> str | None:
    address = item.get("address") or item.get("seller_address") or {}
    parts = [
        address.get("state", {}).get("name") if isinstance(address.get("state"), dict) else address.get("state"),
        address.get("city", {}).get("name") if isinstance(address.get("city"), dict) else address.get("city"),
        address.get("neighborhood", {}).get("name") if isinstance(address.get("neighborhood"), dict) else address.get("neighborhood"),
        address.get("address_line"),
    ]
    cleaned_parts = [str(part).strip() for part in parts if part]
    return ", ".join(cleaned_parts) if cleaned_parts else None


class MercadoLibreClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ml-vehicle-monitor/0.1.0"})

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def search_items(self, target: VehicleTarget, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"q": target.query, "limit": limit}
        if target.category_id:
            params["category"] = target.category_id
        response = self.session.get(
            f"{API_BASE_URL}/sites/{target.site_id}/search",
            params=params,
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        normalized_results: list[dict[str, Any]] = []
        for index, result in enumerate(results, start=1):
            if isinstance(result, str):
                normalized_results.append({"id": result, "search_rank": index})
            else:
                normalized = dict(result)
                normalized["search_rank"] = index
                normalized_results.append(normalized)
        return normalized_results

    def fetch_items(self, item_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not item_ids:
            return {}
        response = self.session.get(
            f"{API_BASE_URL}/items",
            params={"ids": ",".join(item_ids)},
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        items: dict[str, dict[str, Any]] = {}
        for entry in payload:
            if entry.get("code") != 200:
                continue
            body = entry.get("body") or {}
            item_id = body.get("id")
            if item_id:
                items[item_id] = body
        return items

    def fetch_description(self, item_id: str) -> str | None:
        response = self.session.get(
            f"{API_BASE_URL}/items/{item_id}/description",
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        text = payload.get("plain_text") or payload.get("text")
        return text.strip() if isinstance(text, str) else None

    def fetch_seller_nickname(self, seller_id: int | None) -> str | None:
        if seller_id is None:
            return None
        response = self.session.get(f"{API_BASE_URL}/users/{seller_id}", headers=self._headers(), timeout=30)
        if response.status_code != 200:
            return None
        payload = response.json()
        nickname = payload.get("nickname")
        return nickname if isinstance(nickname, str) else None


def build_listing_record(
    target: VehicleTarget,
    item: dict[str, Any],
    description: str | None,
    search_rank: int,
    fetched_at: datetime,
    previous_first_seen_at: str | None = None,
    previous_last_seen_at: str | None = None,
) -> ListingRecord:
    attributes = item.get("attributes") or []
    brand_attribute = _find_attribute(attributes, ["BRAND", "VEHICLE_BRAND"])
    model_attribute = _find_attribute(attributes, ["MODEL", "VEHICLE_MODEL"])
    year_attribute = _find_attribute(attributes, ["YEAR", "VEHICLE_YEAR"])
    mileage_attribute = _find_attribute(attributes, ["KILOMETERS", "MILEAGE", "ODOMETER", "KILOMETER"])
    location = _location_from_item(item)

    year_value, _ = _attribute_value(year_attribute)
    mileage_value, _ = _attribute_value(mileage_attribute)

    publication_date = item.get("date_created") or item.get("start_time")
    status = item.get("status")
    normalized_status = status if isinstance(status, str) else None
    is_available = normalized_status == "active"

    return ListingRecord(
        item_id=str(item.get("id")),
        target_brand=target.brand,
        target_model=target.model,
        search_query=target.query,
        search_rank=search_rank,
        site_id=item.get("site_id") or target.site_id,
        category_id=item.get("category_id") or target.category_id,
        title=item.get("title"),
        brand=brand_attribute.get("value_name") if brand_attribute else target.brand,
        model=model_attribute.get("value_name") if model_attribute else target.model,
        year=_int_from_value(year_value),
        kilometraje=_int_from_value(mileage_value),
        descripcion=description,
        ubicacion=location,
        fecha_publicacion=publication_date,
        cantidad_dias_publicada=_days_since(publication_date, fetched_at),
        precio_publicacion_original=float(item["original_price"]) if item.get("original_price") is not None else None,
        ultimo_precio_relevado=float(item["price"]) if item.get("price") is not None else None,
        estado_publicacion=normalized_status,
        sigue_disponible=is_available,
        permalink=item.get("permalink"),
        currency_id=item.get("currency_id"),
        available_quantity=_int_from_value(item.get("available_quantity")),
        condition=item.get("condition"),
        listing_type_id=item.get("listing_type_id"),
        seller_id=_int_from_value(item.get("seller_id")),
        seller_nickname=None,
        fetched_at=fetched_at.isoformat(),
        first_seen_at=previous_first_seen_at,
        last_seen_at=previous_last_seen_at,
        raw_json=json.dumps(item, ensure_ascii=True),
    )
