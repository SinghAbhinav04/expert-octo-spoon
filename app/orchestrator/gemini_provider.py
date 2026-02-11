"""
Google Gemini LLM provider wrapper

Models:
- gemini-2.5-flash: Brain system / complex reasoning
- gemini-3-flash-preview: Image understanding + fast meta-decisions
"""
from google import genai
from typing import Optional, Dict, Any
import time
import base64
from app.config import settings


class GeminiProvider:
    """Google Gemini API wrapper"""
    
    # Available Gemini models (only 2)
    FLASH_3_0 = "gemini-3-flash-preview"       # Image understanding + fast tasks
    FLASH_2_5 = "gemini-2.5-flash"             # Brain / deep reasoning
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini client"""
        self.api_key = api_key or settings.GOOGLE_API_KEY
        if not self.api_key:
            raise ValueError("Google API key not configured")
        
        self.client = genai.Client(api_key=self.api_key)
    
    async def generate(
        self,
        prompt: str,
        model: str = FLASH_2_5,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        thinking_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Generate content using Gemini models
        
        Args:
            prompt: Input prompt
            model: Gemini model to use
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens to generate
            thinking_mode: Enable thinking mode (2.5 Flash supports it)
        
        Returns:
            Dict with response text, tokens, latency, model used
        """
        start_time = time.time()
        
        # Build generation config
        config = {
            "temperature": temperature,
        }
        
        if max_tokens:
            config["max_output_tokens"] = max_tokens
        
        try:
            # Generate content
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            result = {
                "text": response.text,
                "model": model,
                "latency_ms": latency_ms,
                "tokens_used": self._estimate_tokens(prompt, response.text),
                "finish_reason": getattr(response, 'finish_reason', None),
            }
            
            return result
            
        except Exception as e:
            raise Exception(f"Gemini API error: {str(e)}")
    
    async def understand_image(
        self,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        model: str = None
    ) -> Dict[str, Any]:
        """
        Understand/analyze an image using Gemini 3 Flash Preview
        
        Args:
            prompt: Text prompt describing what to analyze
            image_data: Raw image bytes
            mime_type: Image MIME type (image/jpeg, image/png, etc.)
            model: Model to use (defaults to Flash 3.0 for vision)
        
        Returns:
            Dict with analysis text, tokens, latency
        """
        start_time = time.time()
        model = model or self.FLASH_3_0
        
        try:
            # Encode image for Gemini
            image_part = {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_data).decode("utf-8")
                }
            }
            
            response = self.client.models.generate_content(
                model=model,
                contents=[prompt, image_part]
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            return {
                "text": response.text,
                "model": model,
                "latency_ms": latency_ms,
                "tokens_used": self._estimate_tokens(prompt, response.text),
            }
            
        except Exception as e:
            raise Exception(f"Gemini Vision API error: {str(e)}")
    
    def _estimate_tokens(self, prompt: str, response: str) -> int:
        """
        Rough token estimation (Gemini uses ~4 chars per token)
        """
        total_chars = len(prompt) + len(response)
        return total_chars // 4


# Singleton instance
_gemini_provider = None


def get_gemini_provider() -> GeminiProvider:
    """Get or create Gemini provider instance"""
    global _gemini_provider
    if _gemini_provider is None:
        _gemini_provider = GeminiProvider()
    return _gemini_provider
