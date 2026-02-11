"""
AI-Powered Strategy Selection for 3-Model Orchestration

Routes tasks to the optimal model:
1. gpt-oss-120b (Groq) → Quick-shot / simple Q&A
2. gemini-2.5-flash → Brain / complex reasoning  
3. gemini-3-flash-preview → Image understanding
"""
from enum import Enum
from typing import Dict, Any
import json


class StrategyType(str, Enum):
    """Execution strategy types"""
    SINGLE_STEP = "single_step"              # Simple query → direct response
    MULTI_STEP = "multi_step"                # Complex task → sequential execution
    IMAGE_UNDERSTANDING = "image_understanding"  # Vision task → image analysis


class TaskComplexity(str, Enum):
    """Task complexity classification"""
    SIMPLE = "simple"              # Facts, definitions, simple questions
    MODERATE = "moderate"          # Explanations, summaries, creative tasks
    COMPLEX = "complex"            # Multi-step reasoning, planning, deep analysis
    IMAGE = "image"                # Image understanding tasks


# Provider constants
PROVIDER_GROQ = "groq"
PROVIDER_GEMINI = "gemini"


async def select_strategy_with_ai(user_prompt: str, gemini_provider) -> Dict[str, Any]:
    """
    🧠 AI-POWERED STRATEGY SELECTION
    
    Uses Gemini 3 Flash (fastest) to analyze the task and route to:
    - gpt-oss-120b (Groq) for simple/quick tasks
    - gemini-2.5-flash for complex reasoning
    - gemini-3-flash-preview for image understanding
    """
    from app.orchestrator.gemini_provider import GeminiProvider
    from app.orchestrator.groq_provider import GroqProvider
    
    analysis_prompt = f"""You are a task analyzer for an AI orchestration system. Analyze this user request and determine the optimal execution approach.

USER REQUEST: "{user_prompt}"

AVAILABLE MODELS:
1. openai/gpt-oss-120b (Groq - ultra fast, for simple factual queries, quick Q&A, definitions, translations)
2. gemini-2.5-flash (Google - balanced, for complex reasoning, planning, analysis, coding, deep thinking)
3. gemini-3-flash-preview (Google - vision capable, ONLY for image understanding tasks)

EXECUTION STRATEGIES:
1. single_step - Direct LLM call for straightforward tasks
2. multi_step - Sequential execution for complex multi-part tasks
3. image_understanding - For tasks involving image analysis (only if user mentions images/photos/pictures)

RULES:
- Use gpt-oss-120b for simple questions like "what is X", greetings, translations, math, definitions
- Use gemini-2.5-flash for anything requiring deep thinking, analysis, coding, planning, creative writing
- Use gemini-3-flash-preview ONLY when the task explicitly involves understanding/analyzing an image
- Default to gpt-oss-120b when unsure - it's fast and cheap

Respond ONLY with a valid JSON object (no extra text):
{{
    "complexity": "simple|moderate|complex|image",
    "strategy": "single_step|multi_step|image_understanding",
    "model": "openai/gpt-oss-120b|gemini-2.5-flash|gemini-3-flash-preview",
    "provider": "groq|gemini",
    "temperature": 0.7,
    "reasoning": "Brief explanation of your choice"
}}"""
    
    try:
        # Use fastest Gemini model for meta-decision
        result = await gemini_provider.generate(
            prompt=analysis_prompt,
            model=GeminiProvider.FLASH_3_0,
            temperature=0.2
        )
        
        # Parse JSON response
        response_text = result["text"].strip()
        
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            analysis = json.loads(json_str)
        else:
            raise ValueError("No JSON found in response")
        
        # Validate strategy and model
        strategy = StrategyType(analysis.get("strategy", "single_step"))
        model = analysis.get("model", GroqProvider.GPT_OSS_120B)
        provider = analysis.get("provider", PROVIDER_GROQ)
        
        return {
            "strategy": strategy,
            "model": model,
            "provider": provider,
            "temperature": analysis.get("temperature", 0.7),
            "description": f"AI-selected: {analysis.get('reasoning', 'No reasoning provided')}",
            "ai_analysis": analysis,
            "meta_decision_tokens": result.get("tokens_used", 0)
        }
        
    except Exception as e:
        print(f"⚠️ AI strategy selection failed: {e}. Falling back to keyword-based selection.")
        return select_strategy_fallback(user_prompt)


def select_strategy_fallback(user_prompt: str) -> Dict[str, Any]:
    """
    Fallback keyword-based strategy selection
    Used when AI-powered selection fails
    """
    from app.orchestrator.gemini_provider import GeminiProvider
    from app.orchestrator.groq_provider import GroqProvider
    
    complexity = classify_task_complexity_keywords(user_prompt)
    
    if complexity == TaskComplexity.IMAGE:
        return {
            "strategy": StrategyType.IMAGE_UNDERSTANDING,
            "model": GeminiProvider.FLASH_3_0,
            "provider": PROVIDER_GEMINI,
            "temperature": 0.4,
            "description": "Fallback: Image understanding with Gemini 3 Flash"
        }
    
    elif complexity == TaskComplexity.COMPLEX:
        return {
            "strategy": StrategyType.MULTI_STEP,
            "model": GeminiProvider.FLASH_2_5,
            "provider": PROVIDER_GEMINI,
            "temperature": 0.5,
            "description": "Fallback: Complex reasoning with Gemini 2.5 Flash"
        }
    
    elif complexity == TaskComplexity.MODERATE:
        return {
            "strategy": StrategyType.SINGLE_STEP,
            "model": GeminiProvider.FLASH_2_5,
            "provider": PROVIDER_GEMINI,
            "temperature": 0.7,
            "description": "Fallback: Moderate task with Gemini 2.5 Flash"
        }
    
    else:  # SIMPLE
        return {
            "strategy": StrategyType.SINGLE_STEP,
            "model": GroqProvider.GPT_OSS_120B,
            "provider": PROVIDER_GROQ,
            "temperature": 0.4,
            "description": "Fallback: Quick response with GPT-OSS-120B (Groq)"
        }


def classify_task_complexity_keywords(user_prompt: str) -> TaskComplexity:
    """
    Keyword-based complexity classification (fallback method)
    """
    prompt_lower = user_prompt.lower()
    word_count = len(user_prompt.split())
    
    # Image understanding indicators
    image_keywords = [
        "image", "picture", "photo", "screenshot", "diagram",
        "what is in this", "describe this image", "analyze this photo",
        "look at this", "what do you see"
    ]
    
    # Complex task indicators (→ gemini-2.5-flash)
    complex_keywords = [
        "analyze", "critique", "plan", "design", "create a system",
        "build", "implement", "step by step", "how would you",
        "develop", "architecture", "break down", "organize",
        "pros and cons", "trade-offs", "compare and contrast",
        "write code", "debug", "refactor", "explain the reasoning",
        "philosophy", "ethical", "strategy", "think through"
    ]
    
    # Moderate task indicators (→ gemini-2.5-flash)
    moderate_keywords = [
        "explain", "describe", "summarize", "write", "generate",
        "list", "compare", "what are", "how to", "create"
    ]
    
    if any(keyword in prompt_lower for keyword in image_keywords):
        return TaskComplexity.IMAGE
    
    if any(keyword in prompt_lower for keyword in complex_keywords) or word_count > 50:
        return TaskComplexity.COMPLEX
    
    if any(keyword in prompt_lower for keyword in moderate_keywords) or word_count > 20:
        return TaskComplexity.MODERATE
    
    return TaskComplexity.SIMPLE


# Model selection helpers

def get_quickshot_model() -> str:
    """Get fastest model for quick Q&A (Groq)"""
    from app.orchestrator.groq_provider import GroqProvider
    return GroqProvider.GPT_OSS_120B


def get_brain_model() -> str:
    """Get brain model for complex reasoning (Gemini 2.5 Flash)"""
    from app.orchestrator.gemini_provider import GeminiProvider
    return GeminiProvider.FLASH_2_5


def get_vision_model() -> str:
    """Get vision model for image understanding (Gemini 3 Flash Preview)"""
    from app.orchestrator.gemini_provider import GeminiProvider
    return GeminiProvider.FLASH_3_0


def get_fastest_model() -> str:
    """Get fastest model for meta-decisions"""
    from app.orchestrator.gemini_provider import GeminiProvider
    return GeminiProvider.FLASH_3_0
