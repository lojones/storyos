import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import logging

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
            
            # Validate against schema
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
        """Convert a validated schema to internal Scenario model."""
        from dm.models import (
            DMBehavior, SafetyConstraints, ScenarioMechanics,
            GameState, Character, Relationship
        )
        
        # Convert DM behavior
        dm_behavior = DMBehavior(
            tone=schema.dm_behavior.tone,
            pacing=schema.dm_behavior.pacing,
            description_style=schema.dm_behavior.description_style,
            interaction_style=schema.dm_behavior.interaction_style,
            special_instructions=schema.dm_behavior.special_instructions
        )
        
        # Convert safety constraints
        safety = SafetyConstraints(
            sfw_lock=schema.safety.sfw_lock,
            content_boundaries=schema.safety.content_boundaries,
            trigger_warnings=schema.safety.trigger_warnings
        )
        
        # Convert mechanics
        mechanics = ScenarioMechanics(
            time_advancement=schema.mechanics.time_advancement,
            consequence_system=schema.mechanics.consequence_system,
            choice_structure=schema.mechanics.choice_structure
        )
        
        # Convert initial state
        protagonist = Character(
            name=schema.initial_state.protagonist.name,
            role=schema.initial_state.protagonist.role,
            current_status=schema.initial_state.protagonist.current_status,
            traits=schema.initial_state.protagonist.traits,
            relationships={
                k: Relationship(**v) for k, v in schema.initial_state.protagonist.relationships.items()
            },
            inventory=schema.initial_state.protagonist.inventory,
            goals=schema.initial_state.protagonist.goals
        )
        
        npcs = {}
        for npc_name, npc_data in schema.initial_state.npcs.items():
            npcs[npc_name] = Character(
                name=npc_data.name,
                role=npc_data.role,
                current_status=npc_data.current_status,
                traits=npc_data.traits,
                relationships={k: Relationship(**v) for k, v in npc_data.relationships.items()},
                inventory=npc_data.inventory,
                goals=npc_data.goals
            )
        
        initial_state = GameState(
            current_location=schema.initial_state.current_location,
            current_time=schema.initial_state.current_time,
            protagonist=protagonist,
            npcs=npcs,
            academic_status=schema.initial_state.academic_status,
            stress_level=schema.initial_state.stress_level,
            energy_level=schema.initial_state.energy_level,
            mood=schema.initial_state.mood
        )
        
        return Scenario(
            id=schema.id,
            name=schema.name,
            description=schema.description,
            version=schema.version,
            setting=schema.setting,
            dm_behavior=dm_behavior,
            safety=safety,
            mechanics=mechanics,
            initial_state=initial_state,
            tags=schema.tags,
            author=schema.author,
            created_at=schema.created_at
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
        """Save a scenario to a file."""
        if not file_path:
            safe_name = "".join(c for c in scenario.id if c.isalnum() or c in '-_')
            extension = "json" if format_type == "json" else "yaml"
            file_path = self.packs_dir / f"{safe_name}.{extension}"
        else:
            file_path = Path(file_path)
        
        # Convert scenario to schema format for saving
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
        """Convert internal Scenario model to schema dictionary for saving."""
        return {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "version": scenario.version,
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
                "trigger_warnings": scenario.safety.trigger_warnings,
                "age_rating": "teen"  # Default
            },
            "mechanics": {
                "time_advancement": scenario.mechanics.time_advancement,
                "consequence_system": scenario.mechanics.consequence_system,
                "choice_structure": scenario.mechanics.choice_structure,
                "skill_checks": False,
                "inventory_management": True
            },
            "initial_state": {
                "current_location": scenario.initial_state.current_location,
                "current_time": scenario.initial_state.current_time,
                "protagonist": {
                    "name": scenario.initial_state.protagonist.name,
                    "role": scenario.initial_state.protagonist.role,
                    "current_status": scenario.initial_state.protagonist.current_status,
                    "traits": scenario.initial_state.protagonist.traits,
                    "relationships": {
                        k: {"status": v.status, "score": v.score}
                        for k, v in scenario.initial_state.protagonist.relationships.items()
                    },
                    "inventory": scenario.initial_state.protagonist.inventory,
                    "goals": scenario.initial_state.protagonist.goals
                },
                "npcs": {
                    k: {
                        "name": v.name,
                        "role": v.role,
                        "current_status": v.current_status,
                        "traits": v.traits,
                        "relationships": {
                            rk: {"status": rv.status, "score": rv.score}
                            for rk, rv in v.relationships.items()
                        },
                        "inventory": v.inventory,
                        "goals": v.goals
                    }
                    for k, v in scenario.initial_state.npcs.items()
                },
                "academic_status": scenario.initial_state.academic_status,
                "stress_level": scenario.initial_state.stress_level,
                "energy_level": scenario.initial_state.energy_level,
                "mood": scenario.initial_state.mood
            },
            "tags": scenario.tags,
            "author": scenario.author,
            "created_at": scenario.created_at
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