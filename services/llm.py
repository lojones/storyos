import openai
from typing import Dict, Any, Optional, List
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, 
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 default_model: str = "grok-beta"):
        # Support both XAI and OpenAI API keys
        self.api_key = api_key or os.getenv("XAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("XAI_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.x.ai/v1")
        self.default_model = default_model or os.getenv("DEFAULT_MODEL", "grok-beta")
        
        if not self.api_key:
            raise ValueError("API key is required (set XAI_API_KEY or OPENAI_API_KEY)")
        
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_dm_response(self, 
                           system_prompt: str,
                           scenario_context: str, 
                           game_state: str,
                           player_message: str,
                           model: Optional[str] = None,
                           temperature: float = 0.8,
                           max_tokens: int = 1000) -> Dict[str, Any]:
        """Generate a DM response using the LLM."""
        
        model = model or self.default_model
        
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user", 
                "content": f"ACTIVE SCENARIO:\n{scenario_context}\n\nCURRENT STATE:\n{game_state}\n\nPLAYER MESSAGE: {player_message}"
            }
        ]
        
        try:
            # Grok may not support response_format, so we'll handle JSON parsing manually
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response (handle cases where model includes extra text)
                json_content = self._extract_json_from_response(content)
                parsed_response = json.loads(json_content)
                return self._validate_dm_response(parsed_response)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw content: {content}")
                return self._create_fallback_response(content)
                
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return self._create_error_response(str(e))
    
    def _validate_dm_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean up the DM response."""
        required_fields = ["narrative", "suggested_actions", "state_patch", "scene_tags", "meta"]
        
        validated = {}
        for field in required_fields:
            if field not in response:
                logger.warning(f"Missing required field '{field}' in DM response")
                validated[field] = self._get_default_field_value(field)
            else:
                validated[field] = response[field]
        
        # Ensure proper types
        if not isinstance(validated["suggested_actions"], list):
            validated["suggested_actions"] = []
        
        if not isinstance(validated["state_patch"], dict):
            validated["state_patch"] = {}
        
        if not isinstance(validated["scene_tags"], list):
            validated["scene_tags"] = []
        
        if not isinstance(validated["meta"], dict):
            validated["meta"] = {}
        
        return validated
    
    def _extract_json_from_response(self, content: str) -> str:
        """Extract JSON from model response that might contain extra text."""
        import re
        
        # Try to find JSON block in the response
        json_pattern = r'\{.*\}'
        match = re.search(json_pattern, content, re.DOTALL)
        
        if match:
            return match.group(0)
        
        # If no JSON found, raise error
        raise ValueError(f"No valid JSON found in response: {content[:200]}...")
    
    def _get_default_field_value(self, field: str) -> Any:
        """Get default value for missing response fields."""
        defaults = {
            "narrative": "The story continues...",
            "suggested_actions": ["Continue exploring", "Ask a question", "Take a different approach"],
            "state_patch": {},
            "scene_tags": ["general"],
            "meta": {}
        }
        return defaults.get(field, None)
    
    def _create_fallback_response(self, raw_content: str) -> Dict[str, Any]:
        """Create a fallback response when JSON parsing fails."""
        return {
            "narrative": raw_content[:500] + "..." if len(raw_content) > 500 else raw_content,
            "suggested_actions": ["Continue the conversation", "Try a different approach"],
            "state_patch": {},
            "scene_tags": ["error_recovery"],
            "meta": {"parsing_error": True}
        }
    
    def _create_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Create an error response when the LLM call fails."""
        return {
            "narrative": f"*The story pauses momentarily...* (System error: {error_msg})",
            "suggested_actions": ["Try again", "Check connection"],
            "state_patch": {},
            "scene_tags": ["system_error"],
            "meta": {"error": error_msg}
        }
    
    async def generate_dm_response_async(self, 
                                       system_prompt: str,
                                       scenario_context: str,
                                       game_state: str, 
                                       player_message: str,
                                       model: Optional[str] = None,
                                       temperature: float = 0.8,
                                       max_tokens: int = 1000) -> Dict[str, Any]:
        """Async version of DM response generation."""
        # For now, just wrap the sync version
        # In a real implementation, you'd use the async OpenAI client
        return self.generate_dm_response(
            system_prompt, scenario_context, game_state, player_message,
            model, temperature, max_tokens
        )
    
    def stream_dm_response(self,
                          system_prompt: str,
                          scenario_context: str,
                          game_state: str,
                          player_message: str,
                          model: Optional[str] = None,
                          temperature: float = 0.8,
                          max_tokens: int = 1000):
        """Stream a DM response for real-time display."""
        
        model = model or self.default_model
        
        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"ACTIVE SCENARIO:\n{scenario_context}\n\nCURRENT STATE:\n{game_state}\n\nPLAYER MESSAGE: {player_message}"
            }
        ]
        
        try:
            response_stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            accumulated_content = ""
            for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    content_chunk = chunk.choices[0].delta.content
                    accumulated_content += content_chunk
                    yield content_chunk
            
            # Try to parse the complete response
            try:
                json_content = self._extract_json_from_response(accumulated_content)
                complete_response = json.loads(json_content)
                return self._validate_dm_response(complete_response)
            except (json.JSONDecodeError, ValueError):
                return self._create_fallback_response(accumulated_content)
                
        except Exception as e:
            logger.error(f"Streaming LLM API call failed: {e}")
            yield json.dumps(self._create_error_response(str(e)))
    
    def generate_image_prompt(self, scene_description: str, style: str = "realistic") -> str:
        """Generate an image prompt from scene description."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert at creating detailed image generation prompts. Convert scene descriptions into vivid, detailed prompts suitable for AI image generation. Focus on visual elements, lighting, mood, and composition."
                },
                {
                    "role": "user",
                    "content": f"Create a detailed image generation prompt for this scene (style: {style}):\n\n{scene_description}"
                }
            ]
            
            response = self.client.chat.completions.create(
                model=self.default_model,  # Use configured model
                messages=messages,
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate image prompt: {e}")
            return f"University campus scene: {scene_description}"
    
    def summarize_for_memory(self, events: List[str], max_length: int = 200) -> str:
        """Summarize a list of events for memory compression."""
        if not events:
            return ""
        
        events_text = "\n".join(events)
        if len(events_text) <= max_length:
            return events_text
        
        try:
            messages = [
                {
                    "role": "system", 
                    "content": f"Summarize these story events in {max_length} characters or less. Preserve key plot points, character development, and consequences."
                },
                {
                    "role": "user",
                    "content": events_text
                }
            ]
            
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=0.3,
                max_tokens=max_length // 4  # Rough token estimate
            )
            
            summary = response.choices[0].message.content.strip()
            return summary[:max_length] if len(summary) > max_length else summary
            
        except Exception as e:
            logger.error(f"Failed to summarize events: {e}")
            # Fallback: just truncate
            return events_text[:max_length-3] + "..."
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the LLM connection and return status."""
        try:
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=[{"role": "user", "content": "Test connection. Respond with 'OK'."}],
                max_tokens=10,
                temperature=0
            )
            
            if response.choices[0].message.content.strip() == "OK":
                return True, "Connection successful"
            else:
                return True, f"Connection working, got: {response.choices[0].message.content}"
            
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        try:
            models = self.client.models.list()
            return [model.id for model in models.data]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return [self.default_model]  # Fallback to default