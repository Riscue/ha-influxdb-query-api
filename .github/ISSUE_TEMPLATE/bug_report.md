---
name: Bug Report
about: Report a problem or unexpected behavior
labels: bug
---

## Description

A clear and concise description of the bug.

## To Reproduce

Steps to reproduce the behavior:

1.
2.
3.

## Actual Behavior

What actually happened? Include error messages if available.

## Expected Behavior

What you expected to happen instead.

## Environment

| Component                                  | Version / Info              |
|--------------------------------------------|-----------------------------|
| Home Assistant Core                        | e.g. 2025.1.3               |
| InfluxDB Version                           | e.g. InfluxDB Cloud / 2.7.x |
| InfluxDB Client Type                       | Cloud / Self-hosted         |
| Integration Version (`influxdb_query_api`) | e.g. 1.2.0                  |
| Installation Method                        | HACS / Manual               |

## InfluxDB Configuration

```yaml
# Configuration from configuration.yaml or UI
# Add other relevant config
influxdb_query_api:
  ...
influxdb:
  ...
```

## Logs

<details>
<summary>Home Assistant logs (click to expand)</summary>

```
Paste relevant logs from Home Assistant (Configuration > Logs or home-assistant.log)
Filter by 'influxdb_query_api' if possible
```

</details>

<details>
<summary>InfluxDB query test result (optional)</summary>

```
If you tested the query directly in InfluxDB UI/CLI, paste the result here
```

</details>

## Additional Context

- Does the query work when executed directly in InfluxDB?
- Did this work in a previous version?
- Any recent changes to InfluxDB or Home Assistant configuration?
- Network connectivity issues or authentication problems?
- ...

Add any other context about the problem here.