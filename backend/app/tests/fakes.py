"""A stand-in for the Anthropic client so tests never call the real API."""
from types import SimpleNamespace
from app.services.coding_prompts import RECORD_TOOL_NAME


def tool_message(tool_input: dict, model: str = "claude-test"):
    return SimpleNamespace(
        model=model, stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", name=RECORD_TOOL_NAME, input=tool_input)],
    )


def text_message(text: str = "Here are the codes...", stop_reason: str = "end_turn"):
    return SimpleNamespace(model="claude-test", stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=text)])


class FakeMessages:
    """Returns the queued responses in order (the last one repeats). An Exception
    in the queue is raised instead. Every request's kwargs are kept in `calls`."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(result, Exception):
            raise result
        return result


def install(monkeypatch, *responses) -> FakeMessages:
    from app.services import coding_service
    fake = FakeMessages(*responses)
    monkeypatch.setattr(coding_service, "client", SimpleNamespace(messages=fake))
    return fake
