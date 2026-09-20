import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.logging import setup_logging
from app.core.redis_client import load_lua_scripts

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Dead Hand API...")
    load_lua_scripts()
    logger.info("API ready")
    yield
    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Dead Hand API",
    description="A production-ready Dead Hand fail-safe service with OTP, Celery tasks, and Redis.",
    version="3.0.0",
    lifespan=lifespan,
)

import time

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    from app.core.rate_limit import get_client_ip
    ip = get_client_ip(request)
    start_time = time.perf_counter()
    method = request.method
    path = request.url.path
    logger.info("--> Incoming Request: %s %s | Client IP: %s", method, path, ip)
    response = await call_next(request)
    process_time = (time.perf_counter() - start_time) * 1000
    logger.info("<-- Completed Request: %s %s | Client IP: %s | Status: %d | Time: %.2fms", method, path, ip, response.status_code, process_time)
    return response

# Exception handlers

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 429:
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "application/xhtml" in accept:
            retry_after = exc.headers.get("Retry-After", "60") if exc.headers else "60"
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rate Limit Active · Dead Hand</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {{
      margin: 0;
      padding: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background-color: #f8fafc;
      font-family: 'Inter', -apple-system, sans-serif;
      color: #0f172a;
    }}
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 36px 32px;
      max-width: 440px;
      width: 90%;
      box-shadow: 0 4px 20px -2px rgba(0,0,0,0.06);
      text-align: center;
    }}
    .icon {{
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: #fffbeb;
      border: 1px solid #fde68a;
      color: #d97706;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 18px;
    }}
    h1 {{
      font-size: 1.25rem;
      font-weight: 700;
      margin: 0 0 8px;
      color: #0f172a;
    }}
    p {{
      font-size: 0.88rem;
      color: #64748b;
      line-height: 1.6;
      margin: 0 0 20px;
    }}
    .counter-box {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 12px;
      font-size: 0.85rem;
      color: #334155;
      margin-bottom: 24px;
    }}
    .counter {{
      font-weight: 700;
      font-size: 1.1rem;
      color: #d97706;
      font-family: monospace;
    }}
    .btn {{
      display: inline-block;
      width: 100%;
      padding: 11px 0;
      background: #0f172a;
      color: #ffffff;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.88rem;
      border-radius: 8px;
      transition: background 0.15s;
    }}
    .btn:hover {{
      background: #1e293b;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
    </div>
    <h1>Too Many Login Attempts</h1>
    <div class="counter-box">
      You can try again in <span id="timer" class="counter">{retry_after}</span> seconds.
    </div>
    <a href="http://localhost:5173/" class="btn">Return to Application</a>
  </div>
  <script>
    let seconds = parseInt({retry_after}, 10);
    const el = document.getElementById('timer');
    const interval = setInterval(() => {{
      seconds--;
      if (seconds <= 0) {{
        clearInterval(interval);
        window.location.href = 'http://localhost:5173/';
      }} else {{
        el.textContent = seconds;
      }}
    }}, 1000);
  </script>
</body>
</html>"""
            return HTMLResponse(content=html, status_code=429, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


from app.auth.routes import router as auth_router
from app.otp.routes import router as otp_router
from app.switches.routes import router as switches_router

app.include_router(auth_router)
app.include_router(otp_router)
app.include_router(switches_router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "dead-mans-switch"}
