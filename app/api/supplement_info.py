from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict
from app.data.dbinit import get_db
from app.data.user import User
from app.service.user import get_current_active_user
from app.common.exception import DatabaseConnectionException, RecordNotFoundException, IntegrityException, MissingDataException, GeneralDataException
from app.service.supplement_info import get_supplemental_data
from app.model.supplement_info import ISupplementDetail, UXSupplementInput
from app.common.qdrant_common import QdrantClient


router = APIRouter()

@router.post("/getsupplementdata/", response_model=List[ISupplementDetail])
async def get_supp_data(input_data: UXSupplementInput, db: AsyncSession = Depends(get_db), 
                      current_user: User = Depends(get_current_active_user),
                    client: QdrantClient = Depends(QdrantClient)):
    """
    This API returns a set of links for each objective in an executable plan. 
    Call this method only for approved plans.
    The intent here is to give additional resources for users to help them accomplish activities.
    """
    try:
        return await get_supplemental_data(input_data, db, User, client)
        
    except DatabaseConnectionException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )
    except GeneralDataException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",

            )
    except IntegrityException as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 detail=f"Unable to create user plan {e.message}",
            )
    except Exception as e:
        raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create user plan {e.message}",
            )