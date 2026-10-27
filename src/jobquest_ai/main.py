from dotenv import load_dotenv

# Load secrets before importing authentication modules.
load_dotenv()

from fastapi import FastAPI

from jobquest_ai.database.connection import create_tables
from jobquest_ai.api.routes.auth import router as auth_router

app = FastAPI(title="JobQuest.Ai API")

app.include_router(auth_router)


@app.on_event("startup")
def startup():
    create_tables()


@app.get("/")
def health_check():
    return {"message": "JobQuest.Ai API is running"}