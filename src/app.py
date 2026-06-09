from src.api import router

from fastapi import FastAPI

app = FastAPI(title="MTProto Management API")

app.include_router(router)
