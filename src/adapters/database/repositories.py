from adapters.database.orm import (
    AgentDefinitionRow,
    McpServerRow,
    NotificationRow,
    ProjectRow,
    RunEventRow,
    RunRow,
    SecretRow,
    SkillRow,
    TeamRow,
    WorkItemRow,
)
from adapters.database.repository import SqlRepository
from domain.models import (
    AgentDefinition,
    McpServer,
    Notification,
    Project,
    Run,
    RunEvent,
    Secret,
    Skill,
    Team,
    WorkItem,
)


class ProjectRepository(SqlRepository[Project]):
    orm_model = ProjectRow
    dto = Project


class WorkItemRepository(SqlRepository[WorkItem]):
    orm_model = WorkItemRow
    dto = WorkItem


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


class SkillRepository(SqlRepository[Skill]):
    orm_model = SkillRow
    dto = Skill


class McpServerRepository(SqlRepository[McpServer]):
    orm_model = McpServerRow
    dto = McpServer


class SecretRepository(SqlRepository[Secret]):
    orm_model = SecretRow
    dto = Secret


class NotificationRepository(SqlRepository[Notification]):
    orm_model = NotificationRow
    dto = Notification
