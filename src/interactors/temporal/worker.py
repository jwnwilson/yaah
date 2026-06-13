import asyncio
import os
import shutil
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


def _build_model_provider(settings):
    gw = settings.model_gateway
    use_litellm = gw == "litellm" or (gw == "auto" and bool(settings.litellm_base_url))
    if use_litellm:
        from adapters.model.litellm import LiteLLMProvider
        return LiteLLMProvider(settings.litellm_base_url or "", settings.litellm_api_key or "",
                               default_model=settings.agent_model)
    from adapters.model.anthropic import AnthropicProvider
    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.agent_model)


def _build_runtime(settings, storage):
    choice = settings.agent_runtime
    has_key = bool(settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
    use_claude = (
        choice == "claude_code" or (choice == "auto" and has_key and shutil.which("claude"))
    )
    if use_claude:
        from adapters.runtime.claude_code import ClaudeCodeRuntime
        from adapters.skills.fetcher import SkillFetcher
        return ClaudeCodeRuntime(_build_model_provider(settings), skills=SkillFetcher())
    return FakeAgentRuntime(storage=storage)


def build_activities(database_url: str, profile: str = "local") -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    storage = LocalStorageAdapter(base_dir="data/workspaces")
    from adapters.git.local_git import LocalGit
    from interactors.api.settings import Settings
    settings = Settings()
    git = LocalGit()
    forge = _build_forge(profile)
    runtime = _build_runtime(settings, storage)
    cipher = None
    if settings.secret_key:
        from adapters.secrets.cipher import FernetCipher
        cipher = FernetCipher(settings.secret_key)
    from adapters.notify.inapp import InAppChannel
    from adapters.notify.ports import NotificationDispatcher
    notifier = NotificationDispatcher([InAppChannel()])
    acts = RunActivities(factory, runtime, storage, git, forge, cipher=cipher, notifier=notifier)
    return [acts.persist_run_state, acts.record_event, acts.record_usage, acts.run_stage,
            acts.cleanup_workspace, acts.provision_workspace, acts.open_pr,
            acts.record_notification]


async def run_worker(  # pragma: no cover
    config: TemporalConfig, database_url: str, profile: str
) -> None:
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
