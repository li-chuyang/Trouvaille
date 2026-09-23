"""In-memory message history shared by Runs in one live conversation."""

from typing import Callable, Sequence

from trouvaille.agent import Agent, AgentEvent, RunResult
from trouvaille.messages import Message


class Conversation:
    def __init__(self, agent: Agent, *, history: Sequence[Message] = ()) -> None:
        if any(message.role == "system" for message in history):
            raise ValueError("Conversation history must not contain system messages")
        self.agent = agent
        self._history = tuple(history)

    @property
    def history(self) -> tuple[Message, ...]:
        return self._history

    def run(self, task: str, on_event: Callable[[AgentEvent], None] | None = None) -> RunResult:
        result = self.agent.run(task, on_event=on_event, history=self._history)
        # The first message is the Run's system prompt. Keep it once per model
        # request; only user/assistant/tool messages belong in conversation history.
        self._history += result.messages[1:]
        return result
