"""
Groq LLM provider wrapper (OpenAI-compatible API)

Uses gpt-oss-120b for quick-shot / simple Q&A tasks.
"""
from openai import OpenAI
from typing import Optional, Dict, Any
import time
from app.config import settings


class GroqProvider:
    """Groq API wrapper using OpenAI-compatible client"""
    
    # Available models
    GPT_OSS_120B = "openai/gpt-oss-120b"
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Groq client via OpenAI SDK"""
        self.api_key = api_key or settings.GROQ_API_KEY
        if not self.api_key:
            raise ValueError("Groq API key not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    
    async def generate(
        self,
        prompt: str,
        model: str = GPT_OSS_120B,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate content using Groq models
        
        Args:
            prompt: Input prompt
            model: Model to use (default: gpt-oss-120b)
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate
        
        Returns:
            Dict with response text, tokens, latency, model used
        """
        start_time = time.time()
        
        try:
            # Use the responses API as shown in the docs
            response = self.client.responses.create(
                input=prompt,
                model=model,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            response_text = response.output_text
            
            return {
                "text": response_text,
                "model": model,
                "latency_ms": latency_ms,
                "tokens_used": self._estimate_tokens(prompt, response_text),
            }
            
        except Exception as e:
            raise Exception(f"Groq API error: {str(e)}")
    
    def _estimate_tokens(self, prompt: str, response: str) -> int:
        """
        Rough token estimation (~4 chars per token)
        """
        total_chars = len(prompt) + len(response)
        return total_chars // 4


# Singleton instance
_groq_provider = None


def get_groq_provider() -> GroqProvider:
    """Get or create Groq provider instance"""
    global _groq_provider
    if _groq_provider is None:
        _groq_provider = GroqProvider()
    return _groq_provider
