import os
from dotenv import load_dotenv
load_dotenv()
'''
if os.getenv('SECRET_MANAGER_ENABLED') == 'true':
    from google.cloud import secretmanager_v1beta1 as secretmanager
    client = secretmanager.SecretManagerServiceClient()
    secret_id = os.getenv('JSON_APP_SECRETS_GSM_ID')
    try:
        response = client.access_secret_version(request={"name": secret_id})
        secret_data = response.payload.data.decode("UTF-8")
        import json
        parsed = json.loads(secret_data)
        print(f"Direct GSM test - RABBITMQ_PASSWORD: {parsed.get('RABBITMQ_PASSWORD', 'NOT_FOUND')}")
    except Exception as e:
        print(f"Direct GSM test failed: {e}")
'''
from app.common.logger import configure_logging
configure_logging()
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config.config import settings
from starlette.status import HTTP_404_NOT_FOUND, HTTP_226_IM_USED, HTTP_409_CONFLICT, HTTP_503_SERVICE_UNAVAILABLE, HTTP_406_NOT_ACCEPTABLE, HTTP_205_RESET_CONTENT
from app.api import auth, user, user_prompt_meta_data, supplement_info, progress_mgmt, site_stats, plan_manager, rewards, organizations, billing
from app.data import dbinit
from contextlib import asynccontextmanager
from app.common.qdrant_common import QdrantClient
import structlog

from app.common.middleware import log_requests
from app.common.timezone import TimezoneHeaderMiddleware
from app.common.messaging import rabbitmq_manager
from fastapi.responses import JSONResponse
from app.common.exception import UserNotFound, PlanAlreadyApproved, PlanContextChange, PlanIllegalText, PlanExists, YoudraOpenAIError, YoudraGeminiError

#print ("The key is ", settings.RABBITMQ_PASSWORD)


logger = structlog.get_logger()
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application is starting up...")
    qdrant = None
    try:
        qdrant = QdrantClient()
        app.dependency_overrides[QdrantClient] = lambda: qdrant
        await dbinit.init_db()
        yield
    finally:
        if qdrant:
            await qdrant.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(log_requests)
app.add_middleware(TimezoneHeaderMiddleware)
app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["authentication"]
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await rabbitmq_manager.connect()
    yield
    # Shutdown
    await rabbitmq_manager.disconnect()


app.include_router(
    user.router,
    prefix=f"{settings.API_V1_PREFIX}/users",
    tags=["users"]
)

app.include_router(
    user_prompt_meta_data.router,
    prefix=f"{settings.API_V1_PREFIX}/prompt",
    tags=["prompt"]
)

app.include_router(
    supplement_info.router,
    prefix=f"{settings.API_V1_PREFIX}/supp",
    tags=["supplement"]
)

app.include_router(
    progress_mgmt.router,
    prefix=f"{settings.API_V1_PREFIX}/pro",
    tags=["progress"]
)

app.include_router(
    site_stats.router,
    prefix=f"{settings.API_V1_PREFIX}/stats",
    tags=["stats"]
)

app.include_router(
    rewards.router,
    prefix=f"{settings.API_V1_PREFIX}/rewards",
    tags=["rewards"]
)

app.include_router(
    plan_manager.router,
    prefix=f"{settings.API_V1_PREFIX}/plan",
    tags=["plan"]
)

app.include_router(
    organizations.router,
    prefix=f"{settings.API_V1_PREFIX}/organizations",
    tags=["organizations"],
)

app.include_router(
    billing.router,
    prefix=f"{settings.API_V1_PREFIX}/billing",
    tags=["billing"],
)

@app.exception_handler(UserNotFound)
async def user_not_found_handler(request: Request, exc: UserNotFound):
    return JSONResponse(
        status_code=404,
        content={
            "status_code": HTTP_404_NOT_FOUND,
            "error": "UserNotFound",
            "message": exc.reason,
            "user_id": exc.user_id,
            "path": request.url.path,
        },
    )



async def plan_previously_approved_handled(request: Request, exc: PlanAlreadyApproved):
    return JSONResponse(
        status_code=404,
        content={
            "status_code": HTTP_409_CONFLICT,
            "error": "Please Already Approved",
            "message": exc.reason,
            "plan_id": exc.plan_id,
            "path": request.url.path,
        },
    )

async def plan_exists_handler(request: Request, exc: PlanExists):
    return JSONResponse(
        status_code=404,
        content={
            "status_code": HTTP_226_IM_USED,
            "error": "Plan Exists",
            "message": exc.reason,
            "plan_id": exc.plan_id,
            "path": request.url.path,
        },
    )
async def open_ai_error_handler(request: Request, exc: YoudraOpenAIError):
    return JSONResponse(
        status_code=404,
        content={
            "status_code": HTTP_503_SERVICE_UNAVAILABLE,
            "error": "Open AI not available",
            "message": exc.reason,
            "prompt_text": exc.prompt_text,
            "path": request.url.path,
        },
    )
async def gemini_error_handler(request: Request, exc: YoudraGeminiError):
    return JSONResponse(
        status_code=404,
        content={
            "status_code": HTTP_503_SERVICE_UNAVAILABLE,
            "error": "Gemini Unavailable",
            "message": exc.reason,
            "prompt_text": exc.prompt_text,
            "path": request.url.path,
        },
    )
'''
async def plan_context_change_handler(request: Request, exc: PlanContextChange):
    return JSONResponse(
        status_code=205,
        content={
        
            "error": "Gemini Unavailable",
            "message": exc.reason,
            "prompt_text": exc.prompt_text,
            "path": request.url.path,
        },
    )

async def plan_illegal_text_handler(request: Request, exc: PlanIllegalText):
    return JSONResponse(
        status_code=406,
        content={
        
            "error": "Gemini Unavailable",
            "message": exc.reason,
            "prompt_text": exc.prompt_text,
            "path": request.url.path,
        },
    )
'''


@app.get("/hi")
def greet():
    return "Hello World"

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", reload=True)