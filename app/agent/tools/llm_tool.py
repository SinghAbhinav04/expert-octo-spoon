"""
LLM Generate Tool — Wraps existing Gemini/Groq providers as an agent tool.

This is the primary tool the agent uses for text generation, analysis,
coding, reasoning, and all general-purpose LLM tasks.
"""
from app.agent.tool_registry import Tool, ToolResult, ToolParameter, ToolCategory

from app.orchestrator.gemini_provider import get_gemini_provider, GeminiProvider
from app.orchestrator.groq_provider import get_groq_provider, GroqProvider


class LLMGenerateTool(Tool):
    """Text generation using Gemini or Groq LLM providers"""

    def __init__(self):
        super().__init__(
            name="llm_generate",
            description=(
                "Generate text using an LLM. Use for answering questions, writing, "
                "analysis, coding, reasoning, summarization, and any general-purpose "
                "text generation task."
            ),
            category=ToolCategory.LLM,
            parameters=[
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="The prompt or instruction to send to the LLM",
                    required=True,
                ),
                ToolParameter(
                    name="provider",
                    type="string",
                    description=(
                        "Which LLM provider to use. "
                        "'groq' for fast simple tasks, 'gemini' for complex reasoning/coding."
                    ),
                    required=False,
                    default="groq",
                    enum=["groq", "gemini"],
                ),
                ToolParameter(
                    name="model",
                    type="string",
                    description="Specific model override (optional). Leave empty to use provider default.",
                    required=False,
                    default=None,
                ),
                ToolParameter(
                    name="temperature",
                    type="number",
                    description="Sampling temperature 0.0-1.0. Lower = more focused, higher = more creative.",
                    required=False,
                    default=0.7,
                ),
            ],
            requires_confirmation=False,
        )

    async def execute(self, **kwargs) -> ToolResult:
        """Execute LLM generation"""
        prompt = kwargs.get("prompt")
        if not prompt:
            return ToolResult(success=False, error="'prompt' is required")

        provider_name = kwargs.get("provider", "groq")
        temperature = float(kwargs.get("temperature", 0.7))
        model_override = kwargs.get("model")

        try:
            if provider_name == "gemini":
                provider = get_gemini_provider()
                model = model_override or GeminiProvider.FLASH_2_5
            else:
                provider = get_groq_provider()
                model = model_override or GroqProvider.GPT_OSS_120B

            result = await provider.generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
            )

            return ToolResult(
                success=True,
                output=result["text"],
                tokens_used=result.get("tokens_used", 0),
                latency_ms=result.get("latency_ms", 0),
                metadata={
                    "model": result.get("model", model),
                    "provider": provider_name,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"LLM generation failed: {str(e)}",
                metadata={"provider": provider_name},
            )
