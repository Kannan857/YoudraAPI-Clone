import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from zoneinfo import ZoneInfo
from typing import Optional

class TimezoneHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Step 1: Get headers (primary source)
        tz = request.headers.get("X-Timezone")
        loc = request.headers.get("X-Location")
        lat = request.headers.get("X-Latitude")
        lon = request.headers.get("X-Longitude")

        # Step 2: Fallback using IP lookup
        if not tz or not lat or not lon:
            client_ip = self._get_client_ip(request)
            ip_info = await self._get_location_info_from_ip(client_ip)

            tz = tz or ip_info["timezone"]
            loc = loc or ip_info["city"]
            lat = lat or ip_info["latitude"]
            lon = lon or ip_info["longitude"]

        # Step 3: Attach to request.state
        request.state.timezone = tz
        request.state.location = loc
        request.state.latitude = lat
        request.state.longitude = lon

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.client.host

    async def _get_location_info_from_ip(self, ip: str) -> dict:
        try:
            url = f"https://ipinfo.io/{ip}/json"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    tz = data.get("timezone")
                    city = data.get("city")
                    loc = data.get("loc")  # e.g., "12.34,56.78"
                    lat, lon = (loc.split(",") if loc else (None, None))

                    # Validate timezone
                    if tz:
                        try:
                            ZoneInfo(tz)
                        except Exception:
                            tz = None

                    return {
                        "timezone": tz,
                        "city": city,
                        "latitude": lat,
                        "longitude": lon
                    }
        except Exception:
            pass

        # Return empty defaults
        return {
            "timezone": None,
            "city": None,
            "latitude": None,
            "longitude": None
        }


def is_valid_timezone(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except:
        return False