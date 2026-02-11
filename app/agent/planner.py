"""
Planner — LLM-powered execution plan generator

Takes a user prompt + available tools → structured JSON execution plan.
Uses Gemini 2.5 Flash (thinking mode) for complex plans, and short-circuits
simple queries to a single llm_generate step.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import json

from app.orchestrator.gemini_provider import get_gemini_provider, GeminiProvider
from app.orchestrator.strategies import classify_task_complexity_keywords, TaskComplexity


@dataclass
class PlanStep:
    """A single step in an execution plan"""
    step_id: int
    tool_name: str
    description: str
    args: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    """Complete execution plan for a user request"""
    goal: str
    complexity: str
    steps: List[PlanStep] = field(default_factory=list)
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "complexity": self.complexity,
            "reasoning": self.reasoning,
            "steps": [
                {
                    "step_id": s.step_id,
                    "tool_name": s.tool_name,
                    "description": s.description,
                    "args": s.args,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ExecutionPlan":
        steps = [
            PlanStep(
                step_id=s["step_id"],
                tool_name=s["tool_name"],
                description=s.get("description", ""),
                args=s.get("args", {}),
                depends_on=s.get("depends_on", []),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            goal=data.get("goal", ""),
            complexity=data.get("complexity", "simple"),
            steps=steps,
            reasoning=data.get("reasoning", ""),
            metadata=data.get("metadata", {}),
        )


class Planner:
    """
    LLM-powered plan generator.
    
    For simple queries → single-step plan (no LLM overhead for planning).
    For complex tasks → calls Gemini to generate a multi-step plan.
    """

    # Complexity threshold: below this, skip AI planning
    SIMPLE_COMPLEXITIES = {TaskComplexity.SIMPLE}

    def __init__(self):
        self.gemini = get_gemini_provider()

    async def create_plan(
        self,
        user_prompt: str,
        available_tools: List[Dict[str, Any]],
        memory_context: str = "",
    ) -> ExecutionPlan:
        """
        Generate an execution plan for the user's request.

        Args:
            user_prompt: The user's natural language request
            available_tools: Tool schemas from ToolRegistry.list_tools()
            memory_context: Previous conversation context (optional)

        Returns:
            ExecutionPlan with ordered steps
        """
        # Fast path: simple queries get a single llm_generate step
        complexity = classify_task_complexity_keywords(user_prompt)
        if complexity in self.SIMPLE_COMPLEXITIES:
            return self._create_simple_plan(user_prompt, complexity.value)

        # Complex path: ask LLM to generate a structured plan
        return await self._create_ai_plan(user_prompt, available_tools, memory_context, complexity.value)

    def _create_simple_plan(self, user_prompt: str, complexity: str) -> ExecutionPlan:
        """Create a single-step plan for simple queries (no LLM overhead)"""
        return ExecutionPlan(
            goal=user_prompt,
            complexity=complexity,
            reasoning="Simple query — direct LLM response, no planning needed.",
            steps=[
                PlanStep(
                    step_id=0,
                    tool_name="llm_generate",
                    description="Generate direct response",
                    args={
                        "prompt": user_prompt,
                        "provider": "groq",   # Fast provider for simple queries
                        "temperature": 0.4,
                    },
                    depends_on=[],
                )
            ],
        )

    async def _create_ai_plan(
        self,
        user_prompt: str,
        available_tools: List[Dict[str, Any]],
        memory_context: str,
        complexity: str,
    ) -> ExecutionPlan:
        """Use LLM to generate a multi-step execution plan"""

        # Build tool descriptions for the prompt
        tool_descriptions = self._format_tools_for_prompt(available_tools)

        context_block = ""
        if memory_context:
            context_block = f"""
CONVERSATION CONTEXT (previous exchanges in this session):
{memory_context}
"""

        planning_prompt = f"""You are the planning engine for an autonomous AI agent called minimal.ai.

Your job: analyze the user's request and create a structured execution plan using the available tools.

AVAILABLE TOOLS:
{tool_descriptions}

{context_block}

USER REQUEST: "{user_prompt}"

RULES:
1. Break the task into 1-6 ordered steps using ONLY the available tools.
2. Each step must use exactly one tool by its exact name.
3. Use "llm_generate" for any text generation, analysis, or reasoning.
4. Use "llm_analyze_image" ONLY if the user explicitly provides an image.
5. Use "send_email" ONLY if the user explicitly asks to send an email.
6. Steps can reference outputs of previous steps via depends_on.
7. For the "llm_generate" tool args, include "prompt" with the specific sub-task prompt.
8. Include "provider" in args: use "groq" for quick factual tasks, "gemini" for complex reasoning/coding.
9. Keep it minimal — don't add unnecessary steps.

Respond ONLY with valid JSON (no markdown, no extra text):
{{
    "goal": "Brief description of the overall goal",
    "complexity": "{complexity}",
    "reasoning": "Why you chose this plan",
    "steps": [
        {{
            "step_id": 0,
            "tool_name": "tool_name_here",
            "description": "What this step does",
            "args": {{"key": "value"}},
            "depends_on": []
        }}
    ]
}}"""

        try:
            result = await self.gemini.generate(
                prompt=planning_prompt,
                model=GeminiProvider.FLASH_2_5,
                temperature=0.3,
            )

            plan_data = self._parse_plan_json(result["text"])
            plan = ExecutionPlan.from_dict(plan_data)
            plan.metadata["planning_tokens"] = result.get("tokens_used", 0)
            plan.metadata["planning_latency_ms"] = result.get("latency_ms", 0)
            return plan

        except Exception as e:
            print(f"⚠️ AI planning failed: {e}. Falling back to single-step plan.")
            return self._create_fallback_plan(user_prompt, complexity)

    def _create_fallback_plan(self, user_prompt: str, complexity: str) -> ExecutionPlan:
        """Fallback plan when AI planning fails"""
        return ExecutionPlan(
            goal=user_prompt,
            complexity=complexity,
            reasoning="AI planning failed — falling back to direct LLM response.",
            steps=[
                PlanStep(
                    step_id=0,
                    tool_name="llm_generate",
                    description="Generate direct response (fallback)",
                    args={
                        "prompt": user_prompt,
                        "provider": "gemini",
                        "model": "gemini-2.5-flash",
                        "temperature": 0.5,
                    },
                    depends_on=[],
                )
            ],
        )

    def _format_tools_for_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """Format tool schemas into a readable string for the LLM"""
        lines = []
        for i, tool in enumerate(tools, 1):
            params = tool.get("parameters", {}).get("properties", {})
            param_strs = []
            for pname, pinfo in params.items():
                param_strs.append(f"    - {pname} ({pinfo.get('type', 'any')}): {pinfo.get('description', '')}")
            param_block = "\n".join(param_strs) if param_strs else "    (no parameters)"

            lines.append(
                f"{i}. **{tool['name']}** [{tool.get('category', 'custom')}]\n"
                f"   {tool['description']}\n"
                f"   Parameters:\n{param_block}"
            )
        return "\n\n".join(lines)

    def _parse_plan_json(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON from LLM response"""
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            try:
                return json.loads(text[json_start:json_end])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse plan JSON from LLM response: {text[:200]}")


# ─── Singleton ───────────────────────────────────────────────────────────────

_planner: Optional["Planner"] = None


def get_planner() -> Planner:
    """Get or create the global planner instance"""
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner
