# Home Assistant InfluxDB Query API

[![Home Assistant](https://img.shields.io/badge/home%20assistant-%2341BDF5.svg?style=for-the-badge&logo=home-assistant&logoColor=white)](https://home-assistant.io)
[![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/default)
[![License][license-shield]](LICENSE.md)

[license-shield]: https://img.shields.io/github/license/Riscue/ha-influxdb-query-api.svg?style=for-the-badge

[![GitHub Release](https://img.shields.io/github/release/Riscue/ha-influxdb-query-api.svg?style=for-the-badge)](https://github.com/Riscue/ha-influxdb-query-api/releases)
[![GitHub Downloads (all assets, latest release)](https://img.shields.io/github/downloads/Riscue/ha-influxdb-query-api/latest/total?label=downloads&style=for-the-badge)](https://github.com/Riscue/ha-influxdb-query-api/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/Riscue/ha-influxdb-query-api.svg?style=for-the-badge)](https://github.com/Riscue/ha-influxdb-query-api/commits/master)

![Icon](assets/logo.png)

This Home Assistant custom integration that provides a **secure backend API endpoint** for querying **InfluxDB v2**
using **Flux** queries from within Home Assistant.

This integration enables UI cards, dashboards, and automations to retrieve historical time-series data **without
exposing InfluxDB tokens, URLs, or ports** to the frontend or network.

---

## 🎯 Purpose

Home Assistant's built-in InfluxDB integration only supports **writing** data to InfluxDB.  
This integration adds a **backend API endpoint** that allows controlled **read** access by performing Flux queries
server-side.

### Why Use This Integration?

**Security Benefits:**

- ✅ No InfluxDB credentials stored in UI components
- ✅ No direct browser connections to InfluxDB
- ✅ Prevents CORS and token exposure issues
- ✅ No need to expose InfluxDB externally or on LAN

**Performance Benefits:**

- ⚡ Server-side query execution
- ⚡ Fast query performance
- ⚡ Unlimited historical data retention (unlike Recorder's 10-day default limit)
- ⚡ Reduces load on Home Assistant's database

All data queries run **inside Home Assistant** in a secure, controlled manner.

---

## ✨ Features

| Feature                                       | Description                                              |
|-----------------------------------------------|----------------------------------------------------------|
| 🔒 Secure server-side Flux query execution    | No credentials sent to frontend                          |
| 🌐 Backend **HTTP GET API** endpoint          | Simple call interface for frontend cards                 |
| ⚙️ Uses existing HA InfluxDB v2 configuration | No duplicate configuration needed                        |
| 📊 Time range & entity-based queries          | Works for trend and analytics dashboards                 |
| 🚀 Small, fast, and minimal                   | No services, no UI configuration, no Recorder dependency |
| 📈 `recorder` compatible responses            | Same JSON format as built-in HA Recorder API             |

---

## 📋 Requirements

| Component                                             | Required |
|-------------------------------------------------------|:--------:|
| Home Assistant                                        |    ✅     |
| InfluxDB v2 (self-hosted or cloud)                    |    ✅     |
| Home Assistant **InfluxDB v2 integration** configured |    ✅     |

> **Note:** If you haven't set up InfluxDB v2 in Home Assistant yet, follow
> the [official documentation](https://www.home-assistant.io/integrations/influxdb/).

---

## 📦 Installation

### HACS Installation (Recommended)

This integration can be added to HACS as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories):
* URL: `https://github.com/Riscue/ha-influxdb-query-api`
* Category: `Integration`

After adding a custom repository you can use HACS to install this integration using user interface.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Riscue&repository=ha-influxdb-query-api)

### Manual Installation

1. Download the latest release from the [release page](https://github.com/Riscue/ha-influxdb-query-api/releases)
2. Copy the `influxdb_query_api` folder to `<config_dir>/custom_components/`
3. Restart Home Assistant

---

## ⚙️ Configuration

Add the following to your `configuration.yaml`:

```yaml
influxdb_query_api:
```

That's it! The integration uses your existing InfluxDB v2 configuration automatically.

> **Note:** No additional authentication setup or UI configuration is required.

After adding the configuration, restart Home Assistant to activate the integration.

---

## 🔌 API Usage

### Endpoint

This integration exposes a **backend API endpoint**:

```
GET /api/influxdb_query_api/query/{entity_id}?start={start}&end={end}
```

### Parameters

| Parameter   | Type   | Description                                            | Required | Example                   |
|-------------|--------|--------------------------------------------------------|:--------:|---------------------------|
| `entity_id` | string | The Home Assistant entity ID                           |    ✅     | `sensor.living_room_temp` |
| `start`     | string | ISO 8601 datetime string (UTC or with timezone offset) |    ✅     | `2025-01-10T12:00:00Z`    |
| `end`       | string | ISO 8601 datetime string (UTC or with timezone offset) |    ✅     | `2025-01-10T13:00:00Z`    |

### Example Request (for External Usage)

#### From Lovelace Cards (Internal)

```typescript
const data: DataPoint[] = await this.hass.callApi(
    "GET",
    `influxdb_query_api/query/${entity_id}?start=${start}&end=${end}`
);
```

#### From External Applications

```typescript
const response = await fetch(
    `http://homeassistant.local:8123/api/influxdb_query_api/query/${entity_id}?start=${start}&end=${end}`,
    {headers: {'Authorization': `Bearer ${ACCESS_TOKEN}`}} // Required for external use only
);
```

```bash
curl -X GET "http://homeassistant.local:8123/api/influxdb_query_api/query/${ENTITY_ID}?start=${START}&end=${END}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" # Required for external use only
```

### Example Response

```json
[
  {
    "time": "2025-01-10T12:00:00Z",
    "value": "21.4"
  },
  {
    "time": "2025-01-10T12:05:00Z",
    "value": "21.7"
  },
  {
    "time": "2025-01-10T12:10:00Z",
    "value": "21.9"
  }
]
```

### Response Format

The API returns an array of data points:

```typescript
type DataPoint = {
    time: string;    // ISO 8601 timestamp
    value: string | number;
}
```

---

## 🎨 Recommended Use Cases

### Trend Analysis Card

This integration is designed to work seamlessly with the
**[Trend Analysis Card](https://github.com/Riscue/trend-analysis-card)**:

[![Trend Analysis Card](https://img.shields.io/badge/View-Trend%20Analysis%20Card-blue)](https://github.com/Riscue/trend-analysis-card)

The card automatically fetches historical data from your InfluxDB instance through this API instead of using Home
Assistant's built-in Recorder.

**Why use InfluxDB as a data source?**

- 📊 Unlimited historical data retention (Recorder limited to 10 days by default)
- 🚀 Fast and flexible data querying
- 💾 Minimized Recorder database size and write operations
- 📈 Better performance for time-series analytics

#### Example Card Configuration

```yaml
type: custom:trend-analysis-card
entity: sensor.my_sensor
source: influxdb # Use InfluxDB instead of Recorder
```

The key difference is setting influxdb as a source:

```yaml
source: influxdb
```

This tells the card to request data from this API instead of Home Assistant's Recorder backend.

### Other Use Cases

- **Custom dashboards** with historical data visualization
- **Automations** that need historical data analysis
- **API integrations** requiring time-series data
- **Mobile apps** accessing historical sensor data

---

## ⚠️ Error Handling

| Case                 | Response                            |
|----------------------|-------------------------------------|
| No matching data     | `[]`                                |
| Invalid entity       | `[]`                                |
| Missing parameters   | HTTP 400 Bad Request                |
| InfluxDB unavailable | HTTP 500 Internal Server Error      |
| Internal error       | HTTP 500 + detailed error log in HA |

The API is intentionally predictable and returns empty arrays for missing data to prevent frontend crashes.

---

### Enabling Debug Logging

Add this to your `configuration.yaml` to enable detailed logging:

```yaml
logger:
  default: info
  logs:
    custom_components.influxdb_query_api: debug
```

---

## 📝 Notes

- This integration **only provides a read-only HTTP API endpoint** — no Home Assistant Service is exposed
- Token and bucket configuration come from the existing InfluxDB integration
- This integration does **not** modify or write any data to InfluxDB, only reads
- Query results are not cached — each request executes a new Flux query

---

## License

MIT © [Riscue](https://github.com/riscue)
