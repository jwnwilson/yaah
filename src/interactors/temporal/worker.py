import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from interactors.temporal.activities import RunActivities
from interactors.temporal.config import TemporalConfig
from interactors.temporal.workflows import RunWorkflow


def _build_forge(profile: str):
    if profile != "remote":
        from adapters.forge.fake import FakeGitForge
        return FakeGitForge()
    from adapters.forge.github_app import GitHubApp
    from interactors.api.settings import Settings
    s = Settings()
    return GitHubApp(app_id=s.github_app_id, private_key=s.github_private_key,
                     installation_id=s.github_installation_id, repo=s.github_repo,
                     base_branch=s.github_base_branch)


def build_activities(database_url: str, profile: str = "local") -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    storage = LocalStorageAdapter(base_dir="data/workspaces")
    from adapters.git.local_git import LocalGit
    git = LocalGit()
    forge = _build_forge(profile)
    acts = RunActivities(factory, FakeAgentRuntime(storage=storage), storage, git, forge)
    return [acts.persist_run_state, acts.record_event, acts.run_stage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr]


async def run_worker(config: TemporalConfig, database_url: str, profile: str) -> None:  # pragma: no cover
    client = await Client.connect(config.address, namespace=config.namespace)
    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[RunWorkflow],
        activities=build_activities(database_url, profile=profile),
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    await worker.run()


def main(config: TemporalConfig, database_url: str, profile: str) -> None:  # pragma: no cover
    asyncio.run(run_worker(config, database_url, profile))


def run() -> None:  # pragma: no cover
    from interactors.api.settings import Settings
    settings = Settings()
    main(TemporalConfig.from_settings(settings), settings.database_url, settings.profile)


if __name__ == "__main__":  # pragma: no cover
    run()
