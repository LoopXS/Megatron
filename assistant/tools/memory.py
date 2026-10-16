"""Memory tools for the assistant: write the per-user fact store (risk auto).

Reading memory is not a tool: ``MemoryStore.render`` is injected into the
system prompt every turn, so the model reads facts for free (spec section 9).
Writing happens only through these two ``auto`` tools, which are bound to the
store built by the glue.  Only the standard library and the assistant core
types are imported, so the module loads standalone in tests.
"""

from .._agent_core import Tool, ToolContext, ToolResult
from .._memory_core import MemoryStore


def build_memory_tools(store: MemoryStore) -> list[Tool]:
    """Build ``memory.remember`` and ``memory.forget`` bound to ``store``.

    Both handlers act on ``context.user_id`` only, so one user's facts are
    never visible to or writable by another; the store already keeps users
    isolated.  Forgetting an unknown id is reported as not found rather than
    raised.
    """

    async def remember(arguments, context: ToolContext) -> ToolResult:
        fact = store.add(context.user_id, arguments.get("text", ""))
        return ToolResult(f"Remembered as {fact.id}.")

    async def forget(arguments, context: ToolContext) -> ToolResult:
        fact_id = arguments.get("id", "")
        if store.forget(context.user_id, fact_id):
            return ToolResult(f"Forgot {fact_id}.")
        return ToolResult(f"No fact with id {fact_id} to forget.")

    return [
        Tool(
            name="memory.remember",
            description=(
                "Save a durable fact about the user to remember in future "
                "turns. Use when the user states something worth keeping."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The fact to remember.",
                    }
                },
                "required": ["text"],
            },
            risk="auto",
            handler=remember,
            summarize=lambda arguments: arguments.get("text", ""),
        ),
        Tool(
            name="memory.forget",
            description=(
                "Delete a remembered fact by its id (shown in the memory "
                "block and by memory.remember)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The id of the fact to forget.",
                    }
                },
                "required": ["id"],
            },
            risk="auto",
            handler=forget,
            summarize=lambda arguments: arguments.get("id", ""),
        ),
    ]
