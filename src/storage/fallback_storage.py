 # MongoDB-LLM-assistant\src\storage\fallback_storage.py
"""
Fallback Storage Manager - Works without MongoDB
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import pickle
import hashlib

from .config import FILE_STORAGE_CONFIG, AUTO_SAVE_CONFIG

logger = logging.getLogger(__name__)


class FileOnlyStorageManager:
    """
    File-based storage manager that works without MongoDB
    All metadata stored in JSON files
    """
    
    def __init__(self):
        """Initialize file-only storage"""
        self.storage_paths = self._initialize_storage_paths()
        self.metadata_file = self.storage_paths["exports"] / "metadata.json"
        self.model_registry_file = self.storage_paths["models"] / "registry.json"
        self._load_metadata()
        logger.info("FileOnlyStorageManager initialized (MongoDB not available)")
    
    def _initialize_storage_paths(self) -> Dict[str, Path]:
        """Create storage directories"""
        base_dir = Path(FILE_STORAGE_CONFIG["base_dir"])  # Ensure Path object
        paths = {}
        
        for name, subdir in FILE_STORAGE_CONFIG["subdirs"].items():
            full_path = base_dir / subdir
            full_path.mkdir(parents=True, exist_ok=True)
            paths[name] = full_path
            
        return paths
    
    def _load_metadata(self):
        """Load metadata from JSON files"""
        # Load anomaly metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {"analyses": [], "last_updated": None}
        
        # Load model registry
        if self.model_registry_file.exists():
            with open(self.model_registry_file, 'r') as f:
                self.model_registry = json.load(f)
        else:
            self.model_registry = {"models": [], "active_model": None}
    
    def _save_metadata(self):
        """Save metadata to JSON files"""
        self.metadata["last_updated"] = datetime.utcnow().isoformat()
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2, default=str)
        
        with open(self.model_registry_file, 'w') as f:
            json.dump(self.model_registry, f, indent=2, default=str)
    
    async def initialize(self) -> bool:
        """Initialize storage (compatibility method)"""
        return True
    
    async def shutdown(self):
        """Cleanup (compatibility method)"""
        self._save_metadata()
    
    async def save_anomaly_analysis(self, 
                                   analysis_result: Dict[str, Any],
                                   source_type: str = "unknown",
                                   host: str = None,
                                   time_range: str = None,
                                   auto_save: bool = None) -> Dict[str, str]:
        """Save analysis to file system only"""
        try:
            # Generate analysis ID
            analysis_id = self._generate_analysis_id()
            timestamp = datetime.utcnow()
            
            # Prepare data
            analysis_data = {
                "analysis_id": analysis_id,
                "timestamp": timestamp.isoformat(),
                "source_type": source_type,
                "host": host,
                "time_range": time_range,
                "result": analysis_result
            }
            
            # Save to file
            file_name = f"analysis_{analysis_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            file_path = self.storage_paths["exports"] / file_name
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, indent=2, default=str)
            
            # Update metadata
            self.metadata["analyses"].append({
                "analysis_id": analysis_id,
                "timestamp": timestamp.isoformat(),
                "file_path": str(file_path),
                "source_type": source_type,
                "host": host,
                "summary": analysis_result.get("data", {}).get("summary", {})
            })
            
            # Keep only last 100 analyses in metadata
            if len(self.metadata["analyses"]) > 100:
                self.metadata["analyses"] = self.metadata["analyses"][-100:]
            
            self._save_metadata()
            
            logger.info(f"Analysis saved to file: {file_path}")
            
            return {
                "analysis_id": analysis_id,
                "file_path": str(file_path)
            }
            
        except Exception as e:
            logger.error(f"Error saving analysis: {e}")
            return {}
    
    async def get_anomaly_history(self,
                                 filters: Dict[str, Any] = None,
                                 limit: int = 100,
                                 skip: int = 0,
                                 include_details: bool = False) -> List[Dict[str, Any]]:
        """Get analysis history from metadata"""
        try:
            analyses = self.metadata.get("analyses", [])
            
            # Apply filters
            if filters:
                if "host" in filters:
                    analyses = [a for a in analyses if a.get("host") == filters["host"]]
                if "source_type" in filters:
                    analyses = [a for a in analyses if a.get("source_type") == filters["source_type"]]
            
            # Sort by timestamp (newest first)
            analyses.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Apply pagination
            analyses = analyses[skip:skip + limit]
            
            # Load details if requested
            if include_details:
                for analysis in analyses:
                    file_path = Path(analysis.get("file_path", ""))
                    if file_path.exists():
                        with open(file_path, 'r') as f:
                            full_data = json.load(f)
                            analysis["detailed_data"] = full_data
            
            return analyses
            
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []
    
    def _generate_analysis_id(self) -> str:
        """Generate unique analysis ID"""
        timestamp = datetime.utcnow().isoformat()
        return f"file_{hashlib.md5(timestamp.encode()).hexdigest()[:12]}"
    
    # MongoDB uyumluluk metodları (boş implementasyon)
    async def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Get statistics (limited without MongoDB)"""
        total_analyses = len(self.metadata.get("analyses", []))
        total_models = len(self.model_registry.get("models", []))
        
        return {
            "analysis_stats": {
                "total_analyses": total_analyses,
                "source": "file_system"
            },
            "storage_stats": {
                "total_models": total_models
            }
        }