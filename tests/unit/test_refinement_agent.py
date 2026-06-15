import httpx

from adapters.agent.model.fake import FakeModelProvider
from adapters.agent.refinement.anthropic import AnthropicRefinementAgent
from adapters.agent.refinement.fake import FakeRefinementAgent
from domain.models import ChatMessage, ChatRole
from domain.refinement import RefinementContext


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
