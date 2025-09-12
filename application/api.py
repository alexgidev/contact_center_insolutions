from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict
from datetime import datetime
import os
import time
import logging
import asyncio
import httpx
import atexit
from domain.entities.call import ETCall
from domain.enums import AgentStatus, CallStatus
from application.orchestrator import CallOrchestrator
from infrastructure.redis.structures.agent_queue import AgentQueue
from infrastructure.redis.structures.call_queue import CallQueue
from infrastructure.redis.structures.stats_counter import StatsCounter
from infrastructure.redis.structures.agent_state import AgentState
from infrastructure.repositories.call_repository import CallRepository
from infrastructure.repositories.agent_repository import AgentRepository

# For now, we'll use simple models for requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# Create a global httpx client
webhook_client = httpx.AsyncClient(timeout=1.0)
# En tu código de la API donde haces requests al webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://webhook:8001/webhook")


async def send_to_webhook(data: dict):
    try:
        await webhook_client.post(WEBHOOK_URL, json=data)
    except Exception as e:
        logger.warning(f"Could not send to webhook: {e}")


# Add cleanup on shutdown
@atexit.register
def cleanup():
    asyncio.run(webhook_client.aclose())


class AgentCreateRequest(BaseModel):
    reference_code: int
    agent_type: int
    tenant_id: int = 1


class AgentModifyRequest(BaseModel):
    status: str


class CallCreateRequest(BaseModel):
    call_type: int
    tenant_id: int = 1


class CallFinishRequest(BaseModel):
    result: str


agent_router = APIRouter()


@agent_router.post("/new")
async def create_agent(request: AgentCreateRequest, background_tasks: BackgroundTasks) -> Dict:
    """Register a new agent in the system

    Flow:
        1. Create agent in database
        2. If available, add to Redis queue
        3. Return agent details
    """
    start_time = time.time()

    def _create_agent_sync() -> Dict:
        # Instantiate repository to create agent in DB
        agent_repo = AgentRepository()
        agent = agent_repo.create_in_db(
            reference_code=request.reference_code,
            agent_type=request.agent_type,
            tenant_id=request.tenant_id,
            status=AgentStatus.AVAILABLE.value
        )

        # # Add agent to Redis queue/state if AVAILABLE
        if agent.status == AgentStatus.AVAILABLE.value:
            agent_queue = AgentQueue()
            agent_queue.add(agent.id, None) # None = no current call

            agent_state = AgentState()
            agent_state.set(agent.id, AgentStatus.AVAILABLE.value)

        # Increment counter in Redis stats
        stats = StatsCounter()
        stats.increment("agents_created")

        return {
            "status": "success",
            "agent_id": agent.id,
            "agent_type": agent.agent_type,
            "reference_code": agent.reference_code,
        }

    try:
        # Run synchronous DB work in a thread
        result = await asyncio.to_thread(_create_agent_sync)
        response_time = (time.time() - start_time) * 1000
        result["response_time_ms"] = round(response_time, 2)
        background_tasks.add_task(send_to_webhook, result)
        return result

    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.put("/modify/{agent_id}")
async def modify_agent_status(
    agent_id: int,
    request: AgentModifyRequest,
    background_tasks: BackgroundTasks
) -> Dict:
    """Modify agent status

    Flow:
        1. Validate new status
        2. Update Redis queues accordingly
        3. Check for pending calls if becoming available
        4. Update agent state in Redis
    """
    start_time = time.time()

    try:
        # Validate input against enum values
        if request.status not in AgentStatus._value2member_map_:
            raise HTTPException(status_code=400, detail="Invalid status")

        agent_state = AgentState()
        agent_queue = AgentQueue()
        call_queue = CallQueue()

        if request.status == AgentStatus.AVAILABLE.value:
            agent_queue.add(agent_id, datetime.now())

            # Check for pending calls in Redis
            if call_queue.count() > 0:
                orchestrator = CallOrchestrator()
                next_call_id = call_queue.get_next()
                if next_call_id:
                    await orchestrator.process_pending_call(next_call_id)

        elif request.status in [
            AgentStatus.BUSY.value,
            AgentStatus.PAUSE.value,
            AgentStatus.OFFLINE.value
        ]:
            agent_queue.remove(agent_id)

        # Update Redis state
        agent_state.set(agent_id, request.status)

        response_time = (time.time() - start_time) * 1000
        response = {
            "status": "success",
            "agent_id": agent_id,
            "new_status": request.status,
            "response_time_ms": round(response_time, 2)
        }
        background_tasks.add_task(send_to_webhook, response)
        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error modifying agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.get("/info/{agent_id}")
async def get_agent_info(agent_id: int, background_tasks: BackgroundTasks) -> Dict:
    """Get agent information from Redis state."""
    try:
        agent_state = AgentState()
        state = agent_state.get(agent_id)

        if not state:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Return relevant agent info from Redis
        response = {
            "agent_id": agent_id,
            "status": state.get("status"),
            "current_call_id": state.get("call_id"),
            "last_update": state.get("last_update")
        }
        background_tasks.add_task(send_to_webhook, response)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


call_router = APIRouter()


@call_router.post("/new")
async def create_call(request: CallCreateRequest, background_tasks: BackgroundTasks) -> Dict:
    """Register new call: assign to agent if available, then save in DB"""
    start_time = time.time()

    try:
        call_repo = CallRepository()
        orchestrator = CallOrchestrator()
        stats = StatsCounter()
        call_queue = CallQueue()

        # Create temporary ETCall object
        call = ETCall(
            id=0, # Will be replaced by DB-generated ID
            tenant_id=request.tenant_id,
            call_type=request.call_type,
            created_at=datetime.now(),
            status=CallStatus.PENDING.value
        )

        # Try to assign call to available agent
        assignment_result = await orchestrator.assign_call(call)

        if assignment_result["status"] == "assigned":
            agent_id = assignment_result["agent_id"]
            call.status = CallStatus.ASSIGNED.value
        else:
            agent_id = None
            call.status = CallStatus.PENDING.value

        # Save call in database
        saved_call = call_repo.create_in_db(
            call_type=call.call_type,
            tenant_id=call.tenant_id,
            status=call.status
        )

        # If assigned, update DB with agent_id
        if agent_id:
            call_repo.assign_to_agent_in_db(
                call_id=saved_call.id,
                agent_id=agent_id
            )
            stats.increment("assignments_ok")
        else:
            # If no agent, add to pending queue
            call_queue.add(saved_call.id)
            stats.increment("assignments_failed")

        # Increment total calls counter
        stats.increment("total_calls")

        response_time = (time.time() - start_time) * 1000
        if response_time > 100:
            logger.warning(f"Response time exceeded 100ms: {response_time:.2f}ms")

        response = {
            **assignment_result,
            "call_id": saved_call.id,
            "response_time_ms": round(response_time, 2)
        }
        background_tasks.add_task(send_to_webhook, response)
        return response

    except Exception as e:
        logger.error(f"Error creating call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@call_router.post("/finished/{call_id}")
async def finish_call(call_id: int, request: CallFinishRequest, background_tasks: BackgroundTasks) -> Dict:
    """Mark call as finished.

    Flow:
        1. Update call in database
        2. Free the agent
        3. Check for pending calls
    """
    start_time = time.time()

    try:
        call_repo = CallRepository()
        call = call_repo.get_by_id_from_db(call_id)
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")

        # Update call status in DB
        call_repo.complete_call_in_db(call_id, request.result)

        agent_freed = None
        if call.agent_id:
            # Free the assigned agent
            agent_repo = AgentRepository()
            agent_repo.change_status(
                call.agent_id,
                AgentStatus.AVAILABLE.value
            )
            agent_freed = call.agent_id

            # Check pending calls and assign next
            call_queue = CallQueue()
            next_call_id = call_queue.get_next()
            if next_call_id:
                orchestrator = CallOrchestrator()
                await orchestrator.process_pending_call(next_call_id)

        # Track call success/failure in Redis
        stats = StatsCounter()
        stats.increment(
            "successful_calls" if request.result == "OK"
            else "failed_calls"
        )

        response_time = (time.time() - start_time) * 1000

        response = {
            "status": "success",
            "call_id": call_id,
            "result": request.result,
            "agent_freed": agent_freed,
            "response_time_ms": round(response_time, 2)
        }
        background_tasks.add_task(send_to_webhook, response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finishing call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


stats_router = APIRouter()


@stats_router.get("/live")
async def get_live_stats(background_tasks: BackgroundTasks) -> Dict:
    """Get real-time statistics from Redis and database."""
    try:
        stats = StatsCounter()
        agent_queue = AgentQueue()
        call_queue = CallQueue()

        # Get additional stats from DB
        call_repo = CallRepository()
        agent_repo = AgentRepository()

        # Get database stats for today
        today_stats = call_repo.get_stats_from_db()

        response = {
            "timestamp": datetime.now().isoformat(),
            "agents": {
                "available": agent_queue.count(),
                "total": len(agent_repo.get_all_by_tenant_from_db())
            },
            "calls": {
                "pending": call_queue.count(),
                "redis_stats": stats.get_all(),
                "database_stats": today_stats
            }
        }
        background_tasks.add_task(send_to_webhook, response)
        return response

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
