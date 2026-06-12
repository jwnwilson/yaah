from fastapi import Request

from adapters.database.stores import SqlProjectStore, SqlRunStore, SqlTeamStore, SqlWorkItemStore


def project_store(request: Request) -> SqlProjectStore:
    return SqlProjectStore(request.app.state.session_factory)


def work_item_store(request: Request) -> SqlWorkItemStore:
    return SqlWorkItemStore(request.app.state.session_factory)


def team_store(request: Request) -> SqlTeamStore:
    return SqlTeamStore(request.app.state.session_factory)


def run_store(request: Request) -> SqlRunStore:
    return SqlRunStore(request.app.state.session_factory)
