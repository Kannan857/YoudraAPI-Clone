import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import Column, Integer, Float, Boolean, String
from typing import List, Optional
from app.config.config import settings

import structlog

'''
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
'''

logger = structlog.get_logger()
# Database URL configuration


# Create the SQLAlchemy engine
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    connect_args={'ssl':'require'},
    # Configure connection pooling
    pool_pre_ping=True,  # Enable connection health checks
    pool_size=2,         # Set the maximum number of connections
    max_overflow=2,     # Allow 10 connections beyond pool_size when needed
    pool_recycle=3600    # Recycle connections after 1 hour
)

# Create session factory bound to the engine
# Updated to use async_sessionmaker instead of sessionmaker
SessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False, 
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False  # Important for async operations
)

# Base class for declarative models
Base = declarative_base()
print ("I have connected to the db")
from app.data import billing  # noqa: E402
from app.data import org_member  # noqa: E402
async def get_db():
    db = SessionLocal()
    try:
        yield db
        await db.commit()
    except Exception as e:
        await db.rollback()
        #logger.error(f"Database error: {e}")
        raise
    finally:
        await db.close()

# Updated to work with async
async def execute_sql(query, params=None, fetch=True):
    """
    Execute raw SQL query and optionally fetch results asynchronously
    """
    async with engine.begin() as conn:
        try:
            result = await conn.execute(text(query), params or {})
            if fetch:
                return result.fetchall()
            return None
        except Exception as e:
            #logger.error(f"SQL execution error: {e}")
            raise

# Initialize database on startup - updated to be async
async def init_db():
    # Create tables if they don't exist
    try:
        print("I am inside init db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise
