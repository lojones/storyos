from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
import uuid

class Relationship(BaseModel):
    status: str = "neutral"
    score: int = 0

class Character(BaseModel):
    name: str
    role: str
    current_status: str
    traits: List[str] = Field(default_factory=list)
    relationships: Dict[str, Relationship] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    recent_changes: List[str] = Field(default_factory=list)

class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    time_advance: Optional[str] = None
    location: str
    participants: List[str]
    player_action: str
    dm_outcome: str
    consequences: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

class Phase(BaseModel):
    phase_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    events: List[Event] = Field(default_factory=list)

class Timeline(BaseModel):
    phases: List[Phase] = Field(default_factory=list)

class World(BaseModel):
    setting: List[str] = Field(default_factory=list)
    rules_mechanics: List[str] = Field(default_factory=list)
    ongoing_plots: List[str] = Field(default_factory=list)
    global_changes: List[str] = Field(default_factory=list)

class CurrentScenario(BaseModel):
    location: str
    time: str = Field(default_factory=lambda: datetime.now().isoformat())
    emotional_context: str
    npcs_present: List[str] = Field(default_factory=list)
    open_choices: List[str] = Field(default_factory=list)
    last_exchange_ref: Optional[str] = None
    prompt: str = "What do you do next?"

class Policy(BaseModel):
    sfw_mode: bool = True
    mature_handling: str = "redact"  # redact|reference|inline_if_allowed
    age_verified: bool = False

class Chronicle(BaseModel):
    chronicle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0"
    timeline: Timeline = Field(default_factory=Timeline)
    characters: Dict[str, Character] = Field(default_factory=dict)
    world: World = Field(default_factory=World)
    current: CurrentScenario
    indexes: Dict[str, Dict[str, List[str]]] = Field(default_factory=lambda: {"by_character": {}, "by_tag": {}})
    policy: Policy = Field(default_factory=Policy)

class GameState(BaseModel):
    current_location: str
    current_time: str = Field(default_factory=lambda: datetime.now().isoformat())
    protagonist: Character
    npcs: Dict[str, Character] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    relationships: Dict[str, Relationship] = Field(default_factory=dict)
    academic_status: Dict[str, Any] = Field(default_factory=dict)
    stress_level: int = 0
    energy_level: int = 100
    mood: str = "neutral"
    recent_events: List[str] = Field(default_factory=list)

class DMResponse(BaseModel):
    narrative: str
    suggested_actions: List[str] = Field(default_factory=list)
    state_patch: Dict[str, Any] = Field(default_factory=dict)
    scene_tags: List[str] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)

class ScenarioMechanics(BaseModel):
    time_advancement: str = "flexible"
    consequence_system: str = "grades_stress_relationships"
    choice_structure: str = "open_ended"

class DMBehavior(BaseModel):
    tone: str
    pacing: str
    description_style: str
    interaction_style: str
    special_instructions: List[str] = Field(default_factory=list)

class SafetyConstraints(BaseModel):
    sfw_lock: bool = False
    content_boundaries: List[str] = Field(default_factory=list)
    trigger_warnings: List[str] = Field(default_factory=list)

class Scenario(BaseModel):
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    setting: Dict[str, Any]
    dm_behavior: DMBehavior
    safety: SafetyConstraints
    mechanics: ScenarioMechanics
    initial_state: GameState
    tags: List[str] = Field(default_factory=list)
    author: str = "Unknown"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
