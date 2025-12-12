from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pytz
import structlog
import re
from dateutil import parser

from app.common.exception import GeneralDataException, TimeZoneException

logger = structlog.get_logger()


"""
Major Timezone Categories:

Africa: 'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi'
America:

North America: 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'
Central/South America: 'America/Mexico_City', 'America/Bogota', 'America/Sao_Paulo'


Asia: 'Asia/Tokyo', 'Asia/Singapore', 'Asia/Dubai', 'Asia/Shanghai', 'Asia/Kolkata'
Australia: 'Australia/Sydney', 'Australia/Melbourne', 'Australia/Perth'
Europe: 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow'
Pacific: 'Pacific/Auckland', 'Pacific/Honolulu'
US Shortcuts: 'US/Eastern', 'US/Central', 'US/Mountain', 'US/Pacific', 'US/Alaska', 'US/Hawaii'
UTC/GMT: 'UTC', 'GMT'

"""



def convert_to_user_timezone(dt, timezone_str):
    """Convert a datetime to a specific timezone."""
    try:
        target_tz = pytz.timezone(timezone_str)
        
        # Ensure dt is timezone-aware and in UTC
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt.astimezone(target_tz)
    except ValueError as ve:
        raise TimeZoneException(f"Invalid datetime format: '{dt}'. Expected format: 'YYYY-MM-DD HH:MM:SS'") from ve
    except Exception as e:
        raise TimeZoneException("Unexpected error during datetime conversion", context={"input": dt, "timezone": timezone_str}) from e


def convert_user_time_to_utc(dt, timezone_str):
    '''
    # User input (example values)
    user_date_str = "2025-03-25 14:30"  # Format: YYYY-MM-DD HH:MM
    user_timezone = "America/New_York"   # IANA timezone name
    '''

    try:

        dt = dt.strip()
        # 1. Parse user input into naive datetime
        user_dt_naive = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")

        # 2. Create timezone-aware datetime
        user_tz = ZoneInfo(timezone_str)
        user_dt_aware = user_dt_naive.replace(tzinfo=user_tz)

        # 3. Convert to UTC
        utc_dt = user_dt_aware.astimezone(ZoneInfo("UTC"))

        logger.info(f"UTC time: {utc_dt.isoformat()}")

        return utc_dt
    except ValueError as ve:
        raise TimeZoneException(f"Invalid datetime format: '{dt}'. Expected format: 'YYYY-MM-DD HH:MM:SS'") from ve
    except Exception as e:
        raise TimeZoneException("Unexpected error during datetime conversion", context={"input": dt, "timezone": timezone_str}) from e


def format_date_time(dt_string):
    try:
        # Handle None or empty strings
        if not dt_string:
            return None
            
        # If the input already has timezone info (like +00:00)
        if re.search(r'[+-]\d{2}:?\d{2}$', dt_string) or 'Z' in dt_string:
            try:
                # Use dateutil parser which handles timezone information well
                parsed_date = parser.parse(dt_string)
                # Return in the required format (with timezone if present)
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                pass
        
        # Try the original list of formats
        formats = [
            "%Y-%m-%d %H:%M:%S%z",  # Added format with timezone offset
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y"
        ]

        for fmt in formats:
            try:
                parsed_date = datetime.strptime(dt_string, fmt)
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        
        # Last resort: try the flexible dateutil parser
        try:
            parsed_date = parser.parse(dt_string)
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    except ValueError as ve:
        raise TimeZoneException(f"Invalid datetime format: '{dt_string}'. Expected format: 'YYYY-MM-DD HH:MM:SS'") from ve
    except Exception as e:
        raise TimeZoneException("Unexpected error during datetime conversion", context={"input": dt_string, "timezone": dt_string}) from e
