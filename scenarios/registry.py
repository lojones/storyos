import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import logging
from datetime import datetime

from .schema import ScenarioSchema, validate_scenario_dict, ScenarioValidationError
from dm.models import Scenario


logger = logging.getLogger(__name__)


class ScenarioRegistry:
    def __init__(self, packs_dir: str = "scenarios/packs"):
        self.packs_dir = Path(packs_dir)
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        self._scenarios: Dict[str, Scenario] = {}
        self._load_all_scenarios()
    
    def _load_all_scenarios(self):
        """Load all scenarios from the packs directory."""
        self._scenarios.clear()
        
        for file_path in self.packs_dir.glob("*.json"):
            try:
                self._load_scenario_file(file_path, "json")
            except Exception as e:
                logger.error(f"Failed to load JSON scenario {file_path}: {e}")
        
        for file_path in self.packs_dir.glob("*.yaml"):
            try:
                self._load_scenario_file(file_path, "yaml")
            except Exception as e:
                logger.error(f"Failed to load YAML scenario {file_path}: {e}")
        
        for file_path in self.packs_dir.glob("*.yml"):
            try:
                self._load_scenario_file(file_path, "yaml")
            except Exception as e:
                logger.error(f"Failed to load YML scenario {file_path}: {e}")
        
        logger.info(f"Loaded {len(self._scenarios)} scenarios")
    
    def _load_scenario_file(self, file_path: Path, format_type: str):
        """Load a single scenario file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if format_type == "json":
                    data = json.load(f)
                else:  # yaml
                    data = yaml.safe_load(f)
            
            # Validate against simplified schema
            validated_scenario = validate_scenario_dict(data)
            
            # Convert to internal Scenario model
            scenario = self._schema_to_scenario(validated_scenario)
            
            if scenario.id in self._scenarios:
                logger.warning(f"Duplicate scenario ID '{scenario.id}' in {file_path}")
            
            self._scenarios[scenario.id] = scenario
            logger.debug(f"Loaded scenario '{scenario.id}' from {file_path}")
            
        except ScenarioValidationError as e:
            logger.error(f"Validation error in {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading scenario from {file_path}: {e}")
            raise
    
    def _schema_to_scenario(self, schema: ScenarioSchema) -> Scenario:
        """Convert simplified schema to internal Scenario model with sensible defaults."""
        from dm.models import (
            DMBehavior, SafetyConstraints, ScenarioMechanics,
            GameState, Character, Relationship
        )
        
        # Map simplified freeform behaviour into structured DMBehavior defaults
        dm_behavior = DMBehavior(
            tone="grounded",
            pacing="moderate",
            description_style="detailed",
            interaction_style="realistic",
            special_instructions=[schema.dungeon_master_behaviour]
        )
        
        safety = SafetyConstraints(
            sfw_lock=False,
            content_boundaries=[],
            trigger_warnings=[],
        )
        
        mechanics = ScenarioMechanics(
            time_advancement="flexible",
            consequence_system="grades_stress_relationships",
            choice_structure="open_ended",
        )
        
        # Initial state derived from simplified fields
        protagonist = Character(
            name=schema.player_name,
            role=schema.role,
            current_status="Starting their journey",
            traits=[],
            relationships={},
            inventory=[],
            goals=[],
        )
        
        initial_state = GameState(
            current_location=schema.initial_location,
            current_time=datetime.now().isoformat(),
            protagonist=protagonist,
            npcs={},
            inventory=list(protagonist.inventory),
            relationships=dict(protagonist.relationships),
            academic_status={},
            stress_level=10,
            energy_level=100,
            mood="neutral",
            recent_events=[],
        )
        
        return Scenario(
            id=schema.id,
            name=schema.name,
            description=schema.description,
            version=schema.version,
            setting={"summary": schema.setting},
            dm_behavior=dm_behavior,
            safety=safety,
            mechanics=mechanics,
            initial_state=initial_state,
            tags=[],
            author=schema.author,
            created_at=schema.created_at,
        )
    
    def get_scenario(self, scenario_id: str) -> Optional[Scenario]:
        """Get a scenario by ID."""
        return self._scenarios.get(scenario_id)
    
    def list_scenarios(self, tag_filter: Optional[str] = None) -> List[Scenario]:
        """List all available scenarios, optionally filtered by tag."""
        scenarios = list(self._scenarios.values())
        
        if tag_filter:
            scenarios = [s for s in scenarios if tag_filter in s.tags]
        
        return sorted(scenarios, key=lambda s: s.name)
    
    def get_scenario_info(self, scenario_id: str) -> Optional[Dict]:
        """Get basic info about a scenario without loading full data."""
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            return None
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "version": scenario.version,
            "tags": scenario.tags,
            "author": scenario.author,
            "sfw_lock": scenario.safety.sfw_lock,
            "age_rating": getattr(scenario.safety, 'age_rating', 'teen')
        }
    
    def validate_scenario_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """Validate a scenario file without loading it into registry."""
        try:
            path = Path(file_path)
            
            with open(path, 'r', encoding='utf-8') as f:
                if path.suffix.lower() == '.json':
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)
            
            validate_scenario_dict(data)
            return True, None
            
        except ScenarioValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"File error: {str(e)}"
    
    def save_scenario(self, scenario: Scenario, file_path: Optional[str] = None, format_type: str = "json") -> str:
        """Save a scenario to a file using the simplified schema format."""
        if not file_path:
            safe_name = "".join(c for c in scenario.id if c.isalnum() or c in '-_')
            extension = "json" if format_type == "json" else "yaml"
            file_path = self.packs_dir / f"{safe_name}.{extension}"
        else:
            file_path = Path(file_path)
        
        # Convert scenario to simplified schema format for saving
        schema_data = self._scenario_to_schema_dict(scenario)
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            if format_type == "json":
                json.dump(schema_data, f, indent=2, ensure_ascii=False)
            else:
                yaml.dump(schema_data, f, default_flow_style=False, allow_unicode=True)
        
        # Reload registry to include new scenario
        self._load_all_scenarios()
        
        return str(file_path)
    
    def _scenario_to_schema_dict(self, scenario: Scenario) -> Dict:
        """Convert internal Scenario model to simplified schema dictionary for saving."""
        setting_summary = ""
        try:
            if isinstance(scenario.setting, dict):
                setting_summary = scenario.setting.get("summary") or json.dumps(scenario.setting, ensure_ascii=False)
            else:
                setting_summary = str(scenario.setting)
        except Exception:
            setting_summary = str(scenario.setting)
        
        dm_instructions = "\n".join(scenario.dm_behavior.special_instructions) if scenario.dm_behavior.special_instructions else ""
        if not dm_instructions:
            # Compose minimal instruction from structured fields
            dm_instructions = (
                f"Tone: {scenario.dm_behavior.tone}; Pacing: {scenario.dm_behavior.pacing}; "
                f"Style: {scenario.dm_behavior.description_style}; Interaction: {scenario.dm_behavior.interaction_style}."
            )
        
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "version": scenario.version,
            "setting": setting_summary,
            "dungeon_master_behaviour": dm_instructions,
            "initial_location": scenario.initial_state.current_location,
            "player_name": scenario.initial_state.protagonist.name,
            "role": scenario.initial_state.protagonist.role,
            "author": scenario.author,
            "created_at": scenario.created_at,
        }
    
    def reload(self):
        """Reload all scenarios from disk."""
        self._load_all_scenarios()
    
    def get_tags(self) -> List[str]:
        """Get all unique tags across scenarios."""
        all_tags = set()
        for scenario in self._scenarios.values():
            all_tags.update(scenario.tags)
        return sorted(list(all_tags))
    
    def delete_scenario(self, scenario_id: str) -> bool:
        """Delete a scenario from the registry (does not remove file)."""
        if scenario_id in self._scenarios:
            del self._scenarios[scenario_id]
            return True
        return False