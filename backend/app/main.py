"""Main FastAPI application entrypoint for RecallBench."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router

app = FastAPI(
    title="RecallBench — Agent Memory Reliability Lab",
    version="1.0.0",
    description="Local evaluation laboratory measuring memory reliability across temporal recall, stale-fact detection, contradiction handling, entity isolation, and deletion compliance.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration restricted strictly to local frontend development origins
ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount endpoints
app.include_router(router)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Sanitize uncaught server exceptions to prevent leaking stack traces or internal filesystem paths."""
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing the request."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
