from pydantic import BaseModel, Field, validator
from typing import Dict, List, Any, Optional
from datetime import datetime
import re

class ScenarioValidationError(Exception):
    pass

class DMBehaviorSchema(BaseModel):
    tone: str = Field(..., description="DM's narrative tone (e.g., 'warm and encouraging', 'mysterious')")
    pacing: str = Field(..., description="Scene pacing preference (e.g., 'slow_burn', 'dynamic')")
    description_style: str = Field(..., description="How scenes are described (e.g., 'detailed', 'concise')")
    interaction_style: str = Field(..., description="How NPCs interact (e.g., 'realistic', 'theatrical')")
    special_instructions: List[str] = Field(default_factory=list, description="Additional DM instructions")
    
    @validator('tone')
    def validate_tone(cls, v):
        if len(v.strip()) < 3:
            raise ValueError("Tone must be at least 3 characters")
        return v.strip()
    
    @validator('pacing')
    def validate_pacing(cls, v):
        allowed_pacing = ['slow_burn', 'moderate', 'dynamic', 'fast_paced']
        if v not in allowed_pacing:
            raise ValueError(f"Pacing must be one of: {allowed_pacing}")
        return v

class SafetyConstraintsSchema(BaseModel):
    sfw_lock: bool = Field(default=False, description="If true, forces SFW mode regardless of user settings")
    content_boundaries: List[str] = Field(default_factory=list, description="Content that should be avoided")
    trigger_warnings: List[str] = Field(default_factory=list, description="Potential triggers to warn about")
    age_rating: str = Field(default="teen", description="Minimum age rating (child|teen|adult)")
    
    @validator('age_rating')
    def validate_age_rating(cls, v):
        allowed_ratings = ['child', 'teen', 'adult']
        if v not in allowed_ratings:
            raise ValueError(f"Age rating must be one of: {allowed_ratings}")
        return v

class ScenarioMechanicsSchema(BaseModel):
    time_advancement: str = Field(default="flexible", description="How time progresses in the scenario")
    consequence_system: str = Field(default="grades_stress_relationships", description="What systems track consequences")
    choice_structure: str = Field(default="open_ended", description="How player choices are presented")
    skill_checks: bool = Field(default=False, description="Whether to use skill checks")
    inventory_management: bool = Field(default=True, description="Whether to track inventory")
    
    @validator('time_advancement')
    def validate_time_advancement(cls, v):
        allowed_time = ['real_time', 'flexible', 'scene_based', 'turn_based']
        if v not in allowed_time:
            raise ValueError(f"Time advancement must be one of: {allowed_time}")
        return v

class InitialCharacterSchema(BaseModel):
    name: str
    role: str
    current_status: str
    traits: List[str] = Field(default_factory=list)
    relationships: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)

class InitialStateSchema(BaseModel):
    current_location: str
    current_time: str
    protagonist: InitialCharacterSchema
    npcs: Dict[str, InitialCharacterSchema] = Field(default_factory=dict)
    academic_status: Dict[str, Any] = Field(default_factory=dict)
    stress_level: int = Field(default=0, ge=0, le=100)
    energy_level: int = Field(default=100, ge=0, le=100)
    mood: str = Field(default="neutral")
    
    @validator('current_time')
    def validate_time_format(cls, v):
        # Accept ISO format or simple time descriptions
        if not (re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', v) or len(v) > 5):
            raise ValueError("Time must be ISO format or descriptive string")
        return v

class ScenarioSchema(BaseModel):
    id: str = Field(..., description="Unique scenario identifier")
    name: str = Field(..., description="Human-readable scenario name")
    description: str = Field(..., description="Scenario description for users")
    version: str = Field(default="1.0.0", description="Scenario version")
    setting: Dict[str, Any] = Field(..., description="World setting details")
    dm_behavior: DMBehaviorSchema
    safety: SafetyConstraintsSchema
    mechanics: ScenarioMechanicsSchema
    initial_state: InitialStateSchema
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    author: str = Field(default="Unknown", description="Scenario author")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    @validator('id')
    def validate_id(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("ID must contain only alphanumeric characters, underscores, and hyphens")
        return v
    
    @validator('name')
    def validate_name(cls, v):
        if len(v.strip()) < 3:
            raise ValueError("Name must be at least 3 characters")
        return v.strip()
    
    @validator('description')  
    def validate_description(cls, v):
        if len(v.strip()) < 10:
            raise ValueError("Description must be at least 10 characters")
        return v.strip()
    
    class Config:
        extra = "forbid"  # Don't allow extra fields

def validate_scenario_dict(scenario_dict: Dict[str, Any]) -> ScenarioSchema:
    """Validate a dictionary against the scenario schema."""
    try:
        return ScenarioSchema(**scenario_dict)
    except Exception as e:
        raise ScenarioValidationError(f"Scenario validation failed: {str(e)}")

def get_scenario_template() -> Dict[str, Any]:
    """Get a template for creating new scenarios."""
    return {
        "id": "new_scenario",
        "name": "New Scenario",
        "description": "A new scenario for storyOS",
        "version": "1.0.0",
        "setting": {
            "world": "Modern university campus",
            "location": "McMaster University, Hamilton, ON",
            "time_period": "Present day",
            "cultural_context": "Canadian university life"
        },
        "dm_behavior": {
            "tone": "warm and encouraging",
            "pacing": "moderate",
            "description_style": "detailed",
            "interaction_style": "realistic",
            "special_instructions": []
        },
        "safety": {
            "sfw_lock": False,
            "content_boundaries": [],
            "trigger_warnings": [],
            "age_rating": "teen"
        },
        "mechanics": {
            "time_advancement": "flexible",
            "consequence_system": "grades_stress_relationships",
            "choice_structure": "open_ended",
            "skill_checks": False,
            "inventory_management": True
        },
        "initial_state": {
            "current_location": "Student dormitory",
            "current_time": "2025-09-01T09:00:00-04:00",
            "protagonist": {
                "name": "Protagonist",
                "role": "First-year student",
                "current_status": "Excited and nervous about starting university",
                "traits": ["curious", "determined"],
                "relationships": {},
                "inventory": ["laptop", "textbooks", "student ID"],
                "goals": ["Make friends", "Get good grades", "Find their place"]
            },
            "npcs": {},
            "academic_status": {
                "gpa": 0.0,
                "credits": 0,
                "semester": "Fall 2025",
                "major": "Undecided"
            },
            "stress_level": 20,
            "energy_level": 90,
            "mood": "optimistic"
        },
        "tags": ["university", "slice_of_life", "coming_of_age"],
        "author": "StoryOS",
        "created_at": datetime.now().isoformat()
    }