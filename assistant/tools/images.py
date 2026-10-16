"""Image tools for the assistant: search and generate images (risk auto).

Both side-effecting primitives are injected: ``search`` resolves image URLs
and ``download`` saves one to a local path, while ``generate`` renders a
prompt to a local path (or ``None`` when the provider fails).  No
image-generation provider is bundled, so passing ``generate=None`` still
builds the tool but leaves it returning a clear "not configured" error.  The
module never opens a socket and stays unit-testable; the Telethon glue
supplies the real callables.  Only the standard library and the assistant
core types are imported here, so the module loads standalone in tests.  See
spec section 8.
"""

from .._agent_core import Tool, ToolContext, ToolResult

#: How many images ``images.image_search`` fetches when ``n`` is omitted.
DEFAULT_IMAGE_COUNT = 4


async def _image_search(search, download, arguments) -> ToolResult:
    """Find image URLs, download each, and return their local paths."""

    query = arguments.get("query", "")
    n = arguments.get("n", DEFAULT_IMAGE_COUNT)
    urls = await search(query, n)
    if not urls:
        return ToolResult(f"No images found for: {query}")

    paths = [await download(url) for url in urls]
    caption = f"Found {len(paths)} image(s) for: {query}"
    return ToolResult(caption, files=paths)


async def _image_generate(generate, arguments) -> ToolResult:
    """Render ``prompt`` to a local file, or say no provider is configured."""

    if generate is None:
        return ToolResult(
            "image generation is not configured (set AI_IMAGE_API_KEY)",
            error=True,
        )

    prompt = arguments.get("prompt", "")
    path = await generate(prompt)
    if path is None:
        return ToolResult(
            f"image generation failed for: {prompt}", error=True
        )
    return ToolResult(f"Generated image for: {prompt}", files=[path])


def build_image_tools(search, download, generate=None) -> list[Tool]:
    """Build ``images.image_search`` and ``images.image_generate``.

    ``search`` is ``async (query, n) -> list[str]`` of image URLs; ``download``
    is ``async (url) -> str`` returning the saved local path; ``generate`` is
    ``async (prompt) -> str | None`` and is optional (``None`` disables
    generation with a clear error).  Both tools are risk ``auto``.
    """

    async def image_search(arguments, context: ToolContext) -> ToolResult:
        return await _image_search(search, download, arguments)

    async def image_generate(arguments, context: ToolContext) -> ToolResult:
        return await _image_generate(generate, arguments)

    return [
        Tool(
            name="images.image_search",
            description=(
                "Search for images matching a query, download them to the "
                "workspace, and return their file paths."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search images for.",
                    },
                    "n": {
                        "type": "integer",
                        "description": "How many images to return.",
                    },
                },
                "required": ["query"],
            },
            risk="auto",
            handler=image_search,
            summarize=lambda arguments: arguments.get("query", ""),
        ),
        Tool(
            name="images.image_generate",
            description=(
                "Generate a new image from a text prompt and return its "
                "file path."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt describing the image.",
                    }
                },
                "required": ["prompt"],
            },
            risk="auto",
            handler=image_generate,
            summarize=lambda arguments: arguments.get("prompt", ""),
        ),
    ]
