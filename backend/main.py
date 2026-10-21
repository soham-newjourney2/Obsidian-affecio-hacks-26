from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status, Response
from pydantic import BaseModel

from random import randrange
from app.db import pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    await pool.open()      # runs once at startup
    yield
    await pool.close()     # runs once at shutdown

app = FastAPI(lifespan=lifespan)
