import copy
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import logging

from .models import GameState, DMResponse, Scenario, Chronicle, Event, CurrentScenario
from .prompting import build_full_prompt, validate_dm_response_schema
from memory.chronicle import ChronicleManager
from services.llm import LLMService

logger = logging.getLogger(__name__)


class GameEngine:
    def __init__(self, llm_service: LLMService, chronicle_manager: ChronicleManager):
        self.llm = llm_service
        self.chronicle_manager = chronicle_manager
    
    def process_turn(self, 
                    scenario: Scenario,
                    game_state: GameState, 
                    chronicle: Chronicle,
                    player_message: str,
                    model: Optional[str] = None) -> Tuple[DMResponse, GameState, Chronicle]:
        """Process a complete turn: player input -> LLM -> state update -> chronicle update."""
        
        logger.info(f"Processing turn for scenario {scenario.id}")
        
        try:
            # Build prompts
            system_prompt, user_prompt = build_full_prompt(scenario, game_state, player_message, chronicle)
            
            # Get LLM response
            raw_response = self.llm.generate_dm_response(
                system_prompt=system_prompt,
                scenario_context="",  # Already included in user_prompt
                game_state="",       # Already included in user_prompt  
                player_message=user_prompt,
                model=model,
                temperature=0.8
            )
            
            # Validate response schema
            is_valid, error_msg = validate_dm_response_schema(raw_response)
            if not is_valid:
                logger.error(f"Invalid DM response schema: {error_msg}")
                raw_response = self._create_fallback_response(error_msg)
            
            dm_response = DMResponse(**raw_response)
            
            # Update game state
            updated_game_state = self._apply_state_patch(game_state, dm_response.state_patch, scenario)
            
            # Update chronicle with new event
            updated_chronicle = self._update_chronicle(
                chronicle, 
                player_message, 
                dm_response, 
                updated_game_state,
                scenario
            )
            
            logger.info("Turn processed successfully")
            return dm_response, updated_game_state, updated_chronicle
            
        except Exception as e:
            logger.error(f"Error processing turn: {e}")
            fallback_response = self._create_error_response(str(e))
            return DMResponse(**fallback_response), game_state, chronicle
    
    def _apply_state_patch(self, 
                          current_state: GameState, 
                          state_patch: Dict[str, Any],
                          scenario: Scenario) -> GameState:
        """Apply state changes from DM response to game state."""
        
        # Create a deep copy to avoid modifying original
        new_state_dict = current_state.dict()
        
        # Apply patches with validation
        for key, value in state_patch.items():
            if key in new_state_dict:
                if isinstance(new_state_dict[key], dict) and isinstance(value, dict):
                    # Merge dictionaries
                    new_state_dict[key].update(value)
                else:
                    # Direct replacement
                    new_state_dict[key] = value
            else:
                # Add new field
                new_state_dict[key] = value
        
        # Apply scenario-specific constraints and validation
        new_state_dict = self._apply_scenario_constraints(new_state_dict, scenario)
        
        # Validate state bounds
        new_state_dict = self._validate_state_bounds(new_state_dict)
        
        return GameState(**new_state_dict)
    
    def _apply_scenario_constraints(self, state_dict: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        """Apply scenario-specific constraints to state updates."""
        
        # Time advancement constraints
        if scenario.mechanics.time_advancement == "real_time":
            # Time advances in real-time
            state_dict["current_time"] = datetime.now().isoformat()
        elif scenario.mechanics.time_advancement == "scene_based":
            # Only advance time when location or major action changes
            pass  # Keep current time unless explicitly changed
        
        # Consequence system constraints
        if scenario.mechanics.consequence_system == "grades_stress_relationships":
            # Ensure these systems are tracked
            if "academic_status" not in state_dict:
                state_dict["academic_status"] = {"gpa": 0.0, "credits": 0}
            
            # Auto-calculate stress based on recent events
            if "stress_level" in state_dict:
                state_dict["stress_level"] = max(0, min(100, state_dict["stress_level"]))
        
        return state_dict
    
    def _validate_state_bounds(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that state values are within acceptable bounds."""
        
        # Ensure numeric values are within bounds
        if "stress_level" in state_dict:
            state_dict["stress_level"] = max(0, min(100, state_dict["stress_level"]))
        
        if "energy_level" in state_dict:
            state_dict["energy_level"] = max(0, min(100, state_dict["energy_level"]))
        
        # Validate academic status
        if "academic_status" in state_dict and isinstance(state_dict["academic_status"], dict):
            if "gpa" in state_dict["academic_status"]:
                state_dict["academic_status"]["gpa"] = max(0.0, min(4.0, state_dict["academic_status"]["gpa"]))
        
        # Ensure required fields exist
        required_fields = ["current_location", "current_time", "mood"]
        for field in required_fields:
            if field not in state_dict:
                state_dict[field] = self._get_default_state_value(field)
        
        return state_dict
    
    def _get_default_state_value(self, field: str) -> Any:
        """Get default value for missing state fields."""
        defaults = {
            "current_location": "Unknown location",
            "current_time": datetime.now().isoformat(),
            "mood": "neutral",
            "stress_level": 50,
            "energy_level": 100
        }
        return defaults.get(field, None)
    
    def _update_chronicle(self, 
                         chronicle: Chronicle,
                         player_message: str,
                         dm_response: DMResponse, 
                         game_state: GameState,
                         scenario: Scenario) -> Chronicle:
        """Update the chronicle with the new turn."""
        
        # Create event data
        event_data = {
            "title": self._generate_event_title(player_message, dm_response.narrative),
            "timestamp": datetime.now().isoformat(),
            "time_advance": self._calculate_time_advance(chronicle.current.time, game_state.current_time),
            "location": game_state.current_location,
            "participants": self._extract_participants(dm_response.narrative, game_state),
            "player_action": player_message.strip(),
            "dm_outcome": dm_response.narrative,
            "consequences": self._extract_consequences(dm_response.state_patch),
            "tags": dm_response.scene_tags,
            "notes": "Generated by DM engine"
        }
        
        # Add event to chronicle
        updated_chronicle = self.chronicle_manager.persist_event(chronicle, event_data)
        
        # Update character information
        updated_chronicle = self._update_chronicle_characters(updated_chronicle, game_state)
        
        # Update world state if needed
        world_updates = self._extract_world_updates(dm_response.state_patch, dm_response.scene_tags)
        if world_updates:
            updated_chronicle = self.chronicle_manager.persist_world_update(updated_chronicle, world_updates)
        
        # Update current scenario snapshot
        current_data = {
            "location": game_state.current_location,
            "time": game_state.current_time,
            "emotional_context": self._extract_emotional_context(dm_response.narrative, game_state),
            "npcs_present": list(game_state.npcs.keys()),
            "open_choices": dm_response.suggested_actions,
            "last_exchange_ref": f"turn_{datetime.now().timestamp()}",
            "prompt": self._extract_prompt_from_narrative(dm_response.narrative)
        }
        
        updated_chronicle = self.chronicle_manager.snapshot_current(updated_chronicle, current_data)
        
        return updated_chronicle
    
    def _generate_event_title(self, player_message: str, dm_narrative: str) -> str:
        """Generate a concise title for the event."""
        # Simple heuristic - take first few words of player action
        words = player_message.split()[:4]
        title = " ".join(words)
        
        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]
        
        return title or "Untitled event"
    
    def _calculate_time_advance(self, old_time: str, new_time: str) -> Optional[str]:
        """Calculate time advancement between turns."""
        try:
            old_dt = datetime.fromisoformat(old_time.replace('Z', '+00:00'))
            new_dt = datetime.fromisoformat(new_time.replace('Z', '+00:00'))
            
            delta = new_dt - old_dt
            if delta.total_seconds() > 0:
                return f"PT{int(delta.total_seconds())}S"  # ISO 8601 duration
            
        except Exception:
            pass
        
        return None
    
    def _extract_participants(self, narrative: str, game_state: GameState) -> List[str]:
        """Extract participants from the narrative and game state."""
        participants = ["Player"]
        
        # Add NPCs that are present
        participants.extend(game_state.npcs.keys())
        
        # Try to extract additional participants from narrative
        narrative_lower = narrative.lower()
        for npc_name in game_state.npcs.keys():
            if npc_name.lower() in narrative_lower and npc_name not in participants:
                participants.append(npc_name)
        
        return participants
    
    def _extract_consequences(self, state_patch: Dict[str, Any]) -> List[str]:
        """Extract meaningful consequences from state changes."""
        consequences = []
        
        if "stress_level" in state_patch:
            old_stress = state_patch.get("old_stress_level", 50)  # Default
            new_stress = state_patch["stress_level"]
            if new_stress > old_stress + 10:
                consequences.append("Stress level increased significantly")
            elif new_stress < old_stress - 10:
                consequences.append("Stress level decreased")
        
        if "relationships" in state_patch:
            consequences.append("Relationship status changed")
        
        if "academic_status" in state_patch:
            consequences.append("Academic progress updated")
        
        if "current_location" in state_patch:
            consequences.append(f"Moved to {state_patch['current_location']}")
        
        return consequences or ["Turn completed"]
    
    def _update_chronicle_characters(self, chronicle: Chronicle, game_state: GameState) -> Chronicle:
        """Update character information in the chronicle."""
        
        # Update protagonist
        protagonist_data = {
            "name": game_state.protagonist.name,
            "role": game_state.protagonist.role,
            "current_status": game_state.protagonist.current_status,
            "traits": game_state.protagonist.traits,
            "relationships": {k: {"status": v.status, "score": v.score} 
                           for k, v in game_state.relationships.items()},
            "inventory": game_state.inventory,
            "goals": game_state.protagonist.goals,
            "recent_changes": [f"Updated at {datetime.now().strftime('%H:%M')}"]
        }
        
        chronicle = self.chronicle_manager.persist_character_update(chronicle, "Protagonist", protagonist_data)
        
        # Update NPCs
        for npc_name, npc_data in game_state.npcs.items():
            npc_dict = {
                "name": npc_data.name,
                "role": npc_data.role,
                "current_status": npc_data.current_status,
                "traits": npc_data.traits,
                "relationships": {k: {"status": v.status, "score": v.score} 
                               for k, v in npc_data.relationships.items()},
                "inventory": npc_data.inventory,
                "goals": npc_data.goals,
                "recent_changes": npc_data.recent_changes
            }
            chronicle = self.chronicle_manager.persist_character_update(chronicle, npc_name, npc_dict)
        
        return chronicle
    
    def _extract_world_updates(self, state_patch: Dict[str, Any], scene_tags: List[str]) -> Dict[str, Any]:
        """Extract world-level updates from state changes."""
        world_updates = {}
        
        # Check for global changes
        if "current_time" in state_patch:
            world_updates.setdefault("global_changes", []).append(
                f"Time advanced to {state_patch['current_time']}"
            )
        
        # Add ongoing plots based on scene tags
        if "romance" in scene_tags:
            world_updates.setdefault("ongoing_plots", []).append("Romance storyline developing")
        elif "academics" in scene_tags:
            world_updates.setdefault("ongoing_plots", []).append("Academic challenges ongoing")
        
        return world_updates
    
    def _extract_emotional_context(self, narrative: str, game_state: GameState) -> str:
        """Extract emotional context from narrative and state."""
        mood = game_state.mood
        stress = game_state.stress_level
        
        context_parts = []
        
        # Add mood
        context_parts.append(f"Mood: {mood}")
        
        # Add stress context
        if stress > 80:
            context_parts.append("high stress")
        elif stress > 60:
            context_parts.append("moderate stress") 
        elif stress < 30:
            context_parts.append("low stress")
        
        # Extract emotional keywords from narrative
        narrative_lower = narrative.lower()
        emotions = ["excited", "nervous", "happy", "worried", "confident", "confused", "determined"]
        
        for emotion in emotions:
            if emotion in narrative_lower:
                context_parts.append(f"feeling {emotion}")
                break
        
        return "; ".join(context_parts)
    
    def _extract_prompt_from_narrative(self, narrative: str) -> str:
        """Extract the final prompt/question from the narrative."""
        # Look for common prompt patterns
        sentences = narrative.split('.')
        last_sentence = sentences[-1].strip()
        
        if last_sentence and ('?' in last_sentence or 
                             last_sentence.lower().startswith(('what', 'how', 'where', 'why', 'when')) or
                             'do you' in last_sentence.lower()):
            return last_sentence
        
        return "What do you do next?"
    
    def _create_fallback_response(self, error_msg: str) -> Dict[str, Any]:
        """Create a fallback response when the LLM response is invalid."""
        return {
            "narrative": f"The story continues, though something feels off... [System: {error_msg}]",
            "suggested_actions": ["Continue forward", "Look around", "Try something different"],
            "state_patch": {},
            "scene_tags": ["system_recovery"],
            "meta": {"validation_error": error_msg}
        }
    
    def _create_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Create an error response when turn processing fails."""
        return {
            "narrative": f"*The narrative pauses unexpectedly...* [Error: {error_msg}]",
            "suggested_actions": ["Wait a moment", "Try again"],
            "state_patch": {},
            "scene_tags": ["system_error"],
            "meta": {"processing_error": error_msg}
        }
    
    def initialize_new_game(self, scenario: Scenario) -> Tuple[GameState, Chronicle]:
        """Initialize a new game with the given scenario."""
        
        # Create initial game state from scenario
        game_state = copy.deepcopy(scenario.initial_state)
        
        # Create initial current scenario for chronicle
        initial_current = CurrentScenario(
            location=game_state.current_location,
            time=game_state.current_time,
            emotional_context=f"Starting {scenario.name}",
            npcs_present=list(game_state.npcs.keys()),
            open_choices=["Look around", "Introduce yourself", "Check the time"],
            prompt="What would you like to do first?"
        )
        
        # Create chronicle
        from memory.chronicle import Policy
        policy = Policy(
            sfw_mode=scenario.safety.sfw_lock,
            mature_handling="redact" if scenario.safety.sfw_lock else "reference",
            age_verified=False
        )
        
        chronicle = self.chronicle_manager.create_chronicle(scenario.id, initial_current, policy)
        
        # Add initial world state
        world_updates = {
            "setting": [f"Location: {game_state.current_location}"] + 
                      ([scenario.setting.get("world", "Unknown world")] if isinstance(scenario.setting, dict) else []),
            "rules_mechanics": [
                f"Time advancement: {scenario.mechanics.time_advancement}",
                f"Consequence system: {scenario.mechanics.consequence_system}"
            ],
            "ongoing_plots": ["Story beginning"],
            "global_changes": [f"Game started at {datetime.now().isoformat()}"]
        }
        
        chronicle = self.chronicle_manager.persist_world_update(chronicle, world_updates)
        
        logger.info(f"Initialized new game for scenario {scenario.id}")
        return game_state, chronicle