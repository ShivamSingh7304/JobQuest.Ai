from dotenv import load_dotenv

# Load secrets before importing authentication modules.
load_dotenv()

from fastapi import FastAPI

from jobquest_ai.api.routes.auth import router as auth_router
from jobquest_ai.api.routes.chat import router as chat_router
from jobquest_ai.database.connection import create_tables

app = FastAPI(title="JobQuest.Ai API")

app.include_router(auth_router)
app.include_router(chat_router)


@app.on_event("startup")
def startup():
    create_tables()


@app.get("/")
def health_check():
    return {"message": "JobQuest.Ai API is running"}


def main() -> None:
    import uvicorn

    uvicorn.run("jobquest_ai.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
    main()
