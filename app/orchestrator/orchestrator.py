"""
Core LLM orchestration engine - Multi-Provider

The orchestrator handles:
1. Intent classification (via AI meta-decision)
2. Strategy selection (which model + provider to use)
3. Task execution (single-step, multi-step, image understanding)
4. Response generation

Providers:
- Gemini (gemini-2.5-flash, gemini-3-flash-preview)
- Groq (openai/gpt-oss-120b)
"""
from typing import Dict, Any, List, Optional
import time
import uuid

from app.orchestrator.gemini_provider import get_gemini_provider, GeminiProvider
from app.orchestrator.groq_provider import get_groq_provider, GroqProvider
from app.orchestrator import strategies
from app.db import queries


class Orchestrator:
    """Core orchestration engine for minimal.ai"""
    
    def __init__(self):
        self.gemini = get_gemini_provider()
        self.groq = get_groq_provider()
    
    def _get_provider(self, provider_name: str):
        """Get the correct provider instance"""
        if provider_name == strategies.PROVIDER_GROQ:
            return self.groq
        return self.gemini
    
    async def process_request(
        self,
        db,
        session_id,
        user_prompt: str
    ) -> Dict[str, Any]:
        """
        Main entry point: process a user request end-to-end
        
        Flow:
        1. Classify intent and complexity (AI meta-decision via Gemini 3 Flash)
        2. Select strategy, model, and provider
        3. Execute steps based on strategy
        4. Generate final response
        5. Store everything in MongoDB
        
        Returns:
            Dict with request_id, response, steps, metadata
        """
        start_time = time.time()
        
        # Step 1: 🧠 AI-POWERED strategy selection
        print(f"🤖 Analyzing task with AI meta-decision system...")
        strategy_config = await strategies.select_strategy_with_ai(user_prompt, self.gemini)
        
        ai_analysis = strategy_config.get("ai_analysis", {})
        complexity = ai_analysis.get("complexity", "moderate")
        provider_name = strategy_config.get("provider", strategies.PROVIDER_GROQ)
        
        print(f"✅ AI Decision: {strategy_config['strategy'].value} | Model: {strategy_config['model']} | Provider: {provider_name}")
        print(f"   Reasoning: {ai_analysis.get('reasoning', 'N/A')}")
        
        # Step 2: Create request in MongoDB
        request = await queries.create_request(
            db,
            session_id=session_id,
            user_prompt=user_prompt,
            intent=complexity,
            strategy=strategy_config["strategy"].value
        )
        
        request_id = request['id']
        
        # Step 3: Execute based on AI-selected strategy
        if strategy_config["strategy"] == strategies.StrategyType.SINGLE_STEP:
            response_data = await self._execute_single_step(
                db, request_id, user_prompt, strategy_config
            )
        
        elif strategy_config["strategy"] == strategies.StrategyType.MULTI_STEP:
            response_data = await self._execute_multi_step(
                db, request_id, user_prompt, strategy_config
            )
        
        elif strategy_config["strategy"] == strategies.StrategyType.IMAGE_UNDERSTANDING:
            response_data = await self._execute_image_understanding(
                db, request_id, user_prompt, strategy_config
            )
        
        else:
            # Fallback to single-step
            response_data = await self._execute_single_step(
                db, request_id, user_prompt, strategy_config
            )
        
        # Step 4: Store final response with AI meta-decision data
        total_latency_ms = int((time.time() - start_time) * 1000)
        meta_tokens = strategy_config.get("meta_decision_tokens", 0)
        total_tokens_with_meta = response_data["total_tokens"] + meta_tokens
        
        final_response = await queries.create_response(
            db,
            request_id=request_id,
            final_response=response_data["text"],
            models_used={
                "models": response_data["models_used"],
                "meta_decision": strategy_config.get("ai_analysis", {}),
                "strategy": strategy_config["strategy"].value,
                "provider": provider_name
            },
            latency_ms=total_latency_ms,
            estimated_cost=self._estimate_cost(total_tokens_with_meta, provider_name)
        )
        
        return {
            "request_id": str(request_id),
            "response": response_data["text"],
            "strategy": strategy_config["strategy"].value,
            "complexity": complexity,
            "provider": provider_name,
            "models_used": response_data["models_used"],
            "total_tokens": total_tokens_with_meta,
            "latency_ms": total_latency_ms,
            "steps_count": len(response_data.get("steps", [])),
            "ai_reasoning": ai_analysis.get("reasoning", None)
        }
    
    async def _execute_single_step(
        self,
        db,
        request_id: str,
        user_prompt: str,
        strategy_config: Dict
    ) -> Dict[str, Any]:
        """Execute single-step strategy: direct LLM call to appropriate provider"""
        
        provider = self._get_provider(strategy_config.get("provider", strategies.PROVIDER_GROQ))
        
        result = await provider.generate(
            prompt=user_prompt,
            model=strategy_config["model"],
            temperature=strategy_config.get("temperature", 0.7),
        )
        
        # Log step
        await queries.create_step(
            db,
            request_id=request_id,
            step_type="single_generation",
            model_name=result["model"],
            input_prompt=user_prompt,
            output_text=result["text"],
            tokens_used=result["tokens_used"],
            latency_ms=result["latency_ms"]
        )
        
        return {
            "text": result["text"],
            "models_used": [result["model"]],
            "total_tokens": result["tokens_used"],
            "steps": [result]
        }
    
    async def _execute_multi_step(
        self,
        db,
        request_id: str,
        user_prompt: str,
        strategy_config: Dict
    ) -> Dict[str, Any]:
        """
        Execute multi-step strategy:
        1. Break down task (using fastest model)
        2. Execute main task with brain model (gemini-2.5-flash)
        """
        
        # Step 1: Task decomposition (always use Gemini 3 Flash - fastest)
        decompose_prompt = f"""
        Break down this task into 2-4 concrete steps:
        
        Task: {user_prompt}
        
        Respond with a numbered list of steps only.
        """
        
        decomposition = await self.gemini.generate(
            prompt=decompose_prompt,
            model=GeminiProvider.FLASH_3_0,
            temperature=0.3
        )
        
        await queries.create_step(
            db,
            request_id=request_id,
            step_type="task_decomposition",
            model_name=decomposition["model"],
            input_prompt=decompose_prompt,
            output_text=decomposition["text"],
            tokens_used=decomposition["tokens_used"],
            latency_ms=decomposition["latency_ms"]
        )
        
        # Step 2: Execute with the selected provider/model
        provider = self._get_provider(strategy_config.get("provider", strategies.PROVIDER_GEMINI))
        
        execution = await provider.generate(
            prompt=user_prompt,
            model=strategy_config["model"],
            temperature=strategy_config.get("temperature", 0.5),
        )
        
        await queries.create_step(
            db,
            request_id=request_id,
            step_type="step_execution",
            model_name=execution["model"],
            input_prompt=user_prompt,
            output_text=execution["text"],
            tokens_used=execution["tokens_used"],
            latency_ms=execution["latency_ms"]
        )
        
        total_tokens = decomposition["tokens_used"] + execution["tokens_used"]
        models_used = list(set([decomposition["model"], execution["model"]]))
        
        return {
            "text": execution["text"],
            "models_used": models_used,
            "total_tokens": total_tokens,
            "steps": [decomposition, execution]
        }
    
    async def _execute_image_understanding(
        self,
        db,
        request_id: str,
        user_prompt: str,
        strategy_config: Dict
    ) -> Dict[str, Any]:
        """
        Execute image understanding strategy using Gemini 3 Flash Preview.
        
        Note: For now, this handles text-only prompts about images.
        When actual image data is provided via the API, the route handler
        will call gemini.understand_image() directly.
        """
        
        # Use Gemini 3 Flash Preview for image-related text queries
        result = await self.gemini.generate(
            prompt=user_prompt,
            model=GeminiProvider.FLASH_3_0,
            temperature=strategy_config.get("temperature", 0.4),
        )
        
        await queries.create_step(
            db,
            request_id=request_id,
            step_type="image_understanding",
            model_name=result["model"],
            input_prompt=user_prompt,
            output_text=result["text"],
            tokens_used=result["tokens_used"],
            latency_ms=result["latency_ms"]
        )
        
        return {
            "text": result["text"],
            "models_used": [result["model"]],
            "total_tokens": result["tokens_used"],
            "steps": [result]
        }
    
    def _estimate_cost(self, total_tokens: int, provider: str = "gemini") -> float:
        """
        Estimate cost based on tokens and provider
        """
        if provider == strategies.PROVIDER_GROQ:
            # Groq: much cheaper, ~$0.05 per 1M tokens
            cost_per_million = 0.05
        else:
            # Gemini Flash: ~$0.10 per 1M tokens
            cost_per_million = 0.10
        
        return (total_tokens / 1_000_000) * cost_per_million


# Singleton instance
_orchestrator = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
