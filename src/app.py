import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api import router

app = FastAPI(title="MTProto Management API")

app.include_router(router)


@app.exception_handler(httpx.HTTPStatusError)
async def telemt_error_handler(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    message = exc.response.json().get("error", {}).get("message", exc.response.text)
    return JSONResponse(status_code=exc.response.status_code, content={"detail": message})
