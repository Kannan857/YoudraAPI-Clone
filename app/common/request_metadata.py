from fastapi import Depends, Request

def get_request_metadata(request: Request):
    return {
        "timezone": request.state.timezone,
        "location": request.state.location,
        "latitude": request.state.latitude,
        "longitude": request.state.longitude
    }