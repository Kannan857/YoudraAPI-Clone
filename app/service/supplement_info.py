from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import openai

from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, Any, List

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams
from qdrant_client.http import models, model
from qdrant_client.http.exceptions import UnexpectedResponse



from app.config.config import settings
from app.data.dbinit import get_db
from app.data.user import User
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
from app.model.supplement_info import UXSupplementInput, ISupplementDetail
from app.data.supplement_info import get_data, DBSupplementData
from app.data.user_plan_detail import get_plan_day_detail, UserPlanActivityDetail
from app.data.user_plan import get_executable_plan
from app.data.user import User
from app.common.qdrant_common import QdrantClient
import structlog

logger = structlog.get_logger()
async def get_supplemental_data(obj_input: UXSupplementInput, db: AsyncSession, current_user: User, client: QdrantClient ):
    try:
        filter_params = {}
        filter_params["plan_id"] = obj_input.plan_id
        user_output = []
        
        if obj_input.activity_id:
            filter_params["entity_id"] = obj_input.activity_id
        logger.info("Fetching data from executable plan")
        obj_activity_resultset = await get_executable_plan(filter_params=filter_params, db=db)
        
        for i in range(len(obj_activity_resultset)):
            obj_supplement_data_resultset = []
            obj_supplement_data_resultset = await get_data(db=db, filter_params=filter_params)
            for j in range(len(obj_supplement_data_resultset)):
                user_output.append(ISupplementDetail(
                    site_url = obj_supplement_data_resultset[j].ext_site_url,
                    site_title = obj_supplement_data_resultset[j].ext_site_title,
                    site_keyword=obj_supplement_data_resultset[j].ext_site_keyword,
                    entity_id= str(obj_supplement_data_resultset[j].entity_id),
                    relevance_score= 0.0
                ))
        return user_output
    except IntegrityException as e:

        logger.error(f"Integrity Error when retrieving supplemental data: {str(e)}")
        raise IntegrityException(
            "Integrity Error when retrieving supplemental data",
            context = {"detail": "Error when retrieving supplemental data"}
        )
    except GeneralDataException as e:

        logger.error(f"Database Error when retrieving supplemental data: {str(e)}")
        raise GeneralDataException(
            f"Database Error when retrieving supplemental data {str(e)} ",
            context={"detail": f"Database Error when retrieving supplemental data: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"General Error when retrieving supplemental data: {str(e)}")
        raise GeneralDataException(
            f"General Error when retrieving supplemental data: {str(e)}",
            context={"detail": f"General Error when retrieving supplemental data: {str(e)}"}
        )

async def get_embedding(text):
    response = openai.embeddings.create(
        input=text,
        model="text-embedding-ada-002"
    )
    return response.data[0].embedding

async def get_from_vector_store(text: str, client: QdrantClient)->Optional[List[ISupplementDetail]]:
    try:
        openai.api_key = settings.OPEN_AI_APIKEY
        # Define collection name
        collection_name = settings.QDRANT_ACTIVITY_COLLECTION_NAME
        exists = client.collection_exists(collection_name)
        # Create collection (if not exists)
        if not exists:
            raise MissingDataException(
                message = "The vector data store for activity data is not available. Check the name or the provider",
                context={"detail": f"General Error when retrieving supplemental data from vector data store. Check the name or provider"}
            )
            
        hits = client.query_points(
        collection_name=collection_name,
        query=get_embedding(text),
        limit=5,
        ).points

        supplement_vector_list = []
        for hit in hits:
            print(hit.payload, "score:", hit.score)
            arr = hit.payload["content"]
            for i in range(len(arr)):
                supplement_vector_list.append(ISupplementDetail(
                    site_title= arr[i]["title"],
                    site_url= arr[i].link,
                    entity_id=arr[i].entity_id,
                    relevance_score= hit.score
                ))
                if len(supplement_vector_list) >= 5:
                    return supplement_vector_list
    except Exception as e:
        raise GeneralDataException(
            f"General Error when retrieving supplemental data from vector store: {str(e)}",
            context={"detail": f"General Error when retrieving supplemental data from vector store: {str(e)}"}
        )