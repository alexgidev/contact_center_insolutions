from typing import Dict, Optional
from datetime import datetime
import logging
import asyncio
from domain.entities.call import ETCall
from domain.enums import AgentStatus, CallStatus
from infrastructure.redis.structures.agent_queue import AgentQueue
from infrastructure.redis.structures.call_queue import CallQueue
from infrastructure.redis.structures.agent_state import AgentState
from infrastructure.redis.structures.stats_counter import StatsCounter


logger = logging.getLogger(__name__)


class CallOrchestrator:
    """Asynchronous orchestrator for call assignment using Redis and DB"""

    def __init__(self):
        # Redis structures: safe to keep in memory
        self.agent_queue = AgentQueue()
        self.call_queue = CallQueue()
        self.agent_state = AgentState()
        self.stats = StatsCounter()
        self.assignment_lock = asyncio.Semaphore(100)


    async def assign_call(
        self,
        call: ETCall
    ) -> Dict:
        """Assign call to an available agent or queue it."""
        async with self.assignment_lock:
            try:
                agent_id = self.agent_queue.get_next()
                if agent_id:
                    return await self._assign_to_agent(call, agent_id)
                else:
                    return await self._queue_call(call)
            except Exception as e:
                logger.error(f"Error in call assignment: {e}")
                return {"status": "error", "message": str(e)}


    async def _assign_to_agent(
        self,
        call: ETCall,
        agent_id: int
    ) -> Dict:
        """Assign call to specific agent"""
        try:
            call.agent_id = agent_id
            call.status = CallStatus.ASSIGNED.value
            call.assignment_time = datetime.now()
            if call.created_at:
                call.wait_time_seconds = (
                    call.assignment_time - call.created_at
                ).total_seconds()

            # Update agent state in Redis
            self.agent_state.set(
                agent_id=agent_id,
                status=AgentStatus.BUSY.value, 
                call_id=call.id
            )

            from infrastructure.repositories.call_repository import CallRepository
            call_repo = CallRepository()

            # Persist call in DB asynchronously
            saved_call = await asyncio.to_thread(
                call_repo.create_in_db,
                call_type=call.call_type,
                tenant_id=call.tenant_id,
                status=call.status
            )

            # Assign agent in DB
            await asyncio.to_thread(
                call_repo.assign_to_agent_in_db,
                call_id=saved_call.id,
                agent_id=agent_id
            )

            # Update statistics lazily
            await asyncio.to_thread(
                self.stats.increment,
                "assignments_ok"
            )

            logger.info(f"Call {call.id} assigned to agent {agent_id}")

            return {
                "status": "assigned",
                "agent_id": agent_id,
                "wait_time_seconds": call.wait_time_seconds or 0
            }

        except Exception as e:
            logger.error(
                f"Error assigning call {call.id} to agent {agent_id}: {e}"
            )
            # Return agent to queue in Redis if needed
            if self.agent_state.get(agent_id):
                self.agent_queue.add(agent_id, datetime.now())
            await asyncio.to_thread(self.stats.increment, "assignments_failed")
            raise


    async def _queue_call(
        self,
        call: ETCall
    ) -> Dict:
        """Queue call in Redis and save to DB if no agents available"""
        try:
            call.status = CallStatus.QUEUED.value

            from infrastructure.repositories.call_repository import CallRepository
            call_repo = CallRepository()

            # Save call in DB asynchronously
            saved_call = await asyncio.to_thread(
                call_repo.create_in_db,
                call_type=call.call_type,
                tenant_id=call.tenant_id,
                status=call.status
            )

            # Add call to Redis queue
            self.call_queue.add(saved_call.id)
            queue_position = self.call_queue.count()

            # Increment failed assignments
            await asyncio.to_thread(self.stats.increment, "assignments_failed")

            logger.info(
                f"Call {saved_call.id} queued at position {queue_position}"
            )

            return {
                "status": "queued",
                "message": "No agents available",
                "queue_position": queue_position
            }

        except Exception as e:
            logger.error(f"Error queueing call {call.id}: {e}")
            raise


    async def process_pending_call(
        self,
        call_id: int
    ) -> Optional[Dict]:
        """Process a pending call when an agent becomes available"""
        try:
            from infrastructure.repositories.call_repository import CallRepository
            call_repo = CallRepository()

            # Get call from DB asynchronously
            call = await asyncio.to_thread(
                call_repo.get_by_id_from_db,
                call_id
            )
            if not call:
                logger.error(f"Call {call_id} not found in database")
                return None

            result = await self.assign_call(call)

            if result["status"] != "assigned":
                # Put back in queue if assignment failed
                self.call_queue.add(call_id)
            return result

        except Exception as e:
            logger.error(f"Error processing pending call {call_id}: {e}")
            return None


    def get_assignment_stats(self) -> Dict:
        """Return current assignment statistics"""
        return {
            "available_agents": self.agent_queue.count(),
            "pending_calls": self.call_queue.count(),
            "total_assignments": self.stats.get("assignments_ok") or 0,
            "failed_assignments": self.stats.get("assignments_failed") or 0
        }
