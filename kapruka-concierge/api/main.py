"""
api/main.py
FastAPI application entry-point for the Kapruka Gift Concierge.

Start with:
    uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.stream import router as stream_router
from api.action import router as action_router
from api.image import router as image_router

app = FastAPI(title="Kapruka Concierge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stream_router)
app.include_router(action_router)
app.include_router(image_router)
