"""Configuration management for Vibecon."""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any


class ConfigManager:
    """Manages loading and merging of Vibecon configuration files."""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load JSON config file, return empty dict if not found or invalid."""
        path = os.path.expanduser(config_path)
        if not os.path.exists(path):
            return {}
        
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {path}: {e}")
            sys.exit(1)
    
    def get_merged_config(self) -> Dict[str, Any]:
        """Load and merge global + project configs."""
        global_cfg = self.load_config("~/.vibecon.json")
        project_cfg = self.load_config(os.path.join(self.project_root, ".vibecon.json"))
        
        return {
            "mounts": global_cfg.get("mounts", []) + project_cfg.get("mounts", []),
        }