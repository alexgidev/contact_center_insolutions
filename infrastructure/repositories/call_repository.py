from typing import Optional, List, Dict
from datetime import datetime
from sqlalchemy import update, and_, func
import logging
from domain.entities.call import ETCall
from domain.enums import CallStatus
from infrastructure.database.connection import get_db_session
from infrastructure.database.models.call_model import CallModel
from infrastructure.redis.structures.call_queue import CallQueue
from infrastructure.redis.structures.stats_counter import StatsCounter


logger = logging.getLogger(__name__)


class CallRepository:
    """Repository for Call operations
    Handles database persistence and Redis queue management.
    """

    def __init__(self):
        """Initialize repository with connections"""
        self.call_queue = CallQueue()
        self.stats_counter = StatsCounter()


    def create_in_db(
        self,
        call_type: int,
        tenant_id: int = 1,
        status: str = CallStatus.PENDING.value
    ) -> ETCall:
        """Create call in MySQL database

        Args:
            call_type: Type 1-4 for probability matrix
            tenant_id: Tenant ID (default 1)
            status: Initial status

        Returns:
            ETCall entity with generated ID
        """
        session = get_db_session()
        try:
            existing_call = session.query(CallModel).filter_by(
                tenant_id=tenant_id,
                call_type=call_type,
                status=status
            ).first()
            if existing_call:
                logger.info(
                    f"Call already exists (id={existing_call.id}, status={existing_call.status})"
                )
                return self._model_to_entity(existing_call)

            # created_at controlado SOLO por Python
            call_model = CallModel(
                tenant_id=tenant_id,
                call_type=call_type,
                status=status,
                created_at=datetime.now()
            )

            session.add(call_model)
            session.commit()
            session.refresh(call_model)

            call_entity = self._model_to_entity(call_model)

            logger.info(f"Call created in DB with ID: {call_model.id}")
            return call_entity

        except Exception as e:
            session.rollback()
            logger.error(f"Error creating call in DB: {e}")
            raise
        finally:
            session.close()


    def get_by_id_from_db(
        self,
        call_id: int
    ) -> Optional[ETCall]:
        """Get call by ID from database

        Args:
            call_id: Call's ID

        Returns:
            ETCall entity or None if not found
        """
        session = get_db_session()
        try:
            call_model = session.query(CallModel).filter_by(
                id=call_id
            ).first()

            if call_model:
                return self._model_to_entity(call_model)
            return None

        except Exception as e:
            logger.error(f"Error getting call {call_id} from DB: {e}")
            return None
        finally:
            session.close()


    def assign_to_agent_in_db(
        self,
        call_id: int,
        agent_id: int
    ) -> bool:
        """Assign call to agent in database

        Args:
            call_id: Call's ID
            agent_id: Agent's ID

        Returns:
            True if assigned successfully
        """
        session = get_db_session()
        try:
            now = datetime.now()

            call = session.query(CallModel).filter_by(
                id=call_id
            ).first()
            if not call:
                logger.error(f"Call {call_id} not found")
                return False

            wait_time = (
                (now - call.created_at).total_seconds()
                if call.created_at
                else 0
            )
            if wait_time < 0:
                logger.warning(
                    f"Negative wait_time ({wait_time}) detected for call {call_id}, "
                    "forcing to 0"
                )
                wait_time = 0

            result = session.execute(
                update(CallModel).where(CallModel.id == call_id).values(
                    agent_id=agent_id,
                    status=CallStatus.ASSIGNED.value,
                    assignment_time=now,
                    wait_time_seconds=wait_time
                )
            )
            session.commit()

            updated = result.rowcount > 0
            if updated:
                logger.info(f"Call {call_id} assigned to agent {agent_id}")

            return updated

        except Exception as e:
            session.rollback()
            logger.error(f"Error assigning call {call_id}: {e}")
            return False

        finally:
            session.close()


    def complete_call_in_db(
        self,
        call_id: int,
        result: str,
        end_time: Optional[datetime] = None
    ) -> bool:
        """Mark call as completed in database

        Args:
            call_id: Call's ID
            result: Call result (OK/KO)
            end_time: When call ended (default now)

        Returns:
            True if completed successfully
        """
        session = get_db_session()
        try:
            if not end_time:
                end_time = datetime.now()

            call = session.query(CallModel).filter_by(id=call_id).first()
            if not call:
                logger.error(f"Call {call_id} not found")
                return False

            duration = 0
            if call.assignment_time:
                duration = (end_time - call.assignment_time).total_seconds()

            result_db = session.execute(update(CallModel).where(CallModel.id == call_id).values(
                    status=CallStatus.COMPLETED.value,
                    result=result,
                    end_time=end_time,
                    duration_seconds=duration
                )
            )
            session.commit()

            updated = result_db.rowcount > 0
            if updated:
                logger.info(f"Call {call_id} completed with result: {result}")

            return updated

        except Exception as e:
            session.rollback()
            logger.error(f"Error completing call {call_id}: {e}")
            return False

        finally:
            session.close()


    def abandon_call_in_db(self, call_id: int) -> bool:
        """Mark call as abandoned in database

        Args:
            call_id: Call's ID

        Returns:
            True if marked successfully
        """
        session = get_db_session()
        try:
            result = session.execute(update(CallModel).where(CallModel.id == call_id).values(
                    status=CallStatus.ABANDONED.value,
                    result="KO",
                    end_time=datetime.now()
                )
            )
            session.commit()

            updated = result.rowcount > 0
            if updated:
                logger.info(f"Call {call_id} marked as abandoned")

            return updated

        except Exception as e:
            session.rollback()
            logger.error(f"Error abandoning call {call_id}: {e}")
            return False

        finally:
            session.close()


    def get_calls_by_agent_from_db(
        self,
        agent_id: int,
        limit: int = 100
    ) -> List[ETCall]:
        """Get calls handled by specific agent

        Args:
            agent_id: Agent's ID
            limit: Maximum number of calls to return

        Returns:
            List of ETCall entities
        """
        session = get_db_session()
        try:
            calls = session.query(CallModel).filter_by(
                agent_id=agent_id
            ).order_by(
                CallModel.created_at.desc()
            ).limit(limit).all()

            return [self._model_to_entity(call) for call in calls]

        except Exception as e:
            logger.error(f"Error getting calls for agent {agent_id}: {e}")
            return []
        finally:
            session.close()


    def get_pending_calls_from_db(
        self,
        tenant_id: int = 1
    ) -> List[ETCall]:
        """Get all pending/queued calls from database
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of pending ETCall entities
        """
        session = get_db_session()
        try:
            calls = session.query(CallModel).filter(
                and_(
                    CallModel.tenant_id == tenant_id,
                    CallModel.status.in_([CallStatus.PENDING.value, CallStatus.QUEUED.value])
                )
            ).order_by(CallModel.created_at).all()

            return [self._model_to_entity(call) for call in calls]

        except Exception as e:
            logger.error(f"Error getting pending calls: {e}")
            return []

        finally:
            session.close()


    def get_stats_from_db(
        self,
        tenant_id: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Get call statistics from database
        
        Args:
            tenant_id: Tenant ID
            start_date: Start of period (default: today)
            end_date: End of period (default: now)
            
        Returns:
            Dictionary with statistics
        """
        session = get_db_session()
        try:
            if not start_date:
                start_date = datetime.now().replace(
                    hour=0,
                    minute=0,
                    second=0
                )
            if not end_date:
                end_date = datetime.now()

            base_query = session.query(CallModel).filter(
                and_(
                    CallModel.tenant_id == tenant_id,
                    CallModel.created_at >= start_date,
                    CallModel.created_at <= end_date
                )
            )

            total = base_query.count()
            completed = base_query.filter_by(
                status=CallStatus.COMPLETED.value
            ).count()
            abandoned = base_query.filter_by(
                status=CallStatus.ABANDONED.value
            ).count()
            successful = base_query.filter_by(result="OK").count()

            avg_wait = session.query(
                func.avg(CallModel.wait_time_seconds)
            ).filter(
                and_(
                    CallModel.tenant_id == tenant_id,
                    CallModel.created_at >= start_date,
                    CallModel.created_at <= end_date,
                    CallModel.wait_time_seconds.isnot(None)
                )
            ).scalar() or 0

            avg_duration = session.query(
                func.avg(CallModel.duration_seconds)
            ).filter(
                and_(
                    CallModel.tenant_id == tenant_id,
                    CallModel.created_at >= start_date,
                    CallModel.created_at <= end_date,
                    CallModel.duration_seconds.isnot(None)
                )
            ).scalar() or 0

            return {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "total_calls": total,
                "completed_calls": completed,
                "abandoned_calls": abandoned,
                "successful_calls": successful,
                "success_rate": (
                    (successful / completed * 100)
                    if completed > 0
                    else 0
                ),
                "avg_wait_time_seconds": round(avg_wait, 2),
                "avg_duration_seconds": round(avg_duration, 2)
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

        finally:
            session.close()


    def add_to_pending_queue(
        self,
        call_id: int
    ) -> bool:
        """Add call to Redis pending queue

        Args:
            call_id: Call's ID

        Returns:
            True if added successfully
        """
        success = self.call_queue.add(call_id)
        if success:
            self.stats_counter.increment("calls_queued")
        return success


    def get_next_from_queue(self) -> Optional[int]:
        """Get next call from Redis queue

        Returns:
            Call ID or None if queue is empty
        """
        return self.call_queue.get_next()


    def get_queue_size(self) -> int:
        """Get number of calls in Redis queue

        Returns:
            Queue size
        """
        return self.call_queue.count()


    def increment_call_stats(
        self,
        stat_name: str
    ) -> None:
        """Increment call statistics counter in Redis

        Args:
            stat_name: Name of statistic to increment
        """
        self.stats_counter.increment(stat_name)


    def create_and_queue(
        self,
        call_type: int,
        tenant_id: int = 1
    ) -> ETCall:
        """Create call in DB and add to Redis queue if needed

        Args:
            call_type: Type 1-4
            tenant_id: Tenant ID

        Returns:
            Created ETCall entity
        """
        call = self.create_in_db(
            call_type=call_type,
            tenant_id=tenant_id,
            status=CallStatus.QUEUED.value
        )
        self.add_to_pending_queue(call.id)
        self.increment_call_stats("total_calls")

        return call


    def assign_and_update(
        self,
        call_id: int,
        agent_id: int
    ) -> bool:
        """Assign call to agent in both DB and update stats

        Args:
            call_id: Call's ID
            agent_id: Agent's ID

        Returns:
            True if assigned successfully
        """
        success = self.assign_to_agent_in_db(call_id, agent_id)

        if success:
            self.increment_call_stats("assignments_ok")
        else:
            self.increment_call_stats("assignments_failed")

        return success


    def _model_to_entity(
        self,
        model: CallModel
    ) -> ETCall:
        """Convert SQLAlchemy model to domain entity

        Args:
            model: CallModel from database

        Returns:
            ETCall entity
        """
        return ETCall(
            id=model.id,
            tenant_id=model.tenant_id,
            call_type=model.call_type,
            agent_id=model.agent_id,
            status=(
                model.status.value if isinstance(model.status, CallStatus)
                else model.status
            ),
            created_at=model.created_at,
            assignment_time=model.assignment_time,
            end_time=model.end_time,
            result=model.result,
            wait_time_seconds=model.wait_time_seconds,
            duration_seconds=model.duration_seconds
        )
