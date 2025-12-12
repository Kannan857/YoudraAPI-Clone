
from qdrant_client import AsyncQdrantClient
from app.config.config import settings

class QdrantClient:
    def __init__(self):
        try:
            print ("Instantiating a new qdrant client")
            self._client = AsyncQdrantClient(
                url=settings.QDRANT_URL,  # Qdrant server URL
                api_key=settings.QDRANT_API_KEY,  # From Qdrant cloud or local config
                prefer_grpc=True,  # Use False for HTTP-only
                timeout=30
            )
            print ("After instantiation")
        except Exception as e:
            # Handle initialization errors (e.g., invalid URL, connection issues)
            print(f"Error initializing Qdrant client: {e}")
            raise RuntimeError("Failed to initialize Qdrant client") from e

    
    
    def __getattr__(self, name):
        """
        Dynamically delegate attribute access to the underlying AsyncQdrantClient.
        """
        if hasattr(self._client, name):
            return getattr(self._client, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
        
    async def close(self):
        """
        Explicitly close the underlying Qdrant client.
        """
        try:
            await self._client.close()
        except Exception as e:
            print(f"Error closing Qdrant client: {e}")
            raise RuntimeError("Failed to close Qdrant client") from e
        