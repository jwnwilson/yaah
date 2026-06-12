import pytest

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.stores import SqlRunStore, SqlTeamStore
from adapters.database.tables import metadata
from domain.models import Run, RunStatus
from domain.teams import default_team


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return make_session_factory(engine)


def test_team_roundtrip_with_agents(session_factory):
    store = SqlTeamStore(session_factory)
    team, agents = default_team(owner_id="u1")
    store.add(team, agents)
    assert store.get(team.id, owner_id="u1").name == "Default Team"
    assert store.get(team.id, owner_id="u2") is None
    assert [a.role for a in store.agents(team.id)] == [a.role for a in agents]
    assert [t.id for t in store.list("u1")] == [team.id]


def test_run_roundtrip_and_update(session_factory):
    store = SqlRunStore(session_factory)
    r = store.add(Run(task_id="t1", team_id="tm1"))
    r = r.model_copy(update={"status": RunStatus.RUNNING, "stage": "plan"})
    store.update(r)
    assert store.get(r.id).status == RunStatus.RUNNING
    assert [x.id for x in store.list_for_task("t1")] == [r.id]
