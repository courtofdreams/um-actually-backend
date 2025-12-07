from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from api.routes.text_analysis import router as text_analysis_router
from api.routes.transcript import router as transcript_router
from api.routes.video_analysis import router as video_analysis_router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Um, Actually? API",
    version="1.0.0",
)


origins = [
    "https://um-actually-frontend.fly.dev",
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    text_analysis_router,
    prefix="/api",
    tags=["text-analysis"],
)

app.include_router(
    transcript_router,
    prefix="/api",
    tags=["transcript"],
)

app.include_router(
    video_analysis_router,
    prefix="/api",
    tags=["video-analysis"],
)


# Routes
@app.get("/")
async def root():
    return {"message": "Um Actually Backend API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


def run():
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, env_file='.env')
