import openai
from typing import Optional, Dict, Any
import logging
import os
import base64
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageService:
    """Optional image generation service for visual scene enhancement."""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 default_model: str = "dall-e-3",
                 save_images: bool = True,
                 image_dir: str = "data/images"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.default_model = default_model
        self.save_images = save_images
        self.image_dir = Path(image_dir)
        
        if self.save_images:
            self.image_dir.mkdir(parents=True, exist_ok=True)
        
        if self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("No OpenAI API key provided - image generation disabled")
    
    def generate_scene_image(self, 
                           prompt: str,
                           size: str = "1024x1024",
                           quality: str = "standard",
                           style: str = "vivid") -> Optional[Dict[str, Any]]:
        """Generate an image for a scene description."""
        
        if not self.client:
            logger.warning("Image generation attempted but no API key configured")
            return None
        
        try:
            # Clean and enhance the prompt for DALL-E
            enhanced_prompt = self._enhance_prompt(prompt)
            
            response = self.client.images.generate(
                model=self.default_model,
                prompt=enhanced_prompt,
                size=size,
                quality=quality,
                style=style,
                n=1
            )
            
            image_url = response.data[0].url
            
            result = {
                "url": image_url,
                "prompt": enhanced_prompt,
                "size": size,
                "quality": quality,
                "style": style
            }
            
            # Optionally save the image
            if self.save_images:
                try:
                    saved_path = self._save_image_from_url(image_url, enhanced_prompt)
                    result["saved_path"] = saved_path
                except Exception as e:
                    logger.warning(f"Failed to save image: {e}")
            
            logger.info(f"Generated scene image: {enhanced_prompt[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return None
    
    def _enhance_prompt(self, prompt: str) -> str:
        """Enhance the prompt for better DALL-E results."""
        
        # University life specific enhancements
        university_terms = {
            "campus": "university campus with brick buildings and quad areas",
            "library": "modern university library with study areas and tall windows",
            "dorm": "university dormitory room with twin beds and desk areas", 
            "classroom": "university lecture hall with tiered seating and projector",
            "cafeteria": "university dining hall with long tables and serving areas"
        }
        
        enhanced = prompt.lower()
        
        # Replace generic terms with more specific descriptions
        for term, replacement in university_terms.items():
            if term in enhanced:
                enhanced = enhanced.replace(term, replacement)
        
        # Add style guidance
        style_additions = [
            "photorealistic",
            "warm lighting",
            "detailed",
            "high quality",
            "modern university setting"
        ]
        
        # Combine original prompt with enhancements
        if not any(style in enhanced for style in ["photorealistic", "realistic", "artistic"]):
            enhanced += ", " + ", ".join(style_additions)
        
        # Ensure appropriate content
        enhanced += ", appropriate for all ages, educational setting"
        
        return enhanced[:1000]  # DALL-E prompt limit
    
    def _save_image_from_url(self, image_url: str, prompt: str) -> str:
        """Save image from URL to local storage."""
        import requests
        from datetime import datetime
        
        response = requests.get(image_url)
        response.raise_for_status()
        
        # Create filename from timestamp and prompt
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in " -_").strip()
        safe_prompt = safe_prompt.replace(" ", "_")
        filename = f"{timestamp}_{safe_prompt}.png"
        
        filepath = self.image_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        return str(filepath)
    
    def create_character_portrait(self,
                                character_name: str,
                                character_description: str,
                                style: str = "portrait") -> Optional[Dict[str, Any]]:
        """Generate a character portrait image."""
        
        if not self.client:
            return None
        
        # Build character-focused prompt
        prompt = f"Portrait of {character_name}, {character_description}"
        prompt += ", university student, realistic portrait style, friendly expression"
        prompt += ", appropriate for all ages, professional headshot style"
        
        return self.generate_scene_image(
            prompt=prompt,
            size="1024x1024", 
            quality="standard",
            style="natural"
        )
    
    def is_available(self) -> bool:
        """Check if image generation is available."""
        return self.client is not None
    
    def get_supported_sizes(self) -> list[str]:
        """Get list of supported image sizes."""
        return ["1024x1024", "1792x1024", "1024x1792"]
    
    def get_supported_qualities(self) -> list[str]:
        """Get list of supported quality settings."""
        return ["standard", "hd"]
    
    def get_supported_styles(self) -> list[str]:
        """Get list of supported style settings."""
        return ["vivid", "natural"]