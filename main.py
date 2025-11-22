from fastapi import FastAPI  
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from api.routes.text_analysis import router as text_analysis_router

app = FastAPI(
    title="Um, Actually? API",
    version="0.1.0",
)

## TODO: tighten CORS in production
origins = ["*"]

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


def run():
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, env_file='.env')