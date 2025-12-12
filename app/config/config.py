# app/core/config.py
'''
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = os.getenv('PROJECT_NAME', "My FastAPI Application")
    API_V1_PREFIX: str = os.getenv('API_V1_PREFIX', "/api/v1")
    
    # Sensitive variables with explicit environment variable reading
    OPEN_AI_APIKEY: str = os.getenv('OPEN_AI_API_KEY', '')
    QDRANT_URL: str = os.getenv('QDRANT_URL', '')
    QDRANT_APIKEY: str = os.getenv('QDRANT_API_KEY', '')
    QDRANT_ACTIVITY_COLLECTION_NAME: str = os.getenv('QDRANT_ACTIVITY_COLLECTION_NAME', '')
    QDRANT_GOAL_BUILDER_COLLECTION_NAME: str = os.getenv('QDRANT_GOAL_BUILDER_COLLECTION_NAME', '') 
    # PostgreSQL database connection settings
    POSTGRES_SERVER: str = os.getenv('POSTGRES_SERVER', '')
    POSTGRES_USER: str = os.getenv('POSTGRES_USER', '')
    POSTGRES_PASSWORD: str = os.getenv('POSTGRES_PASSWORD', '')
    POSTGRES_DB: str = os.getenv('POSTGRES_DB', '')
    POSTGRES_PORT: Optional[int] = int(os.getenv('POSTGRES_PORT', 15580))

    RABBITMQ_QUEUE: Optional[str] = str(os.getenv('RABBITMQ_QUEUE', 'plan_tasks_queue'))
    RABBITMQ_USER: str = os.getenv('RABBITMQ_USER', '')
    RABBITMQ_PASSWORD: str = os.getenv('RABBITMQ_PASSWORD', '')
    RABBITMQ_HOST: str = os.getenv('RABBITMQ_HOST','')
    RABBITMQ_PORT: int = os.getenv('RABBITMQ_PORT', '') 
    RABBITMQ_VHOST: str = os.getenv('RABBITMQ_VHOST', '')
    GOOGLE_CLIENT_ID: str = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_GEMINI_API_KEY: str = os.getenv('GOOGLE_GEMINI_API_KEY', '')
    LLM_FLAG: str = str(os.getenv('LLM_FLAG', 'chatgpt'))
    SENDGRID_API_KEY: str = os.getenv('SENDGRID_API_KEY', '')
    
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Get SQLAlchemy database URI"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # JWT settings
    SECRET_KEY: str = os.getenv('SECRET_KEY', '')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 600))

    # Remove env_file for GCP deployment
    model_config = SettingsConfigDict(case_sensitive=True)

# Create global settings object
settings = Settings()

'''

# app/config/config.py
from pydantic_settings import SettingsConfigDict, BaseSettings
from typing import Optional

# Import the GSM loader - this will run at import time and set env vars
from app.config.gsm_settings import gsm_secrets

class Settings(BaseSettings):
    PROJECT_NAME: str = "My FastAPI Application"
    API_V1_PREFIX: str = "/api/v1"
    
    # Sensitive variables - these will now be loaded from env vars set by GSM loader
    OPEN_AI_APIKEY: str = ""
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_ACTIVITY_COLLECTION_NAME: str = ""
    QDRANT_GOAL_BUILDER_COLLECTION_NAME: str = ""
    
    # PostgreSQL database connection settings
    POSTGRES_SERVER: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_PORT: Optional[int] = 0

    RABBITMQ_QUEUE: Optional[str] = ""
    RABBITMQ_USER: str = ""
    RABBITMQ_PASSWORD: str = ""
    RABBITMQ_HOST: str = ""
    RABBITMQ_PORT: int = 0
    RABBITMQ_VHOST: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_GEMINI_API_KEY: str = ""
    LLM_FLAG: str = ""
    SENDGRID_API_KEY: str = ""
    OPEN_AI_API_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_CUSTOM_SEAT_PRICE_ID: str = ""
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Get SQLAlchemy database URI"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # JWT settings
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 0

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file_encoding='utf-8'
    )

# Create settings instance
settings = Settings()

# Debug output
print(f"Settings Debug:")
#print(f"RABBITMQ_PASSWORD: '{settings.RABBITMQ_PASSWORD}'")
#print(f"RABBITMQ_PASSWORD length: {len(settings.RABBITMQ_PASSWORD)}")
#print(f"RABBITMQ_PASSWORD is empty: {not settings.RABBITMQ_PASSWORD}")
print(f"Available GSM secrets: {list(gsm_secrets.keys())}")

# Verify the env var was set
'''
import os
print(f"RABBITMQ_PASSWORD env var: '{os.getenv('RABBITMQ_PASSWORD', 'NOT_SET')}'")
print(f"GSM secrets RABBITMQ_PASSWORD: '{gsm_secrets.get('RABBITMQ_PASSWORD', 'NOT_FOUND')}')")
'''
