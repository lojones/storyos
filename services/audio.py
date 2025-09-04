import openai
from typing import Optional, Dict, Any
import logging
import os
import base64
from pathlib import Path
import io

logger = logging.getLogger(__name__)


class AudioService:
    """Optional text-to-speech service for narrative audio."""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 default_voice: str = "alloy",
                 default_model: str = "tts-1",
                 save_audio: bool = True,
                 audio_dir: str = "data/audio"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.default_voice = default_voice
        self.default_model = default_model
        self.save_audio = save_audio
        self.audio_dir = Path(audio_dir)
        
        if self.save_audio:
            self.audio_dir.mkdir(parents=True, exist_ok=True)
        
        if self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("No OpenAI API key provided - audio generation disabled")
    
    def synthesize_narrative(self, 
                           text: str,
                           voice: Optional[str] = None,
                           model: Optional[str] = None,
                           speed: float = 1.0) -> Optional[Dict[str, Any]]:
        """Convert narrative text to speech."""
        
        if not self.client:
            logger.warning("Audio synthesis attempted but no API key configured")
            return None
        
        voice = voice or self.default_voice
        model = model or self.default_model
        
        try:
            # Clean text for TTS
            cleaned_text = self._clean_text_for_tts(text)
            
            if len(cleaned_text) > 4096:  # OpenAI TTS limit
                cleaned_text = cleaned_text[:4090] + "..."
                logger.warning("Text truncated for TTS due to length limit")
            
            response = self.client.audio.speech.create(
                model=model,
                voice=voice,
                input=cleaned_text,
                speed=speed
            )
            
            # Get audio data
            audio_data = response.content
            
            result = {
                "audio_data": audio_data,
                "text": cleaned_text,
                "voice": voice,
                "model": model,
                "speed": speed,
                "format": "mp3"
            }
            
            # Optionally save the audio
            if self.save_audio:
                try:
                    saved_path = self._save_audio_data(audio_data, cleaned_text)
                    result["saved_path"] = saved_path
                except Exception as e:
                    logger.warning(f"Failed to save audio: {e}")
            
            logger.info(f"Generated TTS audio: {len(cleaned_text)} characters")
            return result
            
        except Exception as e:
            logger.error(f"Audio synthesis failed: {e}")
            return None
    
    def _clean_text_for_tts(self, text: str) -> str:
        """Clean text for better TTS pronunciation."""
        
        # Remove markdown formatting
        cleaned = text.replace("**", "").replace("*", "")
        
        # Remove common chat formatting
        cleaned = cleaned.replace("```", "")
        
        # Handle common abbreviations
        replacements = {
            "Dr.": "Doctor",
            "Prof.": "Professor", 
            "etc.": "et cetera",
            "e.g.": "for example",
            "i.e.": "that is",
            "vs.": "versus",
            "Mr.": "Mister",
            "Ms.": "Miss",
            "Mrs.": "Missus"
        }
        
        for abbrev, replacement in replacements.items():
            cleaned = cleaned.replace(abbrev, replacement)
        
        # Remove excessive whitespace
        cleaned = " ".join(cleaned.split())
        
        # Ensure proper sentence endings
        if cleaned and not cleaned.endswith(('.', '!', '?')):
            cleaned += "."
        
        return cleaned
    
    def _save_audio_data(self, audio_data: bytes, text: str) -> str:
        """Save audio data to file."""
        from datetime import datetime
        
        # Create filename from timestamp and text preview
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        text_preview = "".join(c for c in text[:30] if c.isalnum() or c in " -_").strip()
        text_preview = text_preview.replace(" ", "_")
        filename = f"{timestamp}_{text_preview}.mp3"
        
        filepath = self.audio_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        return str(filepath)
    
    def create_character_voice_sample(self,
                                    character_name: str,
                                    sample_dialogue: str,
                                    voice: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Generate a voice sample for a character."""
        
        if not self.client:
            return None
        
        # Format dialogue for character
        formatted_text = f"Hello, I'm {character_name}. {sample_dialogue}"
        
        return self.synthesize_narrative(
            text=formatted_text,
            voice=voice or self._suggest_voice_for_character(character_name),
            speed=1.0
        )
    
    def _suggest_voice_for_character(self, character_name: str) -> str:
        """Suggest an appropriate voice for a character."""
        # Simple heuristic based on character name/role
        # In a real implementation, this could be more sophisticated
        
        voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        
        # Use name hash to consistently assign voices
        name_hash = hash(character_name.lower()) % len(voices)
        return voices[name_hash]
    
    def batch_synthesize(self, 
                        text_segments: list[str],
                        voice: Optional[str] = None) -> list[Optional[Dict[str, Any]]]:
        """Synthesize multiple text segments in batch."""
        
        results = []
        for segment in text_segments:
            result = self.synthesize_narrative(segment, voice=voice)
            results.append(result)
            
            # Add small delay to respect rate limits
            import time
            time.sleep(0.1)
        
        return results
    
    def is_available(self) -> bool:
        """Check if audio synthesis is available."""
        return self.client is not None
    
    def get_available_voices(self) -> list[str]:
        """Get list of available voices."""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def get_supported_models(self) -> list[str]:
        """Get list of supported TTS models."""
        return ["tts-1", "tts-1-hd"]
    
    def estimate_cost(self, text: str, model: str = "tts-1") -> float:
        """Estimate the cost for synthesizing text."""
        # OpenAI TTS pricing (as of 2024)
        # tts-1: $0.015 per 1K characters
        # tts-1-hd: $0.030 per 1K characters
        
        char_count = len(text)
        
        if model == "tts-1-hd":
            cost_per_1k = 0.030
        else:  # tts-1
            cost_per_1k = 0.015
        
        return (char_count / 1000) * cost_per_1k