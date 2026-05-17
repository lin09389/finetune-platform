from __future__ import annotations

from langchain_core.messages import HumanMessage

from agent_session.langgraph.provider_adapter import GatewayToolCallingChatModel, ProviderAdapterError, get_chat_model


class FakeProvider:
    def __init__(self, response):
        self.response = response

    async def chat(self, messages, model, api_key, **kwargs):
        return self.response

    def get_default_model(self) -> str:
        return "fake-model"


async def test_gateway_tool_calling_chat_model_parses_openai_tool_calls():
    model = GatewayToolCallingChatModel(
        provider_name="mock",
        model_name="fake-model",
        api_key="secret",
        provider=FakeProvider(
            {
                "raw": {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "function": {"name": "list_files", "arguments": '{"pattern":"**/*"}'},
                                    }
                                ],
                            }
                        }
                    ]
                }
            }
        ),
    ).bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files",
                    "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}},
                },
            }
        ]
    )

    message = await model.ainvoke([HumanMessage(content="inspect repo")])
    assert message.tool_calls[0]["name"] == "list_files"
    assert message.tool_calls[0]["args"]["pattern"] == "**/*"


def test_get_chat_model_requires_saved_api_key(monkeypatch):
    monkeypatch.setattr("agent_session.langgraph.provider_adapter.secure_storage.get", lambda key: {})
    context = type("Context", (), {"provider": "glm", "model": "glm-4"})()
    try:
        get_chat_model(context)
    except ProviderAdapterError as exc:
        assert "API Key" in str(exc)
    else:
        raise AssertionError("Expected ProviderAdapterError when API key is missing")

