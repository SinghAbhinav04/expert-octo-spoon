"""
Image Analysis Tool — Wraps Gemini vision capabilities as an agent tool.

Used for understanding, analyzing, and describing images.
"""
from app.agent.tool_registry import Tool, ToolResult, ToolParameter, ToolCategory

from app.orchestrator.gemini_provider import get_gemini_provider, GeminiProvider


class ImageAnalysisTool(Tool):
    """Analyze images using Gemini 3 Flash Preview (vision model)"""

    def __init__(self):
        super().__init__(
            name="llm_analyze_image",
            description=(
                "Analyze or understand an image. Use ONLY when the user explicitly "
                "provides an image to analyze. Supports image description, OCR, "
                "visual question answering, and diagram understanding."
            ),
            category=ToolCategory.VISION,
            parameters=[
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="What to analyze about the image (e.g., 'Describe this image', 'What text is in this image?')",
                    required=True,
                ),
                ToolParameter(
                    name="image_data",
                    type="string",
                    description="Base64-encoded image data",
                    required=False,
                ),
                ToolParameter(
                    name="mime_type",
                    type="string",
                    description="Image MIME type",
                    required=False,
                    default="image/jpeg",
                    enum=["image/jpeg", "image/png", "image/webp", "image/gif"],
                ),
            ],
            requires_confirmation=False,
        )

    async def execute(self, **kwargs) -> ToolResult:
        """Execute image analysis"""
        prompt = kwargs.get("prompt")
        if not prompt:
            return ToolResult(success=False, error="'prompt' is required")

        image_data = kwargs.get("image_data")
        mime_type = kwargs.get("mime_type", "image/jpeg")

        try:
            gemini = get_gemini_provider()

            if image_data:
                # Actual image analysis
                import base64
                image_bytes = base64.b64decode(image_data)
                result = await gemini.understand_image(
                    prompt=prompt,
                    image_data=image_bytes,
                    mime_type=mime_type,
                    model=GeminiProvider.FLASH_3_0,
                )
            else:
                # Text-only prompt about images (fallback)
                result = await gemini.generate(
                    prompt=prompt,
                    model=GeminiProvider.FLASH_3_0,
                    temperature=0.4,
                )

            return ToolResult(
                success=True,
                output=result["text"],
                tokens_used=result.get("tokens_used", 0),
                latency_ms=result.get("latency_ms", 0),
                metadata={
                    "model": result.get("model", GeminiProvider.FLASH_3_0),
                    "provider": "gemini",
                    "had_image": bool(image_data),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Image analysis failed: {str(e)}",
            )
