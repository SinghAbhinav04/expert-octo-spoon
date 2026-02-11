"""
Executor — Agent execution engine (the agent loop)

Takes an ExecutionPlan and runs it step-by-step:
1. Resolve tool from registry
2. Inject previous step outputs into args
3. Execute tool
4. Store step result in MongoDB
5. On failure: retry once, or skip with error
6. Compile final response
"""
from typing import Dict, Any, List, Optional
import time
import re

from app.agent.tool_registry import get_tool_registry, ToolResult
from app.agent.planner import get_planner, ExecutionPlan, PlanStep
from app.agent.memory import get_memory_manager
from app.db import queries
from app.config import settings


class AgentResult:
    """Final result from an agent run"""

    def __init__(
        self,
        request_id: str,
        response: str,
        plan: Dict[str, Any],
        steps_executed: List[Dict[str, Any]],
        total_tokens: int = 0,
        latency_ms: int = 0,
        provider: str = "",
        models_used: Optional[List[str]] = None,
    ):
        self.request_id = request_id
        self.response = response
        self.plan = plan
        self.steps_executed = steps_executed
        self.total_tokens = total_tokens
        self.latency_ms = latency_ms
        self.provider = provider
        self.models_used = models_used or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "response": self.response,
            "plan": self.plan,
            "steps_executed": self.steps_executed,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "models_used": self.models_used,
            "steps_count": len(self.steps_executed),
        }


class AgentRunner:
    """
    Core agent execution engine.
    
    Orchestrates: Memory → Plan → Execute Tools → Store → Respond
    """

    def __init__(self):
        self.registry = get_tool_registry()
        self.planner = get_planner()
        self.memory = get_memory_manager()

    async def run(
        self,
        db,
        session_id: str,
        user_id: str,
        user_prompt: str,
    ) -> AgentResult:
        """
        Main entry point: process a user request through the full agent pipeline.

        Flow:
        1. Fetch memory context for this session
        2. Generate execution plan via Planner
        3. Execute each step in order
        4. Compile final response
        5. Store interaction in memory
        6. Return result

        Args:
            db: Database instance
            session_id: Current session ID
            user_id: Authenticated user ID
            user_prompt: The user's natural language request

        Returns:
            AgentResult with response, plan, steps, and metadata
        """
        start_time = time.time()
        max_steps = getattr(settings, "AGENT_MAX_STEPS", 10)

        # Step 1: Get session memory context
        memory_context = await self.memory.get_session_context(db, session_id)
        print(f"🧠 Memory context: {len(memory_context)} chars")

        # Step 2: Generate execution plan
        print(f"📋 Planning for: {user_prompt[:80]}...")
        available_tools = self.registry.list_tools()
        plan = await self.planner.create_plan(user_prompt, available_tools, memory_context)
        print(f"✅ Plan: {len(plan.steps)} steps | Complexity: {plan.complexity} | {plan.reasoning}")

        # Cap step count
        if len(plan.steps) > max_steps:
            plan.steps = plan.steps[:max_steps]
            print(f"⚠️ Plan capped to {max_steps} steps")

        # Step 3: Create request record in MongoDB
        request_record = await queries.create_request(
            db,
            session_id=session_id,
            user_prompt=user_prompt,
            intent=plan.complexity,
            strategy="agent_" + ("single" if len(plan.steps) == 1 else "multi"),
        )
        request_id = request_record["id"]

        # Step 4: Store the plan
        await self._store_plan(db, request_id, plan)

        # Step 5: Execute steps
        step_results: List[Dict[str, Any]] = []
        step_outputs: Dict[int, str] = {}  # step_id -> output text
        total_tokens = plan.metadata.get("planning_tokens", 0)
        models_used = set()

        for step in plan.steps:
            print(f"  🔧 Step {step.step_id}: {step.tool_name} — {step.description}")

            # Inject previous step outputs into args
            resolved_args = self._resolve_args(step.args, step_outputs)

            # Execute with retry
            result = await self._execute_with_retry(step.tool_name, resolved_args)

            # Extract output text
            output_text = ""
            if result.success and result.output is not None:
                output_text = str(result.output) if not isinstance(result.output, str) else result.output
            elif result.error:
                output_text = f"[ERROR] {result.error}"

            step_outputs[step.step_id] = output_text
            total_tokens += result.tokens_used

            # Track models
            model_name = result.metadata.get("model", step.tool_name)
            models_used.add(model_name)

            # Store step in MongoDB
            await queries.create_step(
                db,
                request_id=request_id,
                step_type=f"agent_tool:{step.tool_name}",
                model_name=model_name,
                input_prompt=str(resolved_args.get("prompt", resolved_args)),
                output_text=output_text[:10000],  # Cap output size
                tokens_used=result.tokens_used,
                latency_ms=result.latency_ms,
            )

            step_results.append({
                "step_id": step.step_id,
                "tool_name": step.tool_name,
                "description": step.description,
                "success": result.success,
                "output": output_text[:2000],  # Trim for API response
                "error": result.error,
                "latency_ms": result.latency_ms,
                "tokens_used": result.tokens_used,
            })

            status = "✅" if result.success else "❌"
            print(f"  {status} Step {step.step_id} done ({result.latency_ms}ms)")

        # Step 6: Compile final response (last successful step output)
        final_response = self._compile_response(step_outputs, plan)

        # Step 7: Calculate totals and store response
        total_latency_ms = int((time.time() - start_time) * 1000)
        models_list = list(models_used)

        await queries.create_response(
            db,
            request_id=request_id,
            final_response=final_response,
            models_used={
                "models": models_list,
                "strategy": "agent",
                "plan": plan.to_dict(),
            },
            latency_ms=total_latency_ms,
            estimated_cost=self._estimate_cost(total_tokens),
        )

        # Step 8: Store in memory
        await self.memory.store_interaction(
            db,
            session_id=session_id,
            user_id=user_id,
            prompt=user_prompt,
            response=final_response,
            plan=plan.to_dict(),
        )

        print(f"🏁 Agent run complete: {total_latency_ms}ms | {total_tokens} tokens | {len(step_results)} steps")

        return AgentResult(
            request_id=request_id,
            response=final_response,
            plan=plan.to_dict(),
            steps_executed=step_results,
            total_tokens=total_tokens,
            latency_ms=total_latency_ms,
            provider=", ".join(models_list),
            models_used=models_list,
        )

    async def _execute_with_retry(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """Execute a tool with one retry on failure"""
        retry_enabled = getattr(settings, "AGENT_RETRY_ON_FAILURE", True)

        result = await self.registry.execute(tool_name, **args)

        if not result.success and retry_enabled:
            print(f"  ⚠️ Retrying {tool_name}...")
            result = await self.registry.execute(tool_name, **args)

        return result

    def _resolve_args(self, args: Dict[str, Any], step_outputs: Dict[int, str]) -> Dict[str, Any]:
        """
        Replace template variables like {step_0_output} with actual step outputs.
        """
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str):
                # Replace {step_N_output} patterns
                def replacer(match):
                    step_id = int(match.group(1))
                    return step_outputs.get(step_id, f"[step {step_id} output unavailable]")

                resolved[key] = re.sub(r"\{step_(\d+)_output\}", replacer, value)
            else:
                resolved[key] = value
        return resolved

    def _compile_response(self, step_outputs: Dict[int, str], plan: ExecutionPlan) -> str:
        """
        Compile the final response from step outputs.
        Uses the last step's output as the primary response.
        """
        if not step_outputs:
            return "I couldn't generate a response. Please try again."

        # Get the last step's output
        last_step_id = max(step_outputs.keys())
        last_output = step_outputs[last_step_id]

        # If it's an error, try to find the last successful output
        if last_output.startswith("[ERROR]"):
            for sid in sorted(step_outputs.keys(), reverse=True):
                if not step_outputs[sid].startswith("[ERROR]"):
                    return step_outputs[sid]
            return "An error occurred while processing your request. Please try again."

        return last_output

    async def _store_plan(self, db, request_id: str, plan: ExecutionPlan) -> None:
        """Store execution plan in MongoDB"""
        try:
            await queries.store_agent_plan(db, request_id, plan.to_dict())
        except Exception as e:
            print(f"⚠️ Failed to store plan: {e}")

    def _estimate_cost(self, total_tokens: int) -> float:
        """Rough cost estimation"""
        return (total_tokens / 1_000_000) * 0.10


# ─── Singleton ───────────────────────────────────────────────────────────────

_runner: Optional["AgentRunner"] = None


def get_agent_runner() -> AgentRunner:
    """Get or create the global agent runner"""
    global _runner
    if _runner is None:
        _runner = AgentRunner()
    return _runner
