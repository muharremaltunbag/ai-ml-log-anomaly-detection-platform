# MongoDB-LLM-assistant\src\storage\storage_manager.py
"""
Storage Manager - Hybrid Storage Orchestrator
Manages both MongoDB metadata and file system storage
"""
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import json
import shutil
import aiofiles
import pickle
import joblib

from .mongodb_handler import MongoDBHandler
from .config import (
    FILE_STORAGE_CONFIG, 
    AUTO_SAVE_CONFIG,
    STORAGE_LIMITS,
    initialize_storage_dirs
)

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Unified storage manager for anomaly detection system
    Coordinates MongoDB metadata storage and file system storage
    """
    
    def __init__(self, mongodb_uri: str = None, database: str = None):
        """
        Initialize storage manager
        
        Args:
            mongodb_uri: MongoDB connection string
            database: Database name
        """
        # Initialize storage directories
        initialize_storage_dirs()
        
        # Initialize MongoDB handler
        self.mongodb = MongoDBHandler(mongodb_uri, database)
        
        # File storage paths
        self.storage_paths = FILE_STORAGE_CONFIG["subdirs"]
        
        # Auto-save configuration
        self.auto_save_enabled = AUTO_SAVE_CONFIG["enabled"]
        self.auto_save_threshold = AUTO_SAVE_CONFIG["anomaly_threshold"]
        self.auto_save_format = AUTO_SAVE_CONFIG["format"]
        
        # Cache for recent analyses (thread-safe)
        self._analysis_cache = {}
        self._cache_size = 0
        self._cache_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            "analyses_saved": 0,
            "models_saved": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        logger.info("StorageManager initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize storage connections
        
        Returns:
            Success status
        """
        try:
            # Connect to MongoDB
            connected = await self.mongodb.connect()
            if not connected:
                logger.error("❌ MongoDB bağlantısı BAŞARISIZ!")
                logger.error(f"   URI: {self.mongodb.connection_string[:50]}...")
                return False
            else:
                logger.info("✅ MongoDB bağlantısı BAŞARILI!")
                logger.info(f"   📍 Database: {self.mongodb.database}")
                logger.info(f"   📍 Collections: anomaly_results, model_registry")
                
                # Disk alanı kontrolü
                await self.check_and_cleanup_by_size()
            
            # Verify file storage paths
            for name, path in self.storage_paths.items():
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created storage directory: {path}")
            
            logger.info("StorageManager fully initialized")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing StorageManager: {e}")
            return False
    
    async def shutdown(self):
        """Cleanup and close connections"""
        try:
            # Save any cached data
            if self._analysis_cache:
                await self._flush_cache()
            
            # Close MongoDB connection
            await self.mongodb.disconnect()
            
            logger.info("StorageManager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    async def save_anomaly_analysis(self, 
                                   analysis_result: Dict[str, Any],
                                   source_type: str = "unknown",
                                   host: str = None,
                                   time_range: str = None,
                                   auto_save: bool = None,
                                   uploaded_filename: str = None,
                                   model_info: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Save complete anomaly analysis (metadata + data)
        
        Args:
            analysis_result: Result from analyze_mongodb_logs
            source_type: Source of data (opensearch, file, etc.)
            host: Host filter if applicable
            time_range: Time range of analysis
            auto_save: Override auto-save setting
            uploaded_filename: Filename for uploaded files
            model_info: Model metadata (version, path, ensemble info, etc.)
        Returns:
            Dictionary with analysis_id and file_path
        """
        try:
            # Check auto-save setting
            if auto_save is None:
                auto_save = self.auto_save_enabled
            
            if not auto_save:
                logger.debug("Auto-save disabled, skipping")
                return {}
            
            # Disk alanı kontrolü - her kayıt öncesi
            await self.check_and_cleanup_by_size()
            
            # Prepare source info
            source_info = {
                "source_type": source_type,
                "host": host,
                "time_range": time_range,
                "timestamp": datetime.utcnow().isoformat()
            }

            # ✅ YENİ: Upload için ek metadata
            if source_type == "upload" and uploaded_filename:
                source_info["uploaded_filename"] = uploaded_filename
                # analysis_result içinden server_info çıkar
                sonuc = analysis_result.get("sonuç") or {}
                if isinstance(sonuc, dict):
                    server_info = sonuc.get("server_info", {})
                    if isinstance(server_info, dict) and server_info:
                        source_info["server_name"] = server_info.get("server_name")
                        source_info["model_status"] = server_info.get("model_status")
                        source_info["model_path"] = server_info.get("model_path")
                logger.info(f"📁 Upload metadata eklendi: {uploaded_filename}")
            
            # ✅ NEW: normalize incoming analysis_result to a safe, consistent dict
            analysis_result = self._normalize_analysis_result(analysis_result, source_info)
            
            # Helpful debug: how many critical anomalies will we store?
            try:
                _kritik = 0
                if isinstance(analysis_result.get("sonuç"), dict):
                    _kritik = len(analysis_result["sonuç"].get("critical_anomalies", []))
                logger.info(f"📊 Kayıt öncesi kritik anomali sayısı: {_kritik}")
            except Exception as _e:
                logger.warning(f"Normalize debug failed: {_e}")
            
            # Save metadata to MongoDB
            analysis_id = await self.mongodb.save_anomaly_result(
                analysis_result, 
                source_info,
                model_info
            )
            
            # ✅ YENİ: MongoDB kayıt durumunu detaylı logla
            if analysis_id:
                logger.info(f"✅ MongoDB KAYIT BAŞARILI - Analysis ID: {analysis_id}")
                logger.info(f"   📍 Database: {self.mongodb.database}")
                logger.info(f"   📍 Collection: anomaly_results")
                logger.info(f"   📍 Host: {host or 'all'}")
                logger.info(f"   📍 Time Range: {time_range}")
                logger.info(f"   📍 Source Type: {source_type}")
                if source_type == "upload" and uploaded_filename:
                    logger.info(f"   📍 Uploaded Filename: {uploaded_filename}")
                    logger.info(f"   📍 Server Name: {source_info.get('server_name')}")
                    logger.info(f"   📍 Model Status: {source_info.get('model_status')}")
                    logger.info(f"   📍 Model Path: {source_info.get('model_path')}")
            else:
                logger.error("❌ MongoDB KAYIT BAŞARISIZ - Analysis ID alınamadı!")
            
            # Save detailed data to file system
            file_path = await self._save_analysis_file(
                analysis_id,
                analysis_result,
                source_info,
                model_info
            )
            
            # Update statistics
            self.stats["analyses_saved"] += 1
            
            # Add to cache
            await self._add_to_cache(analysis_id, analysis_result)
            
            logger.info(f"Analysis saved - ID: {analysis_id}, File: {file_path}")
            
            return {
                "analysis_id": analysis_id,
                "file_path": str(file_path)
            }
            
        except Exception as e:
            logger.error(f"Error saving anomaly analysis: {e}")
            return {}
    
    async def save_model(self,
                        model_path: str,
                        model_info: Dict[str, Any],
                        performance_metrics: Dict[str, Any] = None,
                        backup_previous: bool = True) -> str:
        """
        Save model with metadata and optional backup
        
        Args:
            model_path: Path to model file
            model_info: Model information
            performance_metrics: Model performance metrics
            backup_previous: Backup previous model version
            
        Returns:
            Model version ID
        """
        try:
            model_file = Path(model_path)
            
            # Backup previous model if exists
            if backup_previous and model_file.exists():
                await self._backup_model(model_file)
            
            # Save model metadata to MongoDB
            version_id = await self.mongodb.save_model_metadata(
                model_info,
                model_path,
                performance_metrics
            )
            
            # Copy model to versioned storage
            versioned_path = self.storage_paths["models"] / f"model_{version_id}.pkl"
            if model_file.exists():
                shutil.copy2(model_file, versioned_path)
                logger.info(f"Model copied to versioned storage: {versioned_path}")
            
            # Update statistics
            self.stats["models_saved"] += 1
            
            return version_id
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return ""
    
    async def get_anomaly_history(self,
                                 filters: Dict[str, Any] = None,
                                 limit: int = 100,
                                 skip: int = 0,
                                 include_details: bool = False) -> List[Dict[str, Any]]:
        """
        Get anomaly history with optional detailed data

        Supports fallback to JSON files if MongoDB doesn't have the record

        Args:
            filters: Query filters
            limit: Maximum results
            skip: Skip for pagination
            include_details: Load full details from files

        Returns:
            List of anomaly analyses
        """
        try:
            # Get metadata from MongoDB
            analyses = await self.mongodb.get_anomaly_history(filters, limit, skip)

            # ========== YENİ: JSON FALLBACK ==========
            # Eğer MongoDB'de bulunamadıysa ve analysis_id filtresi varsa, JSON'dan dene
            if not analyses and filters and "analysis_id" in filters:
                analysis_id = filters["analysis_id"]
                logger.info(f"MongoDB'de bulunamadı, JSON fallback deneniyor: {analysis_id}")

                # JSON dosyasından yükle (backward compat ile)
                json_data = await self._load_analysis_file(analysis_id)

                if json_data:
                    logger.info(f"✅ JSON fallback başarılı: {analysis_id}")
                    # JSON verisini MongoDB formatına uyumlu hale getir
                    analyses = [{
                        "analysis_id": json_data.get("analysis_id", analysis_id),
                        "host": json_data.get("host") or json_data.get("source_info", {}).get("host"),
                        "source": json_data.get("source", "unknown"),
                        "timestamp": json_data.get("saved_at"),
                        "logs_analyzed": json_data.get("logs_analyzed", 0),
                        "anomaly_count": json_data.get("anomaly_count", json_data.get("critical_count", 0)),
                        "anomaly_rate": json_data.get("anomaly_rate", 0),
                        "time_range": json_data.get("time_range") or json_data.get("source_info", {}).get("time_range"),
                        # Detaylı veri zaten yüklü
                        "detailed_data": json_data,
                        "_from_json_fallback": True  # Debug için işaret
                    }]
                else:
                    logger.warning(f"JSON fallback da başarısız: {analysis_id}")
            # ========== JSON FALLBACK SONU ==========

            # Load detailed data if requested
            if include_details:
                for analysis in analyses:
                    # JSON fallback zaten detaylı veriyi yükledi
                    if analysis.get("_from_json_fallback"):
                        continue

                    analysis_id = analysis.get("analysis_id")
                    
                    # Check cache first (thread-safe)
                    with self._cache_lock:
                        cached = self._analysis_cache.get(analysis_id)
                    if cached is not None:
                        analysis["detailed_data"] = cached
                        self.stats["cache_hits"] += 1
                    else:
                        # Load from file
                        detailed_data = await self._load_analysis_file(analysis_id)
                        if detailed_data:
                            analysis["detailed_data"] = detailed_data
                        self.stats["cache_misses"] += 1

            return analyses

        except Exception as e:
            logger.error(f"Error getting anomaly history: {e}")
            return []
    async def get_latest_analysis(self, 
                                 host: str = None,
                                 source_type: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the most recent analysis
        
        Args:
            host: Filter by host
            source_type: Filter by source type
            
        Returns:
            Latest analysis with details
        """
        try:
            filters = {}
            if host:
                filters["host"] = host
            if source_type:
                filters["source"] = source_type
            
            analyses = await self.get_anomaly_history(
                filters=filters,
                limit=1,
                include_details=True
            )
            
            if analyses:
                return analyses[0]
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest analysis: {e}")
            return None
    
    async def get_dba_analysis_history(self, source_type: str = "opensearch_dba", limit: int = 10, days_back: int = 30) -> List[Dict[str, Any]]:
        """
        Get DBA-specific anomaly analysis history from MongoDB
        
        Args:
            source_type: Source type filter (default: 'opensearch_dba')
            limit: Maximum number of results to return
            days_back: How many days back to search (default: 30)
            
        Returns:
            List of DBA analysis summaries with essential fields for UI display
        """
        try:
            # Build filter with date range
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            filters = {
                "source_type": source_type,
                "start_date": cutoff_date
            }
            
            analyses = await self.mongodb.get_anomaly_history(
                filters=filters,
                limit=limit,
                skip=0
            )
            
            # Format specifically for DBA UI display
            dba_history = []
            for doc in analyses:
                # source_info: mongodb_handler saves as doc["source_info"] (dict)
                # doc["source"] is the raw string like "unknown" — not what we want
                source_info = doc.get("source_info", {})

                # ✅ TYPE KONTROLÜ - source_info string mi dict mi?
                if isinstance(source_info, str):
                    source_info = {"type": source_type, "host": "Unknown", "time_range": ""}
                elif not isinstance(source_info, dict):
                    source_info = {}

                # Read from document top-level fields (set by mongodb_handler.save_anomaly_result)
                # NOT from "analysis_result" which doesn't exist in the document schema
                dba_entry = {
                    "_id": str(doc.get("_id", "")),
                    "analysis_id": doc.get("analysis_id", ""),
                    "host": doc.get("host", source_info.get("host", "Unknown") if isinstance(source_info, dict) else "Unknown"),
                    "timestamp": doc.get("timestamp"),
                    "anomaly_count": doc.get("anomaly_count", 0),
                    "total_logs": doc.get("logs_analyzed", 0),
                    "anomaly_rate": doc.get("anomaly_rate", 0),
                    "time_range": doc.get("time_range", source_info.get("time_range", "") if isinstance(source_info, dict) else ""),
                    "source_type": source_info.get("source_type", source_type) if isinstance(source_info, dict) else source_type,
                    "has_ai_explanation": bool(doc.get("ai_explanation")),
                    "storage_id": doc.get("analysis_id", str(doc.get("_id", "")))
                }
                dba_history.append(dba_entry)
            
            logger.info(f"✅ Retrieved {len(dba_history)} DBA analyses from last {days_back} days")
            return dba_history
            
        except Exception as e:
            logger.error(f"❌ Failed to get DBA analysis history: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
            
    async def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get storage and analysis statistics
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Statistics dictionary
        """
        try:
            # Get MongoDB statistics
            mongodb_stats = await self.mongodb.get_anomaly_statistics(days)
            
            # Calculate storage usage
            storage_stats = await self._calculate_storage_usage()
            
            # Combine statistics
            stats = {
                "analysis_stats": mongodb_stats,
                "storage_stats": storage_stats,
                "manager_stats": self.stats,
                "period_days": days
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}
    
    async def cleanup_old_data(self, force: bool = False) -> Dict[str, int]:
        """
        Clean up old data based on retention policies
        
        Args:
            force: Force cleanup even if within limits
            
        Returns:
            Cleanup statistics
        """
        try:
            cleanup_stats = {
                "files_deleted": 0,
                "space_freed_mb": 0,
                "mongodb_deleted": 0,
                "total_freed_gb": 0
            }
            
            # MongoDB boyut bazlı temizlik
            if self.mongodb and self.mongodb.is_connected:
                max_size_gb = STORAGE_LIMITS.get("max_database_size_gb", 10.0)
                deleted_count = await self.mongodb.cleanup_by_size(max_size_gb)
                cleanup_stats["mongodb_deleted"] = deleted_count
                logger.info(f"MongoDB cleanup: {deleted_count} documents deleted")
            # MongoDB cleanup is handled automatically by TTL
            
            # File system cleanup
            cutoff_date = datetime.utcnow() - timedelta(
                days=AUTO_SAVE_CONFIG.get("retention_days", 90)
            )
            
            # Clean analysis files
            analysis_dir = self.storage_paths["exports"] / "anomaly"
            if analysis_dir.exists():
                for file_path in analysis_dir.glob("*.json"):
                    file_stat = file_path.stat()
                    file_date = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if force or file_date < cutoff_date:
                        file_size_mb = file_stat.st_size / (1024 * 1024)
                        file_path.unlink()
                        cleanup_stats["files_deleted"] += 1
                        cleanup_stats["space_freed_mb"] += file_size_mb
            
            # Clean temp files
            temp_dir = self.storage_paths["temp"]
            if temp_dir.exists():
                temp_cutoff = datetime.utcnow() - timedelta(hours=6)
                for file_path in temp_dir.glob("*"):
                    file_stat = file_path.stat()
                    file_date = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if file_date < temp_cutoff:
                        file_size_mb = file_stat.st_size / (1024 * 1024)
                        file_path.unlink()
                        cleanup_stats["files_deleted"] += 1
                        cleanup_stats["space_freed_mb"] += file_size_mb
            
            logger.info(f"Cleanup completed: {cleanup_stats}")
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return {"files_deleted": 0, "space_freed_mb": 0}
    
    async def export_analysis(self, 
                             analysis_id: str,
                             format: str = "json") -> Optional[str]:
        """
        Export analysis in specified format
        
        Args:
            analysis_id: Analysis ID
            format: Export format (json, csv)
            
        Returns:
            Export file path
        """
        try:
            # Get analysis with details
            filters = {"analysis_id": analysis_id}
            analyses = await self.get_anomaly_history(
                filters=filters,
                limit=1,
                include_details=True
            )
            
            if not analyses:
                logger.warning(f"Analysis not found: {analysis_id}")
                return None
            
            analysis = analyses[0]
            
            # Export based on format
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            if format == "json":
                export_path = self.storage_paths["exports"] / f"export_{analysis_id}_{timestamp}.json"
                async with aiofiles.open(export_path, 'w') as f:
                    await f.write(json.dumps(analysis, indent=2, default=str))
                    
            elif format == "csv":
                # Export critical anomalies as CSV
                import pandas as pd
                
                export_path = self.storage_paths["exports"] / f"export_{analysis_id}_{timestamp}.csv"
                
                if "detailed_data" in analysis:
                    anomalies = analysis["detailed_data"].get("data", {}).get("critical_anomalies", [])
                    if anomalies:
                        df = pd.DataFrame(anomalies)
                        df.to_csv(export_path, index=False)
                    else:
                        logger.warning("No anomalies to export")
                        return None
            else:
                logger.error(f"Unsupported export format: {format}")
                return None
            
            logger.info(f"Analysis exported to: {export_path}")
            return str(export_path)
            
        except Exception as e:
            logger.error(f"Error exporting analysis: {e}")
            return None
    
    async def _save_analysis_file(self,
                                 analysis_id: str,
                                 analysis_result: Dict[str, Any],
                                 source_info: Dict[str, Any],
                                 model_info: Dict[str, Any] = None) -> Path:
        """Save analysis data to file system"""
        try:
            # Determine file format
            if self.auto_save_format == "json":
                file_name = f"{analysis_id}.json"
                file_path = self.storage_paths["exports"] / "anomaly" / file_name
                
                # Ensure directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save as JSON - MongoDB ile uyumlu flat yapı

                # Extract data from result format (sonuç veya data key'inden)
                sonuc = analysis_result.get("sonuç") or analysis_result.get("data") or {}

                data = {
                    "analysis_id": analysis_id,
                    "source_info": source_info,
                    "saved_at": datetime.utcnow().isoformat(),

                    # Summary information
                    "source": sonuc.get("source", "unknown"),
                    "logs_analyzed": sonuc.get("logs_analyzed", 0),
                    "filtered_logs": sonuc.get("filtered_logs", 0),
                    "summary": sonuc.get("summary", {}),

                    # Analysis results (MongoDB ile aynı)
                    "anomaly_count": sonuc.get("summary", {}).get("n_anomalies", 0),
                    "anomaly_rate": sonuc.get("summary", {}).get("anomaly_rate", 0),
                    "score_range": sonuc.get("summary", {}).get("score_range", {}),

                    # Anomalies - flat structure
                    "critical_anomalies_display": sonuc.get("critical_anomalies", [])[:100],
                    "critical_anomalies_full": sonuc.get("critical_anomalies", []),
                    "critical_count": len(sonuc.get("critical_anomalies", [])),
                    "unfiltered_anomalies": sonuc.get("unfiltered_anomalies", []),
                    "unfiltered_count": sonuc.get("unfiltered_count", 0),

                    # Alerts and analysis
                    "security_alerts": sonuc.get("security_alerts", {}),
                    "performance_alerts": sonuc.get("performance_alerts", {}),
                    "temporal_analysis": sonuc.get("temporal_analysis", {}),
                    "component_analysis": sonuc.get("component_analysis", {}),

                    # AI explanation
                    "ai_explanation": sonuc.get("ai_explanation", {}),

                    # Host and time info (flat for easy access)
                    "host": source_info.get("host") if source_info else None,
                    "time_range": source_info.get("time_range") if source_info else None,

                    #  Model metadata (MongoDB ile uyumlu yapı)
                    "model_info": {
                        "model_version": model_info.get("model_version") if model_info else None,
                        "model_path": model_info.get("model_path") if model_info else None,
                        "server_name": model_info.get("server_name") if model_info else None,
                        "is_ensemble_mode": model_info.get("is_ensemble_mode", False) if model_info else False,
                        "ensemble_model_count": model_info.get("ensemble_model_count", 0) if model_info else 0,
                        "historical_buffer_samples": model_info.get("historical_buffer_samples", 0) if model_info else 0,
                        "model_trained_at": model_info.get("model_trained_at") if model_info else None,
                        "feature_count": model_info.get("feature_count", 0) if model_info else 0,
                        "contamination": model_info.get("contamination") if model_info else None
                    } if model_info else None,

                    # Keep original for backward compatibility
                    "_original_result": analysis_result
                }
                async with aiofiles.open(file_path, 'w') as f:
                    await f.write(json.dumps(data, indent=2, default=str))
                    
            elif self.auto_save_format == "pickle":
                file_name = f"{analysis_id}.pkl"
                file_path = self.storage_paths["exports"] / "anomaly" / file_name
                
                # Ensure directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Save as pickle
                data = {
                    "analysis_id": analysis_id,
                    "source_info": source_info,
                    "result": analysis_result,
                    "saved_at": datetime.utcnow()
                }
                
                # Pickle requires sync I/O
                await asyncio.get_event_loop().run_in_executor(
                    None, 
                    joblib.dump,
                    data,
                    file_path
                )
            else:
                raise ValueError(f"Unsupported format: {self.auto_save_format}")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving analysis file: {e}")
            raise
    
    async def _load_analysis_file(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Load analysis data from file system with backward compatibility"""
        try:
            # Try JSON first
            json_path = self.storage_paths["exports"] / "anomaly" / f"{analysis_id}.json"
            if json_path.exists():
                async with aiofiles.open(json_path, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    # Normalize to flat structure for backward compatibility
                    return self._normalize_loaded_analysis(data)

            # Try pickle
            pkl_path = self.storage_paths["exports"] / "anomaly" / f"{analysis_id}.pkl"
            if pkl_path.exists():
                # Pickle requires sync I/O
                data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    joblib.load,
                    pkl_path
                )
                # Normalize to flat structure for backward compatibility
                return self._normalize_loaded_analysis(data)

            logger.warning(f"Analysis file not found: {analysis_id}")
            return None

        except Exception as e:
            logger.error(f"Error loading analysis file: {e}")
            return None

    def _normalize_loaded_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize loaded analysis data to flat structure
        Handles both old (nested) and new (flat) formats

        Args:
            data: Raw loaded data from file

        Returns:
            Normalized flat structure data
        """
        # Check if already in new flat format
        if "critical_anomalies_full" in data:
            return data

        # Old format: result.sonuç.critical_anomalies
        # Need to convert to flat format
        result = data.get("result", {})
        sonuc = result.get("sonuç") or result.get("data") or {}
        source_info = data.get("source_info", {})

        # If no sonuç found, return as-is (might be pickle or other format)
        if not sonuc:
            return data

        # Convert to flat structure (same as _save_analysis_file)
        normalized = {
            "analysis_id": data.get("analysis_id"),
            "source_info": source_info,
            "saved_at": data.get("saved_at"),

            # Summary information
            "source": sonuc.get("source", "unknown"),
            "logs_analyzed": sonuc.get("logs_analyzed", 0),
            "filtered_logs": sonuc.get("filtered_logs", 0),
            "summary": sonuc.get("summary", {}),

            # Analysis results
            "anomaly_count": sonuc.get("summary", {}).get("n_anomalies", 0),
            "anomaly_rate": sonuc.get("summary", {}).get("anomaly_rate", 0),
            "score_range": sonuc.get("summary", {}).get("score_range", {}),

            # Anomalies - flat structure
            "critical_anomalies_display": sonuc.get("critical_anomalies", [])[:100],
            "critical_anomalies_full": sonuc.get("critical_anomalies", []),
            "critical_count": len(sonuc.get("critical_anomalies", [])),
            "unfiltered_anomalies": sonuc.get("unfiltered_anomalies", []),
            "unfiltered_count": sonuc.get("unfiltered_count", 0),

            # Alerts and analysis
            "security_alerts": sonuc.get("security_alerts", {}),
            "performance_alerts": sonuc.get("performance_alerts", {}),
            "temporal_analysis": sonuc.get("temporal_analysis", {}),
            "component_analysis": sonuc.get("component_analysis", {}),

            # AI explanation
            "ai_explanation": sonuc.get("ai_explanation", {}),

            # Host and time info
            "host": source_info.get("host"),
            "time_range": source_info.get("time_range"),

            # Keep original for reference
            "_original_result": data
        }

        logger.debug(f"Normalized old format analysis: {data.get('analysis_id')}")
        return normalized

    async def _backup_model(self, model_path: Path):
        """Backup existing model file"""
        try:
            if model_path.exists():
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{model_path.stem}_backup_{timestamp}{model_path.suffix}"
                backup_path = self.storage_paths["backups"] / backup_name
                
                shutil.copy2(model_path, backup_path)
                logger.info(f"Model backed up to: {backup_path}")
                
        except Exception as e:
            logger.error(f"Error backing up model: {e}")
    async def _add_to_cache(self, analysis_id: str, analysis_result: Dict[str, Any]):
        """Add analysis to cache with size management (thread-safe)"""
        try:
            # Estimate size (rough approximation)
            estimated_size = len(json.dumps(analysis_result, default=str))

            # Check cache size limit (10 MB)
            max_cache_size = 10 * 1024 * 1024

            with self._cache_lock:
                # If adding would exceed limit, clear oldest entries
                if self._cache_size + estimated_size > max_cache_size:
                    # Clear half of cache
                    to_remove = len(self._analysis_cache) // 2
                    for key in list(self._analysis_cache.keys())[:to_remove]:
                        del self._analysis_cache[key]

                    # Recalculate cache size
                    self._cache_size = sum(
                        len(json.dumps(v, default=str))
                        for v in self._analysis_cache.values()
                    )

                # Add to cache
                self._analysis_cache[analysis_id] = analysis_result
                self._cache_size += estimated_size

        except Exception as e:
            logger.error(f"Error adding to cache: {e}")
    
    async def _flush_cache(self):
        """Flush cache to disk if needed (thread-safe snapshot)"""
        try:
            with self._cache_lock:
                cache_snapshot = dict(self._analysis_cache)
            if cache_snapshot:
                cache_file = self.storage_paths["temp"] / "analysis_cache.json"

                async with aiofiles.open(cache_file, 'w') as f:
                    await f.write(json.dumps(
                        cache_snapshot,
                        indent=2,
                        default=str
                    ))

                logger.info(f"Cache flushed to: {cache_file}")

        except Exception as e:
            logger.error(f"Error flushing cache: {e}")
    
    async def _calculate_storage_usage(self) -> Dict[str, Any]:
        """Calculate storage usage statistics"""
        try:
            stats = {
                "total_size_mb": 0,
                "models_size_mb": 0,
                "exports_size_mb": 0,
                "temp_size_mb": 0,
                "file_counts": {}
            }
            
            for name, path in self.storage_paths.items():
                if path.exists():
                    # Calculate size
                    size_bytes = sum(
                        f.stat().st_size 
                        for f in path.rglob("*") 
                        if f.is_file()
                    )
                    size_mb = size_bytes / (1024 * 1024)
                    
                    # Count files
                    file_count = sum(1 for f in path.rglob("*") if f.is_file())
                    
                    stats[f"{name}_size_mb"] = round(size_mb, 2)
                    stats["file_counts"][name] = file_count
                    stats["total_size_mb"] += size_mb
            
            stats["total_size_mb"] = round(stats["total_size_mb"], 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating storage usage: {e}")
            return {}
    
    async def check_and_cleanup_by_size(self, warning_threshold: float = 0.8) -> Dict[str, Any]:
        """
        Check storage size and cleanup if necessary
        
        Args:
            warning_threshold: Warning when usage exceeds this percentage (0.8 = 80%)
            
        Returns:
            Storage status and cleanup results
        """
        try:
            status = {
                "checked_at": datetime.utcnow().isoformat(),
                "mongodb_size_gb": 0,
                "file_size_gb": 0,
                "total_size_gb": 0,
                "limit_gb": STORAGE_LIMITS.get("max_total_size_gb", 10.0),
                "usage_percent": 0,
                "cleaned_up": False,
                "deleted_count": 0
            }
            
            # MongoDB boyutu
            if self.mongodb and self.mongodb.is_connected:
                size_info = await self.mongodb.check_database_size()
                status["mongodb_size_gb"] = size_info.get("total_size_gb", 0)
                
                # Detaylı MongoDB bilgileri
                status["mongodb_details"] = {
                    "data_size_gb": size_info.get("data_size_gb", 0),
                    "index_size_gb": size_info.get("index_size_gb", 0),
                    "collections": size_info.get("collections", 0),
                    "documents": size_info.get("objects", 0)
                }
            
            # File storage boyutu
            storage_stats = await self._calculate_storage_usage()
            status["file_size_gb"] = storage_stats.get("total_size_mb", 0) / 1024
            
            # Toplam boyut
            status["total_size_gb"] = status["mongodb_size_gb"] + status["file_size_gb"]
            status["usage_percent"] = (status["total_size_gb"] / status["limit_gb"]) * 100
            
            # Limit kontrolü
            if status["total_size_gb"] > status["limit_gb"]:
                logger.warning(f"⚠️ Storage limit exceeded: {status['total_size_gb']:.2f} GB > {status['limit_gb']} GB")
                
                # FIFO temizlik - en eski kayıtları sil
                cleanup_result = await self.cleanup_old_data(force=True)
                status["cleaned_up"] = True
                status["deleted_count"] = cleanup_result.get("mongodb_deleted", 0)
                
                # MongoDB'de agresif temizlik
                if status["mongodb_size_gb"] > status["limit_gb"] * 0.7:  # MongoDB %70'ten fazla kullanıyorsa
                    logger.warning("MongoDB using >70% of limit, aggressive cleanup...")
                    deleted = await self.mongodb.cleanup_by_size(status["limit_gb"] * 0.5)  # %50'ye düşür
                    status["deleted_count"] += deleted
                    
                logger.info(f"✅ Cleanup completed: {status['deleted_count']} items deleted")
                
            elif status["usage_percent"] > (warning_threshold * 100):
                logger.warning(f"⚠️ Storage usage high: {status['usage_percent']:.1f}%")
                
                # Soft cleanup - 30 günden eski kayıtları temizle
                if self.mongodb:
                    cutoff = datetime.utcnow() - timedelta(days=30)
                    collection = self.mongodb.db[self.mongodb.collections["anomaly_history"]]
                    result = await collection.delete_many({"timestamp": {"$lt": cutoff}})
                    status["deleted_count"] = result.deleted_count
                    logger.info(f"Soft cleanup: {result.deleted_count} old records deleted")
            else:
                logger.info(f"✅ Storage usage normal: {status['usage_percent']:.1f}%")
            
            # İstatistikleri sakla
            self.stats["last_size_check"] = status
            
            return status
            
        except Exception as e:
            logger.error(f"Error checking storage size: {e}")
            return {
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }

    async def get_storage_status(self) -> Dict[str, Any]:
        """
        Get comprehensive storage status
        
        Returns:
            Detailed storage status
        """
        try:
            # Boyut kontrolü yap
            size_status = await self.check_and_cleanup_by_size()
            
            # İstatistikleri al
            stats = await self.get_statistics(days=7)
            
            return {
                "size": size_status,
                "statistics": stats,
                "limits": {
                    "max_total_gb": STORAGE_LIMITS.get("max_total_size_gb", 10.0),
                    "max_mongodb_gb": STORAGE_LIMITS.get("max_database_size_gb", 5.0),
                    "max_file_gb": STORAGE_LIMITS.get("max_file_size_gb", 5.0),
                    "retention_days": AUTO_SAVE_CONFIG.get("retention_days", 90)
                },
                "health": {
                    "mongodb_connected": self.mongodb.is_connected if self.mongodb else False,
                    "auto_save_enabled": self.auto_save_enabled,
                    "last_cleanup": self.stats.get("last_cleanup"),
                    "cache_size": len(self._analysis_cache)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting storage status: {e}")
            return {"error": str(e)}
    
    def _normalize_analysis_result(self, analysis_result: Any, source_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure analysis_result is a dict with a stable shape:
        {
          "durum": "...",
          "işlem": "...",
          "açıklama": "...",
          "sonuç": {
              "summary": {...},
              "critical_anomalies": [...],
              ...
          },
          "ai_explanation": {...} (opsiyonel),
          "suggestions": [...]
        }
        """
        # 1) parse string to dict if needed
        if isinstance(analysis_result, str):
            try:
                analysis_result = json.loads(analysis_result)
            except Exception:
                # wrap raw string
                analysis_result = {
                    "durum": "tamamlandı",
                    "işlem": "anomaly_analysis",
                    "açıklama": "Raw string result wrapped by normalizer",
                    "sonuç": {"raw_result": analysis_result}
                }

        # 2) ensure we have a dict
        if not isinstance(analysis_result, dict):
            analysis_result = {
                "durum": "tamamlandı",
                "işlem": "anomaly_analysis",
                "açıklama": "Non-dict result wrapped by normalizer",
                "sonuç": {"raw_result": str(analysis_result)}
            }

        # 3) prefer "sonuç", fallback to "data"
        if "sonuç" not in analysis_result:
            if "data" in analysis_result and isinstance(analysis_result["data"], dict):
                analysis_result["sonuç"] = analysis_result["data"]
            else:
                analysis_result.setdefault("sonuç", {})

        data = analysis_result["sonuç"]
        if not isinstance(data, dict):
            data = {"raw_data": data}
            analysis_result["sonuç"] = data

        # 4) ensure summary exists with minimal fields
        summary = data.get("summary") or {}
        if not isinstance(summary, dict):
            summary = {}
        # fill minimal safe fields
        summary.setdefault("total_logs", data.get("logs_analyzed") or data.get("filtered_logs") or 0)
        # anomaly count fallback
        try:
            ca = data.get("critical_anomalies") or []
            if isinstance(ca, list):
                summary.setdefault("n_anomalies", len(ca))
        except Exception:
            summary.setdefault("n_anomalies", 0)
        # anomaly rate fallback (best-effort)
        if "anomaly_rate" not in summary:
            tl = summary.get("total_logs") or 0
            na = summary.get("n_anomalies") or 0
            summary["anomaly_rate"] = round((na / tl * 100), 3) if tl else 0.0

        # attach back
        data["summary"] = summary

        # 5) attach source hints (useful for querying later)
        data.setdefault("source", {})
        if isinstance(data["source"], dict):
            data["source"].setdefault("type", source_info.get("source_type"))
            data["source"].setdefault("host", source_info.get("host"))
            data["source"].setdefault("time_range", source_info.get("time_range"))

        return analysis_result

    async def save_uploaded_log(self, file_object, filename: str) -> str:
        """
        Upload edilen log dosyasını kalıcı storage'a kaydet (FIFO kontrollü)
        
        Args:
            file_object: FastAPI UploadFile.file objesi
            filename: Kaydedilecek dosya adı
            
        Returns:
            Kaydedilen dosyanın tam yolu
        """
        try:
            upload_dir = self.storage_paths["uploads"]
            target_path = upload_dir / filename
            
            # 1. FIFO: Limit kontrolü yap ve gerekirse yer aç
            await self._enforce_upload_storage_limit()
            
            # 2. Dosyayı kaydet
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file_object, buffer)
                
            logger.info(f"✅ Log file saved to permanent storage: {target_path}")
            
            # Dosya boyutunu logla
            size_mb = target_path.stat().st_size / (1024 * 1024)
            logger.info(f"   Size: {size_mb:.2f} MB")
            
            return str(target_path)
            
        except Exception as e:
            logger.error(f"❌ Error saving uploaded log: {e}")
            raise

    async def _enforce_upload_storage_limit(self):
        """
        Upload klasörü boyut limitini FIFO (First-In-First-Out) mantığıyla koru
        """
        try:
            upload_dir = self.storage_paths["uploads"]
            # Config'den limiti al (GB -> Byte çevir)
            max_size_gb = STORAGE_LIMITS.get("max_upload_size_gb", 5.0)
            max_size_bytes = max_size_gb * 1024 * 1024 * 1024
            
            # Mevcut dosyaları listele
            files = list(upload_dir.glob("*"))
            if not files:
                return

            # Mevcut boyutu hesapla
            current_size = sum(f.stat().st_size for f in files if f.is_file())
            
            # Eğer limit aşıldıysa temizlik yap
            if current_size >= max_size_bytes:
                logger.warning(f"⚠️ Upload storage limit exceeded: {current_size / (1024**3):.2f} GB / {max_size_gb} GB")
                logger.info("🧹 Starting FIFO cleanup for uploads...")
                
                # Dosyaları değiştirilme tarihine göre sırala (En eski en başta)
                files.sort(key=lambda x: x.stat().st_mtime)
                
                deleted_count = 0
                freed_bytes = 0
                
                for f in files:
                    # Yeterince yer açıldı mı? (Güvenlik payı olarak %10 altına inene kadar sil)
                    if current_size < (max_size_bytes * 0.9):
                        break
                    
                    try:
                        file_size = f.stat().st_size
                        f.unlink()
                        current_size -= file_size
                        freed_bytes += file_size
                        deleted_count += 1
                        logger.debug(f"Deleted old upload: {f.name}")
                    except Exception as del_err:
                        logger.error(f"Failed to delete {f.name}: {del_err}")
                
                logger.info(f"✅ FIFO Cleanup complete: {deleted_count} files deleted, {freed_bytes / (1024**2):.2f} MB freed")
                
        except Exception as e:
            logger.error(f"Error enforcing upload limits: {e}")

    # ──────────────────────────────────────────────
    # Prediction & Early Warning Storage Delegation
    # ──────────────────────────────────────────────

    async def save_prediction_alert(self, alert_data: Dict[str, Any],
                                    alert_source: str = "trend",
                                    server_name: str = None,
                                    retention_days: int = 90,
                                    source_type: str = None) -> Optional[str]:
        """Delegate to MongoDBHandler"""
        return await self.mongodb.save_prediction_alert(
            alert_data, alert_source, server_name, retention_days,
            source_type=source_type
        )

    async def get_prediction_alerts(self, server_name: str = None,
                                    alert_source: str = None,
                                    only_with_alerts: bool = False,
                                    limit: int = 50,
                                    days: int = 7,
                                    source_type: str = None) -> List[Dict[str, Any]]:
        """Delegate to MongoDBHandler"""
        return await self.mongodb.get_prediction_alerts(
            server_name, alert_source, only_with_alerts, limit, days,
            source_type=source_type
        )

    async def get_prediction_summary(self, server_name: str = None,
                                     days: int = 7,
                                     source_type: str = None) -> Dict[str, Any]:
        """Delegate to MongoDBHandler"""
        return await self.mongodb.get_prediction_summary(
            server_name, days, source_type=source_type
        )

    async def get_prediction_timeseries(self, server_name: str = None,
                                        alert_source: str = None,
                                        days: int = 7,
                                        source_type: str = None) -> Dict[str, Any]:
        """Delegate to MongoDBHandler"""
        return await self.mongodb.get_prediction_timeseries(
            server_name, alert_source, days, source_type=source_type
        )

    async def get_prediction_server_overview(self, source_type: str = None,
                                              days: int = 7) -> List[Dict[str, Any]]:
        """Delegate to MongoDBHandler — sunucu bazlı prediction risk özeti"""
        return await self.mongodb.get_prediction_server_overview(source_type, days)

    async def get_prediction_latest_context(self, server_name: str = None,
                                             source_type: str = None) -> Dict[str, Any]:
        """Delegate to MongoDBHandler — son prediction bağlamı"""
        return await self.mongodb.get_prediction_latest_context(server_name, source_type)