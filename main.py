import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from application.api import agent_router, call_router, stats_router
from infrastructure.database.connection import init_database
from infrastructure.redis.connection import init_redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application lifecycle.
    Runs on startup and shutdown.
    """
    # Startup
    logger.info("Starting Contact Center API...")
    
    # Initialize database
    if not init_database():
        logger.error("Failed to initialize database")
        raise RuntimeError("Database initialization failed")
    
    # Initialize Redis
    if not init_redis():
        logger.error("Failed to initialize Redis")
        raise RuntimeError("Redis initialization failed")
    
    logger.info("All systems ready!")
    
    yield  # Application runs
    
    # Shutdown
    logger.info("Shutting down Contact Center API...")
    # Cleanup connections if needed


# Create FastAPI application
app = FastAPI(
    title="Contact Center API",
    description="Call assignment system for contact center",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS (for web clients)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router, prefix="/agent", tags=["Agents"])
app.include_router(call_router, prefix="/call", tags=["Calls"])
app.include_router(stats_router, prefix="/stats", tags=["Statistics"])

# Root endpoint
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Contact Center API",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    from infrastructure.database.connection import db_connection
    from infrastructure.redis.connection import redis_connection
    
    return {
        "status": "healthy",
        "database": "connected" if db_connection.test_connection() else "disconnected",
        "redis": "connected" if redis_connection.test_connection() else "disconnected"
    }


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )