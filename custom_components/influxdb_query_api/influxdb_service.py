import asyncio

from influxdb_client import InfluxDBClient

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "TOKEN"
INFLUX_ORG = "org"
INFLUX_BUCKET = "bucket"


async def run_flux_query(entity_id, range_start, range_stop):
    domain, entity = entity_id.split('.', 1)
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
        |> range(start: {range_start}, stop: {range_stop})
        |> filter(fn: (r) => r.domain == "{domain}" and r.entity_id == "{entity}" and r._field == "value")
    '''

    def sync_query():
        with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
            tables = client.query_api().query(query)
            result = []
            for table in tables:
                for record in table.records:
                    result.append({"time": record.get_time().isoformat(), "value": record.get_value()})
            return result

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_query)
