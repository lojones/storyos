from pydantic import BaseModel, Field, validator
from typing import Dict, Any
from datetime import datetime
import re

class ScenarioValidationError(Exception):
    pass

# Simplified schema derived from scenarios/packs/campus_freshman2.json
class ScenarioSchema(BaseModel):
    id: str = Field(..., description="Unique scenario identifier")
    name: str = Field(..., description="Human-readable scenario name")
    description: str = Field(..., description="Scenario description for users")
    version: str = Field(default="1.0.0", description="Scenario version")
    setting: str = Field(..., description="World setting details (freeform text)")
    dungeon_master_behaviour: str = Field(..., description="Freeform DM behaviour/instructions")
    initial_location: str = Field(..., description="Starting location description")
    player_name: str = Field(..., description="Default protagonist name")
    role: str = Field(..., description="Player role / short title")
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
        extra = "forbid"

def validate_scenario_dict(scenario_dict: Dict[str, Any]) -> ScenarioSchema:
    """Validate a dictionary against the simplified scenario schema."""
    try:
        return ScenarioSchema(**scenario_dict)
    except Exception as e:
        raise ScenarioValidationError(f"Scenario validation failed: {str(e)}")

def get_scenario_template() -> Dict[str, Any]:
    """Get a template for creating new simplified scenarios."""
    return {
        "id": "new_scenario",
        "name": "New Scenario",
        "description": "A new scenario for storyOS",
        "version": "1.0.0",
        "setting": "Describe the world, place, time period, and key context.",
        "dungeon_master_behaviour": (
            "As DM, set vivid scenes, role-play NPCs, enforce constraints, and end with 'What do you do?'. "
            "Keep it grounded and consistent with the setting."
        ),
        "initial_location": "Student dorm room at the start of the semester",
        "player_name": "Protagonist",
        "role": "First-year student",
        "author": "StoryOS",
        "created_at": datetime.now().isoformat(),
    }