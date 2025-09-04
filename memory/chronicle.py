import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from cryptography.fernet import Fernet
import os
import base64

from dm.models import Chronicle, Event, Character, World, CurrentScenario, Policy, Phase, Timeline


class MatureContentHandler:
    def __init__(self, encryption_key: Optional[str] = None):
        self.encryption_key = encryption_key
        if encryption_key:
            # Ensure key is 32 bytes for Fernet
            key_bytes = bytes.fromhex(encryption_key) if len(encryption_key) == 64 else encryption_key.encode()[:32]
            key_b64 = base64.urlsafe_b64encode(key_bytes)
            self.cipher = Fernet(key_b64)
        else:
            self.cipher = None
    
    def process_content(self, content: str, policy: Policy, content_type: str = "narrative") -> tuple[str, Optional[str]]:
        """Process content based on mature content policy."""
        is_mature = self._is_mature_content(content)
        
        if not is_mature:
            return content, None
        
        if policy.mature_handling == "redact":
            return self._redact_content(content, content_type), None
        elif policy.mature_handling == "reference" and self.cipher:
            redacted = self._redact_content(content, content_type)
            vault_key = self._encrypt_to_vault(content)
            return redacted, vault_key
        elif policy.mature_handling == "inline_if_allowed" and policy.age_verified:
            return content, None
        else:
            # Fallback to redaction
            return self._redact_content(content, content_type), None
    
    def _is_mature_content(self, content: str) -> bool:
        """Simple heuristic to detect mature content."""
        mature_keywords = [
            'explicit', 'sexual', 'intimate', 'romantic', 'adult',
            'violence', 'blood', 'death', 'drugs', 'alcohol'
        ]
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in mature_keywords)
    
    def _redact_content(self, content: str, content_type: str) -> str:
        """Create a redacted version of mature content."""
        if content_type == "narrative":
            return "[Content redacted - mature themes present]"
        elif content_type == "dialogue":
            return "[Dialogue redacted - mature content]"
        else:
            return "[Redacted content]"
    
    def _encrypt_to_vault(self, content: str) -> str:
        """Encrypt content and store in vault, return reference key."""
        if not self.cipher:
            return None
        
        encrypted = self.cipher.encrypt(content.encode())
        vault_key = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        vault_dir = Path("data/vault")
        vault_dir.mkdir(exist_ok=True)
        
        vault_file = vault_dir / f"{vault_key}.bin"
        with open(vault_file, "wb") as f:
            f.write(encrypted)
        
        return vault_key
    
    def retrieve_from_vault(self, vault_key: str) -> Optional[str]:
        """Retrieve and decrypt content from vault."""
        if not self.cipher or not vault_key:
            return None
        
        vault_file = Path("data/vault") / f"{vault_key}.bin"
        if not vault_file.exists():
            return None
        
        try:
            with open(vault_file, "rb") as f:
                encrypted = f.read()
            decrypted = self.cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception:
            return None


class ChronicleManager:
    def __init__(self, data_dir: str = "data", encryption_key: Optional[str] = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.saves_dir = self.data_dir / "saves"
        self.transcripts_dir = self.data_dir / "transcripts"
        self.saves_dir.mkdir(exist_ok=True)
        self.transcripts_dir.mkdir(exist_ok=True)
        
        self.mature_handler = MatureContentHandler(encryption_key)
    
    def create_chronicle(self, scenario_id: str, initial_current: CurrentScenario, policy: Policy) -> Chronicle:
        """Create a new chronicle."""
        return Chronicle(
            scenario_id=scenario_id,
            current=initial_current,
            policy=policy
        )
    
    def persist_event(self, chronicle: Chronicle, event_data: Dict[str, Any]) -> Chronicle:
        """Add an event to the chronicle timeline."""
        # Process mature content
        event_data["sfw_level"] = "sfw"
        event_data["mature_pointer"] = None
        
        for field in ["player_action", "dm_outcome", "title"]:
            if field in event_data:
                processed_content, vault_key = self.mature_handler.process_content(
                    event_data[field], chronicle.policy, field
                )
                event_data[field] = processed_content
                if vault_key:
                    event_data["sfw_level"] = "mature"
                    event_data["mature_pointer"] = vault_key
        
        event = Event(**event_data)
        
        # Add to current phase or create new one
        if not chronicle.timeline.phases:
            phase = Phase(title="Opening", events=[event])
            chronicle.timeline.phases.append(phase)
        else:
            chronicle.timeline.phases[-1].events.append(event)
        
        # Update indexes
        for participant in event.participants:
            if participant not in chronicle.indexes["by_character"]:
                chronicle.indexes["by_character"][participant] = []
            chronicle.indexes["by_character"][participant].append(event.event_id)
        
        for tag in event.tags:
            if tag not in chronicle.indexes["by_tag"]:
                chronicle.indexes["by_tag"][tag] = []
            chronicle.indexes["by_tag"][tag].append(event.event_id)
        
        chronicle.updated_at = datetime.now().isoformat()
        return chronicle
    
    def persist_character_update(self, chronicle: Chronicle, character_name: str, character_data: Dict[str, Any]) -> Chronicle:
        """Update character information in the chronicle."""
        # Process mature content in character data
        character_data["sfw_level"] = "sfw"
        character_data["mature_pointer"] = None
        
        for field in ["current_status", "recent_changes"]:
            if field in character_data:
                if isinstance(character_data[field], list):
                    processed_list = []
                    for item in character_data[field]:
                        processed_content, vault_key = self.mature_handler.process_content(
                            str(item), chronicle.policy, field
                        )
                        processed_list.append(processed_content)
                        if vault_key:
                            character_data["sfw_level"] = "mature"
                            character_data["mature_pointer"] = vault_key
                    character_data[field] = processed_list
                else:
                    processed_content, vault_key = self.mature_handler.process_content(
                        character_data[field], chronicle.policy, field
                    )
                    character_data[field] = processed_content
                    if vault_key:
                        character_data["sfw_level"] = "mature"
                        character_data["mature_pointer"] = vault_key
        
        character = Character(**character_data)
        chronicle.characters[character_name] = character
        chronicle.updated_at = datetime.now().isoformat()
        return chronicle
    
    def persist_world_update(self, chronicle: Chronicle, world_updates: Dict[str, Any]) -> Chronicle:
        """Update world state in the chronicle."""
        # Process mature content in world updates
        world_data = chronicle.world.dict()
        world_data.update(world_updates)
        world_data["sfw_level"] = "sfw"
        world_data["mature_pointer"] = None
        
        for field in ["setting", "rules_mechanics", "ongoing_plots", "global_changes"]:
            if field in world_data and isinstance(world_data[field], list):
                processed_list = []
                for item in world_data[field]:
                    processed_content, vault_key = self.mature_handler.process_content(
                        str(item), chronicle.policy, field
                    )
                    processed_list.append(processed_content)
                    if vault_key:
                        world_data["sfw_level"] = "mature"
                        world_data["mature_pointer"] = vault_key
                world_data[field] = processed_list
        
        chronicle.world = World(**world_data)
        chronicle.updated_at = datetime.now().isoformat()
        return chronicle
    
    def snapshot_current(self, chronicle: Chronicle, current_data: Dict[str, Any]) -> Chronicle:
        """Update the current scenario snapshot."""
        # Process mature content
        current_data["sfw_level"] = "sfw"
        current_data["mature_pointer"] = None
        
        for field in ["emotional_context", "prompt"]:
            if field in current_data:
                processed_content, vault_key = self.mature_handler.process_content(
                    current_data[field], chronicle.policy, field
                )
                current_data[field] = processed_content
                if vault_key:
                    current_data["sfw_level"] = "mature"
                    current_data["mature_pointer"] = vault_key
        
        chronicle.current = CurrentScenario(**current_data)
        chronicle.updated_at = datetime.now().isoformat()
        return chronicle
    
    def save_chronicle(self, chronicle: Chronicle, filename: Optional[str] = None) -> str:
        """Save chronicle to disk."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chronicle_{chronicle.session_id[:8]}_{timestamp}.json"
        
        filepath = self.saves_dir / filename
        with open(filepath, "w") as f:
            json.dump(chronicle.dict(), f, indent=2, default=str)
        
        return str(filepath)
    
    def load_chronicle(self, filepath: str) -> Chronicle:
        """Load chronicle from disk."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return Chronicle(**data)
    
    def export_chronicle(self, chronicle: Chronicle, include_vault_refs: bool = False) -> Dict[str, Any]:
        """Export chronicle for sharing, optionally including vault references."""
        export_data = chronicle.dict()
        
        if not include_vault_refs:
            # Remove vault pointers for clean export
            self._remove_vault_refs(export_data)
        
        return export_data
    
    def _remove_vault_refs(self, data: Any):
        """Recursively remove vault references from export data."""
        if isinstance(data, dict):
            if "mature_pointer" in data:
                data["mature_pointer"] = None
            for value in data.values():
                self._remove_vault_refs(value)
        elif isinstance(data, list):
            for item in data:
                self._remove_vault_refs(item)
    
    def compress_timeline(self, chronicle: Chronicle, max_events_per_phase: int = 50) -> Chronicle:
        """Compress timeline by merging older events if phases get too long."""
        for phase in chronicle.timeline.phases[:-1]:  # Don't compress current phase
            if len(phase.events) > max_events_per_phase:
                # Keep first and last few events, summarize middle ones
                keep_start = 10
                keep_end = 10
                
                events_to_keep = (
                    phase.events[:keep_start] +
                    phase.events[-keep_end:]
                )
                
                # Create summary event for compressed middle
                middle_events = phase.events[keep_start:-keep_end]
                if middle_events:
                    summary_event = Event(
                        title=f"Summary of {len(middle_events)} events",
                        timestamp=middle_events[0].timestamp,
                        location="Various",
                        participants=list(set(p for e in middle_events for p in e.participants)),
                        player_action="Multiple actions taken",
                        dm_outcome=f"Events compressed from {middle_events[0].timestamp} to {middle_events[-1].timestamp}",
                        consequences=["Timeline compressed for storage efficiency"],
                        tags=["compressed_summary"]
                    )
                    events_to_keep.insert(keep_start, summary_event)
                
                phase.events = events_to_keep
        
        chronicle.updated_at = datetime.now().isoformat()
        return chronicle
    
    def get_recent_events(self, chronicle: Chronicle, limit: int = 10) -> List[Event]:
        """Get the most recent events from the timeline."""
        all_events = []
        for phase in chronicle.timeline.phases:
            all_events.extend(phase.events)
        
        # Sort by timestamp and return most recent
        all_events.sort(key=lambda e: e.timestamp, reverse=True)
        return all_events[:limit]
    
    def search_events(self, chronicle: Chronicle, query: str = None, character: str = None, tag: str = None) -> List[Event]:
        """Search events in the chronicle."""
        results = []
        
        if character and character in chronicle.indexes["by_character"]:
            event_ids = chronicle.indexes["by_character"][character]
            for phase in chronicle.timeline.phases:
                for event in phase.events:
                    if event.event_id in event_ids:
                        results.append(event)
        
        if tag and tag in chronicle.indexes["by_tag"]:
            event_ids = chronicle.indexes["by_tag"][tag]
            for phase in chronicle.timeline.phases:
                for event in phase.events:
                    if event.event_id in event_ids:
                        results.append(event)
        
        if query:
            # Simple text search
            for phase in chronicle.timeline.phases:
                for event in phase.events:
                    if (query.lower() in event.title.lower() or
                        query.lower() in event.player_action.lower() or
                        query.lower() in event.dm_outcome.lower()):
                        results.append(event)
        
        # Remove duplicates and sort by timestamp
        unique_results = list({e.event_id: e for e in results}.values())
        unique_results.sort(key=lambda e: e.timestamp, reverse=True)
        
        return unique_results