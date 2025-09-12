from typing import Optional, List
from datetime import datetime
from sqlalchemy import update
import logging
from domain.entities.agent import ETAgent
from domain.enums import AgentStatus
from infrastructure.database.connection import get_db_session
from infrastructure.database.models.agent_model import AgentModel
from infrastructure.redis.structures.agent_queue import AgentQueue
from infrastructure.redis.structures.agent_state import AgentState


logger = logging.getLogger(__name__)


class AgentRepository:
    """Repository for Agent operations
    Separates database and cache operations as requested.
    """

    def __init__(self):
        """Initialize repository with connections"""
        self.agent_queue = AgentQueue()
        self.agent_state = AgentState()


    def create_in_db(
        self, 
        reference_code: int, 
        agent_type: int, 
        tenant_id: int = 1,
        status: str = AgentStatus.AVAILABLE.value
    ) -> ETAgent:
        """Create agent in MySQL database
        
        Args:
            reference_code: Unique reference code for agent
            agent_type: Type 1-4 for probability matrix
            tenant_id: Tenant ID (default 1 for single tenant)
            status: Initial status

        Returns:
            ETAgent entity with generated ID
        """
        session = get_db_session()
        try:
            # if existing_agent := session.query(AgentModel).filter_by(
            #     reference_code=reference_code
            # ).first():
            #     logger.info(
            #         f"Agent with reference_code={reference_code} "
            #         f"already exists (id={existing_agent.id}) - returning existing"
            #     )
            #     return self._model_to_entity(existing_agent)
            valid_statuses = {s.value for s in AgentStatus}
            if status not in valid_statuses:
                logger.warning(
                    f"Status {status} is not a known AgentStatus. "
                    "Defaulting to AVAILABLE."
                )
                status = AgentStatus.AVAILABLE.value

            agent_model = AgentModel(
                tenant_id=tenant_id,
                reference_code=reference_code,
                agent_type=agent_type,
                status=status,
                created_at=datetime.now()
            )

            with session.begin():
                session.add(agent_model)
                session.flush()
                session.refresh(agent_model)

            agent_entity = self._model_to_entity(agent_model)
            logger.info(
                "Agent created in DB with ID: "
                f"{agent_model.id} (ref: {reference_code})"
            )
            return agent_entity

        except Exception as e:
            try:
                session.rollback()
            except Exception as e:
                logger.error(f"Rollback failed after error: {e}")
            logger.error(
                "Error creating agent in DB for "
                f"reference_code={reference_code}: {e}"
            )
            raise
        finally:
            try:
                session.close()
            except Exception as e:
                logger.error(f"Failed to close DB session: {e}")


    def get_by_id_from_db(
        self,
        agent_id: int
    ) -> Optional[ETAgent]:
        """Get agent by ID from database

        Args:
            agent_id: Agent's ID

        Returns:
            ETAgent entity or None if not found
        """
        session = get_db_session()
        try:
            agent_model = session.query(AgentModel).filter_by(
                id=agent_id
            ).first()
            if agent_model:
                return self._model_to_entity(agent_model)
            return None

        except Exception as e:
            logger.error(
                f"Error getting agent {agent_id} from DB: {e}"
            )
            return None
        finally:
            try:
                session.close()
            except Exception:
                pass


    def get_by_reference_code_from_db(
        self,
        reference_code: int
    ) -> Optional[ETAgent]:
        """Get agent by reference code from database.
        
        Args:
            reference_code: Agent's reference code
            
        Returns:
            ETAgent entity or None if not found
        """
        session = get_db_session()
        try:
            agent_model = session.query(AgentModel).filter_by(
                reference_code=reference_code
            ).first()
            if agent_model:
                return self._model_to_entity(agent_model)
            return None

        except Exception as e:
            logger.error(
                f"Error getting agent by ref {reference_code}: {e}"
            )
            return None

        finally:
            try:
                session.close()
            except Exception:
                pass


    def update_status_in_db(
        self, 
        agent_id: int, 
        status: str,
        current_call_id: Optional[int] = None
    ) -> bool:
        """Update agent status in database.
        
        Args:
            agent_id: Agent's ID
            status: New status
            current_call_id: Current call if BUSY
            
        Returns:
            True if updated successfully
        """
        session = get_db_session()
        try:
            valid_statuses = {s.value for s in AgentStatus}
            if status not in valid_statuses:
                logger.warning(
                    f"Attempted to update agent {agent_id} "
                    f"to unknown status '{status}'"
                )
                return False

            last_call_time_value = (
                datetime.now() if status == AgentStatus.BUSY.value
                else None
            )

            with session.begin():
                result = session.execute(
                    update(AgentModel).where(AgentModel.id == agent_id).values(
                        status=status,
                        current_call_id=current_call_id,
                        last_call_time=last_call_time_value
                    )
                )

            updated = (getattr(result, "rowcount", 0) or 0) > 0
            if updated:
                logger.info(
                    f"Agent {agent_id} status updated "
                    f"to {status} in DB"
                )
            else:
                logger.info(
                    f"Agent {agent_id} status update "
                    f"to {status} affected 0 rows")
            return updated

        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            logger.error(
                f"Error updating agent {agent_id} "
                f"status to {status}: {e}"
            )
            return False

        finally:
            try:
                session.close()
            except Exception:
                pass


    def get_all_by_tenant_from_db(
            self,
            tenant_id: int = 1
        ) -> List[ETAgent]:
        """Get all agents for a tenant from database
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of ETAgent entities
        """
        session = get_db_session()
        try:
            agents = session.query(AgentModel).filter_by(
                tenant_id=tenant_id
            ).all()
            return [self._model_to_entity(agent) for agent in agents]

        except Exception as e:
            logger.error(
                f"Error getting agents for tenant {tenant_id}: {e}"
            )
            return []

        finally:
            try:
                session.close()
            except Exception:
                pass


    def add_to_available_queue(
        self,
        agent_id: int,
        last_call_time: Optional[datetime] = None
    ) -> bool:
        """Add agent to Redis available queue

        Args:
            agent_id: Agent's ID
            last_call_time: Last call timestamp for priority

        Returns:
            True if added successfully
        """
        try:
            return self.agent_queue.add(agent_id, last_call_time)
        except Exception as e:
            logger.error(
                f"Failed to add agent {agent_id} to available queue: {e}"
            )
            return False


    def remove_from_available_queue(
        self,
        agent_id: int
    ) -> bool:
        """Remove agent from Redis available queue

        Args:
            agent_id: Agent's ID

        Returns:
            True if removed successfully
        """
        try:
            return self.agent_queue.remove(agent_id)
        except Exception as e:
            logger.error(
                f"Failed to remove agent {agent_id} from available queue: {e}"
            )
            return False


    def get_next_available_from_queue(self) -> Optional[int]:
        """Get next available agent from Redis queue.
        
        Returns:
            Agent ID or None if no agents available
        """
        try:
            return self.agent_queue.get_next()
        except Exception as e:
            logger.error(
                f"Failed to get next available agent from queue: {e}", 
            )
            return None


    def update_state_in_cache(
        self, 
        agent_id: int, 
        status: str, 
        call_id: Optional[int] = None
    ) -> bool:
        """Update agent state in Redis cache

        Args:
            agent_id: Agent's ID
            status: Current status
            call_id: Current call if BUSY

        Returns:
            True if updated successfully
        """
        try:
            return self.agent_state.set(agent_id, status, call_id)
        except Exception as e:
            logger.error(
                f"Failed to update state in cache for agent {agent_id}: {e}"
            )
            return False


    def get_state_from_cache(
        self,
        agent_id: int
    ) -> Optional[dict]:
        """Get agent state from Redis cache
        
        Args:
            agent_id: Agent's ID
            
        Returns:
            State dictionary or None
        """
        try:
            return self.agent_state.get(agent_id)
        except Exception as e:
            logger.error(
                f"Failed to get state in cache for agent {agent_id}: {e}"
            )
            return None


    def create_and_activate(
        self, 
        reference_code: int, 
        agent_type: int, 
        tenant_id: int = 1
    ) -> ETAgent:
        """Create agent in DB and add to Redis if available

        Args:
            reference_code: Unique reference code
            agent_type: Type 1-4
            tenant_id: Tenant ID

        Returns:
            Created ETAgent entity
        """
        agent = self.create_in_db(
            reference_code=reference_code,
            agent_type=agent_type,
            tenant_id=tenant_id,
            status=AgentStatus.AVAILABLE.value
        )

        try:
            self.add_to_available_queue(agent.id, None)
            self.update_state_in_cache(agent.id, AgentStatus.AVAILABLE.value)
        except Exception:
            logger.error(
                f"Agent {agent.id} created but failed "
                "to fully activate in Redis."
            )

        return agent


    def change_status(
        self, 
        agent_id: int, 
        new_status: str,
        call_id: Optional[int] = None
    ) -> bool:
        """Change agent status in both DB and Redis

        Args:
            agent_id: Agent's ID
            new_status: New status
            call_id: Call ID if becoming BUSY

        Returns:
            True if changed successfully
        """
        valid_statuses = {s.value for s in AgentStatus}
        if new_status not in valid_statuses:
            logger.warning(
                f"Invalid status '{new_status}' provided "
                f"for agent {agent_id}"
            )
            return False

        db_updated = self.update_status_in_db(
            agent_id,
            new_status,
            call_id
        )

        if not db_updated:
            logger.debug(
                f"DB update failed for agent {agent_id} "
                f"to status {new_status}"
            )
            return False

        try:
            match new_status:
                case AgentStatus.AVAILABLE.value:
                    self.add_to_available_queue(agent_id, datetime.now())
                    self.update_state_in_cache(agent_id, new_status)
                case AgentStatus.BUSY.value:
                    self.remove_from_available_queue(agent_id)
                    self.update_state_in_cache(agent_id, new_status, call_id)
                case _:
                    self.remove_from_available_queue(agent_id)
                    self.update_state_in_cache(agent_id, new_status)
        except Exception:
            logger.error(
                f"Failed to synchronize Redis for agent {agent_id} "
                f"after DB update to {new_status}"
            )

        return True


    def _model_to_entity(
        self,
        model: AgentModel
    ) -> ETAgent:
        """Convert SQLAlchemy model to domain entity.
        
        Args:
            model: AgentModel from database
            
        Returns:
            ETAgent entity
        """
        if model is None:
            raise TypeError(
                "Model cannot be None "
                f"in _model_to_entity:  {model}"
            )

        return ETAgent(
            id=model.id,
            tenant_id=model.tenant_id,
            reference_code=model.reference_code,
            agent_type=model.agent_type,
            status=(
                model.status.value if isinstance(model.status, AgentStatus)
                else model.status
            ),
            last_call_time=model.last_call_time,
            current_call_id=model.current_call_id,
            created_at=model.created_at
        )
