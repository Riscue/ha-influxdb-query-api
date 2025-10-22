from homeassistant.components import http
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .influxdb_service import run_flux_query

DOMAIN = "influxdb_query_api"


async def async_setup(hass: HomeAssistant, config: ConfigType):
    hass.http.register_view(InfluxDBQueryView)
    return True


class InfluxDBQueryView(http.HomeAssistantView):
    url = "/api/influxdb_query_api/query/{entity_id}"
    name = "api:influxdb_query_api"
    requires_auth = True

    async def get(self, request, entity_id):
        start = request.query.get("start", "-1h")
        end = request.query.get("end", "now()")

        data = await run_flux_query(entity_id, start, end)
        return self.json(data)
