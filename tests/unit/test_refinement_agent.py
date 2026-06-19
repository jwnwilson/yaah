import httpx

from adapters.agent.model.fake import FakeModelProvider
from adapters.agent.refinement.anthropic import AnthropicRefinementAgent
from adapters.agent.refinement.fake import FakeRefinementAgent
from domain.refinement import ChatMessage, ChatRole, RefinementContext


def _ctx():
    return RefinementContext(
        project_name="Alpha",
        history=[
            ChatMessage(
                owner_id="u",
                session_id="s",
                role=ChatRole.USER,
                content="add login",
            )
        ],
        hierarchy=[],
        system_prompt="be the lead",
    )


def test_fake_agent_proposes_from_last_message():
    out = FakeRefinementAgent().respond(_ctx())
    assert out.reply
    assert out.proposals and out.proposals[0].title


def test_anthropic_agent_parses_tool_use(monkeypatch):
    agent = AnthropicRefinementAgent(FakeModelProvider())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [
                    {
                        "type": "tool_use",
                        "name": "propose",
                        "input": {
                            "reply": "Here's a plan",
                            "proposals": [
                                {
                                    "kind": "epic",
                                    "title": "Auth",
                                    "body": "",
                                    "acceptance_criteria": [],
                                }
                            ],
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(
        agent,
        "_client_factory",
        lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    out = agent.respond(_ctx())
    assert out.reply == "Here's a plan" and out.proposals[0].kind == "epic"


def test_fake_agent_proposes_feature_and_epic_update_when_epic_scoped():
    from adapters.agent.refinement.fake import FakeRefinementAgent
    from domain.refinement import ChatMessage, ChatRole, RefinementContext

    ctx = RefinementContext(
        project_name="p",
        epic_id="epic-1",
        history=[
            ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER, content="cart flow")
        ],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.epic_update is not None
    assert out.proposals and out.proposals[0].parent_id == "epic-1"
    assert out.proposals[0].kind == "feature"


def test_fake_agent_commits_on_approval_token():
    from adapters.agent.refinement.fake import FakeRefinementAgent
    from domain.refinement import (
        ChatMessage,
        ChatRole,
        RefinementAction,
        RefinementContext,
    )

    ctx = RefinementContext(
        project_name="Alpha",
        history=[ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER,
                             content="go")],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.action == RefinementAction.COMMIT
    assert out.proposals == []


def test_fake_agent_discusses_by_default():
    from adapters.agent.refinement.fake import FakeRefinementAgent
    from domain.refinement import (
        ChatMessage,
        ChatRole,
        RefinementAction,
        RefinementContext,
    )

    ctx = RefinementContext(
        project_name="Alpha",
        history=[ChatMessage(owner_id="u", session_id="s", role=ChatRole.USER,
                             content="build login")],
    )
    out = FakeRefinementAgent().respond(ctx)
    assert out.action == RefinementAction.DISCUSS
    assert out.proposals  # still drafts an epic


def test_anthropic_output_parses_action_from_tool_input():
    # Lock-in: action flows through the schema-derived tool + RefinementOutput(**input).
    from domain.refinement import RefinementAction, RefinementOutput

    schema = RefinementOutput.model_json_schema()
    assert "action" in schema["properties"]
    out = RefinementOutput(**{"reply": "ok", "action": "commit"})
    assert out.action == RefinementAction.COMMIT
