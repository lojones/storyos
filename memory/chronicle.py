import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64

from dm.models import Chronicle, Event, Character, World, CurrentScenario, Policy, Phase, Timeline


class MatureContentHandler:
    def __init__(self, encryption_key: Optional[str] = None):
        """AES-256-GCM vault with 32-byte key.

        Accepts STORYOS_AES_KEY as base64 string (32-byte) or legacy hex.
        """
        self._aesgcm: Optional[AESGCM] = None
        self._key: Optional[bytes] = None
        self.encryption_key = encryption_key
        if encryption_key:
            k = encryption_key.strip()
            try:
                # Prefer base64 (spec)
                kb = base64.b64decode(k)
            except Exception:
                # Fallback hex
                kb = bytes.fromhex(k) if len(k) in (32, 64) else k.encode()[:32]
            # Ensure 32 bytes
            if len(kb) != 32:
                kb = (kb + b"\x00" * 32)[:32]
            self._key = kb
            self._aesgcm = AESGCM(self._key)
    
    def process_content(self, content: str, policy: Policy, content_type: str = "narrative") -> tuple[str, Optional[str]]:
        """By default, allow all content inline without checks or redactions."""
        return content, None
    
    def _is_mature_content(self, content: str) -> bool:
        """Deprecated: no content classification performed."""
        return False
    
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
        if not self._aesgcm:
            return None
        # AES-GCM encrypt with random 12-byte nonce, store nonce||ciphertext
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, content.encode(), None)
        blob = nonce + ct
        vault_key = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        vault_dir = Path("data/vault")
        vault_dir.mkdir(exist_ok=True)
        
        vault_file = vault_dir / f"{vault_key}.bin"
        with open(vault_file, "wb") as f:
            f.write(blob)
        
        return vault_key
    
    def retrieve_from_vault(self, vault_key: str) -> Optional[str]:
        """Retrieve and decrypt content from vault."""
        if not self._aesgcm or not vault_key:
            return None
        
        vault_file = Path("data/vault") / f"{vault_key}.bin"
        if not vault_file.exists():
            return None
        
        try:
            with open(vault_file, "rb") as f:
                blob = f.read()
            nonce, ct = blob[:12], blob[12:]
            pt = self._aesgcm.decrypt(nonce, ct, None)
            return pt.decode()
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
        # Backward-compat: provide a no-op content processor to avoid errors
        self.mature_handler = type("_NoopContent", (), {
            "process_content": staticmethod(lambda content, policy, field: (content, None))
        })()
    
    def create_chronicle(self, scenario_id: str, initial_current: CurrentScenario, policy: Policy | dict) -> Chronicle:
        """Create a new chronicle.

        Accepts a Policy instance or a plain dict to avoid any class identity
        issues across modules/runtimes. Pydantic will coerce the dict.
        """
        try:
            policy_payload = policy.dict() if hasattr(policy, "dict") else dict(policy)
        except Exception:
            # Fallback to default policy if something unexpected is passed
            policy_payload = Policy().dict()

        return Chronicle(
            scenario_id=scenario_id,
            current=initial_current,
            policy=policy_payload
        )
    
    def persist_event(self, chronicle: Chronicle, event_data: Dict[str, Any]) -> Chronicle:
        """Add an event to the chronicle timeline."""
        # No content processing; persist as-is
        
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
