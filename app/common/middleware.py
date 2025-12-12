from fastapi import Request
import logging
import uuid
import structlog

logger = structlog.get_logger()

async def log_requests(request: Request, call_next):
    '''
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code}")
    return response
    '''
    request_id = str(uuid.uuid4())
    
    # Bind context vars for all downstream logs
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        client_ip=request.client.host if request.client else None
    )
    
    logger.info("Request received")
    response = await call_next(request)
    logger.info(f"Request completed - status_code = {response.status_code}")
    
    return response