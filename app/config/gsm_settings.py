#from google.cloud import secretmanager
from google.auth import default as gc_auth
import os
import json
from typing import Dict, Any
from google.cloud import secretmanager_v1beta1 as secretmanager
import structlog

logger = structlog.get_logger()

def load_secrets_from_gsm() -> Dict[str, Any]:
    """
    Load secrets from Google Secret Manager and return as dictionary.
    This function can be called before Settings initialization.
    """
    secret_manager_enabled = os.getenv('SECRET_MANAGER_ENABLED', 'false').lower() == 'true'
    json_secret_id = os.getenv('JSON_APP_SECRETS_GSM_ID')
    
    print(f"GSM Loader - Enabled: {secret_manager_enabled}")
    print(f"GSM Loader - Secret ID: {json_secret_id}")
    
    if not secret_manager_enabled or not json_secret_id:
        logger.info("Secret Manager disabled or ID not set - returning empty dict")
        return {}
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        logger.info(f"Fetching secret: {json_secret_id}")
        
        response = client.access_secret_version(request={"name": json_secret_id})
        json_string = response.payload.data.decode("UTF-8")
        secrets = json.loads(json_string)
        
        logger.info(f"Successfully loaded {len(secrets)} secrets from GSM")
        print(f"GSM Loader - Found keys: {list(secrets.keys())}")
        print(f"GSM Loader - RABBITMQ_PASSWORD present: {'RABBITMQ_PASSWORD' in secrets}")
        
        return secrets
        
    except Exception as e:
        logger.error(f"Failed to load secrets from GSM: {e}")
        print(f"GSM Loader Error: {e}")
        return {}

def set_env_vars_from_secrets(secrets: Dict[str, Any]) -> None:
    """
    Set environment variables from the secrets dictionary.
    This allows Pydantic's default env variable loading to work.
    """
    for key, value in secrets.items():
        if value is not None:  # Only set non-null values
            os.environ[key] = str(value)
            print(f"Set env var: {key}")
    
    print(f"Total env vars set: {len(secrets)}")


# Load secrets at module import time
gsm_secrets = load_secrets_from_gsm()
set_env_vars_from_secrets(gsm_secrets)