import json
from typing import Dict, Any
from pathlib import Path
from dm.models import Scenario, GameState, Chronicle


_PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "system_prompt.md"

def load_system_prompt() -> str:
    """Load the base system prompt from a Markdown file.

    Falls back to a minimal instruction if the file is missing.
    """
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return (
            "You are the Story Orchestrator (Dungeon Master) for storyOS. "
            "Follow the active scenario and return ONLY the requested output format."
        )


def build_scenario_context(scenario: Scenario) -> str:
    """Build the scenario context section for the prompt."""
    scenario_json = {
        "id": scenario.id,
        "name": scenario.name,
        "setting": scenario.setting,
        "dm_behavior": {
            "tone": scenario.dm_behavior.tone,
            "pacing": scenario.dm_behavior.pacing,
            "description_style": scenario.dm_behavior.description_style,
            "interaction_style": scenario.dm_behavior.interaction_style,
            "special_instructions": scenario.dm_behavior.special_instructions
        },
        "safety": {
            "sfw_lock": scenario.safety.sfw_lock,
            "content_boundaries": scenario.safety.content_boundaries,
            "trigger_warnings": scenario.safety.trigger_warnings
        },
        "mechanics": {
            "time_advancement": scenario.mechanics.time_advancement,
            "consequence_system": scenario.mechanics.consequence_system,
            "choice_structure": scenario.mechanics.choice_structure
        }
    }
    
    return json.dumps(scenario_json, indent=2)


def build_state_context(game_state: GameState, chronicle: Chronicle = None) -> str:
    """Build the current state context for the prompt."""
    
    # Core game state
    state_dict = {
        "current_location": game_state.current_location,
        "current_time": game_state.current_time,
        "protagonist": {
            "name": game_state.protagonist.name,
            "role": game_state.protagonist.role,
            "current_status": game_state.protagonist.current_status,
            "traits": game_state.protagonist.traits,
            "inventory": game_state.inventory,
            "relationships": {k: {"status": v.status, "score": v.score} 
                           for k, v in game_state.relationships.items()},
            "goals": game_state.protagonist.goals
        },
        "npcs_present": {k: {
            "name": v.name,
            "role": v.role, 
            "current_status": v.current_status,
            "recent_changes": v.recent_changes
        } for k, v in game_state.npcs.items()},
        "academic_status": game_state.academic_status,
        "stress_level": game_state.stress_level,
        "energy_level": game_state.energy_level,
        "mood": game_state.mood,
        "recent_events": game_state.recent_events[-5:]  # Last 5 events
    }
    
    # Add chronicle context if available
    if chronicle:
        # Recent timeline events
        recent_events = []
        if chronicle.timeline.phases:
            last_phase = chronicle.timeline.phases[-1]
            for event in last_phase.events[-3:]:  # Last 3 events
                recent_events.append({
                    "title": event.title,
                    "location": event.location,
                    "player_action": event.player_action,
                    "dm_outcome": event.dm_outcome,
                    "consequences": event.consequences
                })
        
        state_dict["recent_timeline"] = recent_events
        
        # Current scenario snapshot
        state_dict["current_scenario"] = {
            "location": chronicle.current.location,
            "emotional_context": chronicle.current.emotional_context,
            "npcs_present": chronicle.current.npcs_present,
            "open_choices": chronicle.current.open_choices
        }
        
        # World state
        state_dict["world_state"] = {
            "setting": chronicle.world.setting[-3:],  # Recent setting updates
            "ongoing_plots": chronicle.world.ongoing_plots,
            "global_changes": chronicle.world.global_changes[-3:]  # Recent changes
        }
    
    return json.dumps(state_dict, indent=2)


def build_full_prompt(scenario: Scenario, game_state: GameState, 
                     player_message: str, chronicle: Chronicle = None) -> tuple[str, str]:
    """Build the complete prompt for the LLM."""
    
    # System prompt (scenario-agnostic)
    system_prompt = load_system_prompt()
    
    # User prompt with scenario and state context  
    scenario_context = build_scenario_context(scenario)
    state_context = build_state_context(game_state, chronicle)
    
    user_prompt = f"""ACTIVE SCENARIO:
{scenario_context}

CURRENT STATE (read-only):
{state_context}

GLOBAL CONSTRAINTS:
- Aim for ~100–250 words unless the player asks otherwise
- Enforce scenario safety constraints and SFW locks strictly
- Advance time sensibly and reflect consequences of choices
- If images are enabled and the scene is visually distinct, set meta.image_prompt
- Return valid JSON only, no additional text or formatting

PLAYER MESSAGE: {player_message}"""
    
    return system_prompt, user_prompt


def build_narrative_only_prompt(
    scenario: Scenario,
    game_state: GameState,
    player_message: str,
    chronicle: Chronicle = None,
) -> tuple[str, str]:
    """Build prompts to get ONLY the creative narrative text (no JSON)."""
    scenario_context = build_scenario_context(scenario)
    state_context = build_state_context(game_state, chronicle)
    system_prompt = (
        "You are the Dungeon Master narrating an immersive scene. "
        "Respond with ONLY the narrative prose, 150–300 words, second person, vivid and engaging. "
        "Do NOT include JSON, tags, code fences, or additional formatting."
    )
    user_prompt = f"""ACTIVE SCENARIO:
{scenario_context}

CURRENT STATE (read-only):
{state_context}

PLAYER MESSAGE: {player_message}

Return ONLY narrative text, nothing else."""
    return system_prompt, user_prompt


def build_structured_followup_prompt(
    scenario: Scenario,
    game_state: GameState,
    player_message: str,
    narrative_text: str,
    chronicle: Chronicle = None,
) -> tuple[str, str, dict]:
    """Build a follow-up prompt to produce a DMResponse JSON using the already generated narrative."""
    scenario_context = build_scenario_context(scenario)
    state_context = build_state_context(game_state, chronicle)
    system_prompt = (
        "You are a strict JSON generator. Given scenario and the DM narrative text, "
        "produce a JSON object adhering to the exact schema. Return ONLY JSON."
    )
    schema = {
        "type": "object",
        "properties": {
            "narrative": {"type": "string", "minLength": 10},
            "suggested_actions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 4,
            },
            "state_patch": {"type": "object"},
            "scene_tags": {"type": "array", "items": {"type": "string"}},
            "meta": {"type": "object"},
        },
        "required": ["narrative", "suggested_actions", "state_patch", "scene_tags", "meta"],
        "additionalProperties": False,
    }
    user_prompt = f"""ACTIVE SCENARIO:
{scenario_context}

CURRENT STATE (read-only):
{state_context}

PLAYER MESSAGE: {player_message}

DM NARRATIVE (text you already wrote; use as 'narrative' in the JSON):
{narrative_text}

Return ONLY a JSON object matching the schema."""
    return system_prompt, user_prompt, schema


def extract_chronicle_summary(chronicle: Chronicle, max_events: int = 10) -> Dict[str, Any]:
    """Extract key information from chronicle for prompt context."""
    if not chronicle:
        return {}
    
    summary = {
        "session_duration": chronicle.updated_at,
        "total_phases": len(chronicle.timeline.phases),
        "total_events": sum(len(phase.events) for phase in chronicle.timeline.phases),
        "key_characters": list(chronicle.characters.keys()),
        "major_tags": []
    }
    
    # Get most common tags
    tag_counts = {}
    for phase in chronicle.timeline.phases:
        for event in phase.events:
            for tag in event.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    summary["major_tags"] = sorted(tag_counts.keys(), 
                                 key=lambda x: tag_counts[x], 
                                 reverse=True)[:5]
    
    return summary


def create_image_generation_prompt(narrative: str, location: str, 
                                 time_of_day: str = "day", 
                                 style: str = "realistic") -> str:
    """Create an image generation prompt from narrative context."""
    
    base_prompt = f"A {style} scene at {location}"
    
    # Add time context
    if "morning" in time_of_day.lower():
        base_prompt += ", morning light"
    elif "evening" in time_of_day.lower() or "night" in time_of_day.lower():
        base_prompt += ", evening/night atmosphere"
    else:
        base_prompt += ", daytime"
    
    # Extract visual elements from narrative
    visual_keywords = []
    narrative_lower = narrative.lower()
    
    # Architecture/settings
    if "library" in narrative_lower:
        visual_keywords.append("university library")
    elif "dorm" in narrative_lower or "room" in narrative_lower:
        visual_keywords.append("dorm room")
    elif "cafeteria" in narrative_lower or "dining" in narrative_lower:
        visual_keywords.append("dining hall")
    elif "quad" in narrative_lower or "campus" in narrative_lower:
        visual_keywords.append("campus quad")
    elif "classroom" in narrative_lower or "lecture" in narrative_lower:
        visual_keywords.append("lecture hall")
    
    # People/characters
    if "students" in narrative_lower:
        visual_keywords.append("university students")
    elif "professor" in narrative_lower:
        visual_keywords.append("professor")
    elif "roommate" in narrative_lower:
        visual_keywords.append("college roommates")
    
    # Mood/atmosphere
    if "nervous" in narrative_lower or "anxious" in narrative_lower:
        visual_keywords.append("tense atmosphere")
    elif "excited" in narrative_lower or "happy" in narrative_lower:
        visual_keywords.append("cheerful mood")
    elif "studying" in narrative_lower or "books" in narrative_lower:
        visual_keywords.append("academic setting")
    
    if visual_keywords:
        base_prompt += f", featuring {', '.join(visual_keywords[:3])}"
    
    # Add university-specific details
    base_prompt += ", McMaster University campus, Canadian university setting"
    
    # Style modifiers
    if style == "realistic":
        base_prompt += ", photorealistic, detailed, high quality"
    elif style == "artistic":
        base_prompt += ", artistic, painterly style, warm colors"
    elif style == "cinematic":
        base_prompt += ", cinematic lighting, dramatic composition"
    
    return base_prompt


def validate_dm_response_schema(response: Dict[str, Any]) -> tuple[bool, str]:
    """Validate that a DM response matches the expected schema."""
    required_fields = ["narrative", "suggested_actions", "state_patch", "scene_tags", "meta"]
    
    for field in required_fields:
        if field not in response:
            return False, f"Missing required field: {field}"
    
    # Type validation
    if not isinstance(response["narrative"], str):
        return False, "Field 'narrative' must be a string"
    
    if not isinstance(response["suggested_actions"], list):
        return False, "Field 'suggested_actions' must be a list"
    
    if not isinstance(response["state_patch"], dict):
        return False, "Field 'state_patch' must be a dictionary"
    
    if not isinstance(response["scene_tags"], list):
        return False, "Field 'scene_tags' must be a list"
    
    if not isinstance(response["meta"], dict):
        return False, "Field 'meta' must be a dictionary"
    
    # Content validation
    if len(response["narrative"].strip()) < 10:
        return False, "Narrative must be at least 10 characters"
    
    if len(response["suggested_actions"]) == 0:
        return False, "Must provide at least one suggested action"
    
    return True, "Response schema is valid"
