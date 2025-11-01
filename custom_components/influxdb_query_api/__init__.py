import homeassistant.helpers.config_validation as cv
from homeassistant.components import http
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .influxdb_service import run_flux_query

DOMAIN = "influxdb_query_api"
INFLUXDB_CONF_DOMAIN = "influxdb"

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    if INFLUXDB_CONF_DOMAIN not in config:
        return False

    conf = config[INFLUXDB_CONF_DOMAIN]
    hass.http.register_view(InfluxDBQueryView(conf))
    return True


class InfluxDBQueryView(http.HomeAssistantView):
    url = f"/api/{DOMAIN}/query/{{entity_id}}"
    name = f"api:{DOMAIN}"
    requires_auth = True

    def __init__(self, conf):
        self.conf = conf

    async def get(self, request, entity_id):
        start = request.query.get("start", "-1h")
        end = request.query.get("end", "now()")

        data = await run_flux_query(self.conf, entity_id, start, end)
        return self.json(data)
