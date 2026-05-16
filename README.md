# Monitoreo de publicaciones de vehiculos en Mercado Libre

Proceso para rastrear publicaciones relacionadas con Nissan X-Trail Acenta y Nissan Xterra en Mercado Libre, guardar historico y generar reporte diario.

## Que hace

- Busca publicaciones por termino de busqueda configurable.
- Consulta el detalle de cada publicacion y extrae campos de vehiculos cuando la API los expone.
- Guarda un historico en SQLite y mantiene una tabla con el estado actual.
- Genera un reporte CSV y HTML en cada corrida.
- Puede enviar el reporte por email usando SMTP de Gmail.
- Puede volcar el reporte a Google Sheets usando una service account de GCP.

## Campos almacenados

Se guardan, como minimo, estos campos:

- marca
- modelo
- ano
- kilometraje
- descripcion
- ubicacion
- fecha de publicacion
- cantidad de dias desde que esta publicada
- precio de publicacion original
- ultimo precio relevado
- estado de la publicacion

Ademas se guardan campos utiles extra cuando estan disponibles en la API:

- item_id
- permalink
- categoria
- currency_id
- available_quantity
- condition
- listing_type_id
- seller_id
- seller_nickname
- site_id
- first_seen_at
- last_seen_at
- search_query
- search_rank
- raw_json

## Configuracion

1. Copia `.env.example` a `.env`.
2. Ajusta `VEHICLES_JSON` si queres cambiar los vehiculos a monitorear.
3. Si queres email, completa las credenciales SMTP.

Variables principales:

- `VEHICLES_JSON`: lista JSON con `brand`, `model`, `query` y, opcionalmente, `site_id` y `category_id`.
- `UPDATE_INTERVAL_HOURS`: frecuencia de actualizacion al correr en modo continuo.
- `REPORT_INTERVAL_HOURS`: frecuencia de reporte al correr en modo continuo.
- `EMAIL_ENABLED`: activa el envio del reporte por email.
- `SHEETS_ENABLED`: activa la carga del reporte a Google Sheets.
- `GOOGLE_SERVICE_ACCOUNT_FILE`: ruta al JSON de la service account.
- `GOOGLE_SHEETS_SPREADSHEET_ID`: id de la hoja destino.
- `GOOGLE_SHEETS_WORKSHEET_NAME`: nombre de la pestaña destino.

## Uso local

Instala dependencias:

```bash
pip install -e .
```

Ejecuta una corrida completa:

```bash
ml-vehicle-monitor --once
```

Modo continuo con intervalos configurables:

```bash
ml-vehicle-monitor --loop
```

## Salida

- Base historica: `data/ml_vehicle_monitor.sqlite3`
- Reportes: `reports/`

## GitHub Actions

El repositorio incluye un workflow diario para ejecutar el proceso automaticamente. Para usarlo, subilo a tu repo personal de GitHub y cargá los secretos en el repo.

Secretos sugeridos:

- `VEHICLES_JSON`
- `ML_ACCESS_TOKEN` si queres autenticar las llamadas
- `EMAIL_ENABLED`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `SHEETS_ENABLED`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SHEETS_WORKSHEET_NAME`

## Mercado Libre

La implementacion usa la API publica de Mercado Libre para buscar publicaciones y el detalle del item. Para algunas cuentas o consultas privadas, puede hacer falta un access token.

## Recomendacion para evitar Gmail

Si queres evitar credenciales de Gmail, la mejor opcion es usar Google Sheets con una service account de GCP. En ese caso solo necesitas compartir la hoja con el email de la service account y configurar el JSON de credenciales.
