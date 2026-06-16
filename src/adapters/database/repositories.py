from sqlalchemy.exc import IntegrityError as SQLIntegrityError

from adapters.database.orm import (
    AgentDefinitionRow,
    AuditEventRow,
    ChatMessageRow,
    ChatSessionRow,
    McpServerRow,
    MemoryProposalRow,
    MessageRow,
    NotificationRow,
    ProjectRow,
    RunEventRow,
    RunRow,
    SecretRow,
    SkillRow,
    TeamRow,
    UsageRecordRow,
    WorkItemAttachmentRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository
from domain.errors import IntegrityConflict
from domain.models import (
    AgentDefinition,
    AuditEvent,
    ChatMessage,
    ChatSession,
    McpServer,
    MemoryProposal,
    Message,
    Notification,
    Project,
    Run,
    RunEvent,
    Secret,
    Skill,
    Team,
    UsageRecord,
    WorkItem,
    WorkItemAttachment,
)


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


class WorkItemAttachmentRepository(SqlRepository[WorkItemAttachment]):
    orm_model = WorkItemAttachmentRow
    dto = WorkItemAttachment
    default_order_by = "created_at"


class TeamRepository(SqlRepository[Team]):
    orm_model = TeamRow
    dto = Team


class AgentDefinitionRepository(SqlRepository[AgentDefinition]):
    # Not owner-scoped: agents are reached through their (owner-scoped) team,
    # and AgentDefinitionRow has no owner_id column — _scoped() skips absent keys.
    orm_model = AgentDefinitionRow
    dto = AgentDefinition
    default_order_by = "id"


class RunRepository(SqlRepository[Run]):
    orm_model = RunRow
    dto = Run


class RunEventRepository(SqlRepository[RunEvent]):
    orm_model = RunEventRow
    dto = RunEvent
    default_order_by = "created_at"


class AuditEventRepository(SqlRepository[AuditEvent]):
    orm_model = AuditEventRow
    dto = AuditEvent
    default_order_by = "created_at"


class SkillRepository(SqlRepository[Skill]):
    orm_model = SkillRow
    dto = Skill


class McpServerRepository(SqlRepository[McpServer]):
    orm_model = McpServerRow
    dto = McpServer


class SecretRepository(SqlRepository[Secret]):
    orm_model = SecretRow
    dto = Secret


class ChatSessionRepository(SqlRepository[ChatSession]):
    orm_model = ChatSessionRow
    dto = ChatSession


class ChatMessageRepository(SqlRepository[ChatMessage]):
    orm_model = ChatMessageRow
    dto = ChatMessage
    default_order_by = "created_at"


class NotificationRepository(SqlRepository[Notification]):
    orm_model = NotificationRow
    dto = Notification


class MessageRepository(SqlRepository[Message]):
    orm_model = MessageRow
    dto = Message
    default_order_by = "-created_at"  # newest-first inbox


class MemoryProposalRepository(SqlRepository[MemoryProposal]):
    orm_model = MemoryProposalRow
    dto = MemoryProposal
    default_order_by = "created_at"


class UsageRecordRepository(SqlRepository[UsageRecord]):
    orm_model = UsageRecordRow
    dto = UsageRecord

    def create(self, obj: UsageRecord) -> UsageRecord:
        data = obj.model_dump()
        data["dedupe_key"] = obj.dedupe_key  # stored column, derived on the DTO
        row = self.orm_model(**data)
        try:
            self._session.add(row)
            self._session.flush()
        except SQLIntegrityError as err:
            raise IntegrityConflict(str(err.orig)) from err
        return self._to_dto(row)

    def _to_dto(self, row: UsageRecordRow) -> UsageRecord:
        data = {
            k: v
            for k, v in row.__dict__.items()
            if not k.startswith("_") and k != "dedupe_key"
        }
        return UsageRecord(**data)
