from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

try:
    from .core.logging_config import setup_logging
except ImportError:
    from core.logging_config import setup_logging

setup_logging()

try:
    from .routes.negotiate import router
except ImportError:  # pragma: no cover - allows running the app directly from the backend folder
    from routes.negotiate import router

logger = logging.getLogger(__name__)

app = FastAPI(title="Negotia AI Backend", version="1.0.0")

logger.info("Backend started successfully")

# Allow the React frontend to talk to this API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the negotiation endpoints.
app.include_router(router)


@app.get("/")
def read_root() -> dict[str, str]:
    """Return a simple welcome message for the backend."""
    return {"message": "Welcome to the Negotia AI backend."}


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint used to confirm the API is running."""
    return {"status": "healthy"}
