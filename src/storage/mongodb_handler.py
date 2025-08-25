# MongoDB-LLM-assistant\src\storage\mongodb_handler.py
"""
MongoDB Handler for Anomaly Detection Storage
Async MongoDB operations for storing anomaly results and model metadata
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import hashlib

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
import pandas as pd

from .config import MONGODB_CONFIG, RETENTION_POLICY

logger = logging.getLogger(__name__)


class MongoDBHandler:
    """
    MongoDB handler for anomaly detection storage
    Manages anomaly history, model registry, and feedback
    """
    
    def __init__(self, connection_string: str = None, database: str = None):
        """
        Initialize MongoDB handler
        
        Args:
            connection_string: MongoDB connection URI
            database: Database name
        """
        self.connection_string = connection_string or MONGODB_CONFIG["connection_string"]
        self.database_name = database or MONGODB_CONFIG["database"]
        self.collections = MONGODB_CONFIG["collections"]
        
        self.client = None
        self.db = None
        self._connected = False
        
        logger.info(f"MongoDB handler initialized for database: {self.database_name}")
    
    async def connect(self) -> bool:
        """
        Establish async connection to MongoDB
        
        Returns:
            Connection success status
        """
        try:
            # Create async client
            self.client = AsyncIOMotorClient(
                self.connection_string,
                **MONGODB_CONFIG["options"]
            )
            
            # Get database
            self.db = self.client[self.database_name]
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._create_indexes()
            
            self._connected = True
            logger.info("Successfully connected to MongoDB")
            return True
            
        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error during MongoDB connection: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("MongoDB connection closed")
    
    async def _create_indexes(self):
        """Create necessary indexes for optimal performance"""
        try:
            # Anomaly history indexes
            anomaly_collection = self.db[self.collections["anomaly_history"]]
            await anomaly_collection.create_index([("timestamp", DESCENDING)])
            await anomaly_collection.create_index([("analysis_id", ASCENDING)])
            await anomaly_collection.create_index([("severity_score", DESCENDING)])
            await anomaly_collection.create_index([("host", ASCENDING)])
            await anomaly_collection.create_index([
                ("timestamp", DESCENDING),
                ("severity_score", DESCENDING)
            ])
            
            # Model registry indexes
            model_collection = self.db[self.collections["model_registry"]]
            await model_collection.create_index([("version", DESCENDING)])
            await model_collection.create_index([("created_at", DESCENDING)])
            await model_collection.create_index([("is_active", ASCENDING)])
            
            logger.debug("MongoDB indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    async def save_anomaly_result(self, analysis_result: Dict[str, Any], 
                                 source_info: Dict[str, Any] = None) -> str:
        """
        Save anomaly analysis result to MongoDB
        Compatible with anomaly_tools.analyze_mongodb_logs() output
        
        Args:
            analysis_result: Result from analyze_mongodb_logs
            source_info: Additional source metadata
            
        Returns:
            Analysis ID
        """
        try:
            # Generate unique analysis ID
            analysis_id = self._generate_analysis_id()
            

            # Extract data from result format - try both "sonuç" and "data" keys
            data = analysis_result.get("sonuç") or analysis_result.get("data") or {}
            
            # Build document
            document = {
                "analysis_id": analysis_id,
                "timestamp": datetime.utcnow(),
                
                # Summary information
                "summary": data.get("summary", {}),
                "source": data.get("source", "unknown"),
                "logs_analyzed": data.get("logs_analyzed", 0),
                "filtered_logs": data.get("filtered_logs", 0),
                
                # Analysis results
                "anomaly_count": data.get("summary", {}).get("n_anomalies", 0),
                "anomaly_rate": data.get("summary", {}).get("anomaly_rate", 0),
                "score_range": data.get("summary", {}).get("score_range", {}),
                
                # Critical anomalies (store only top N for storage efficiency)
                "critical_anomalies": data.get("critical_anomalies", [])[:100],
                "critical_count": len(data.get("critical_anomalies", [])),
                
                # Alerts and analysis
                "security_alerts": data.get("security_alerts", {}),
                "performance_alerts": data.get("performance_alerts", {}),
                "temporal_analysis": data.get("temporal_analysis", {}),
                "component_analysis": data.get("component_analysis", {}),
                "severity_distribution": data.get("severity_distribution", {}),
                
                # AI explanation if available
                "ai_explanation": analysis_result.get("ai_explanation", {}),
                "suggestions": analysis_result.get("suggestions", []),
                
                # Source metadata
                "source_info": source_info or {},
                "host": source_info.get("host") if source_info else None,
                "time_range": source_info.get("time_range") if source_info else None,
                
                # Metadata
                "created_at": datetime.utcnow(),
                "ttl_date": datetime.utcnow() + timedelta(days=RETENTION_POLICY["anomaly_history_days"])
            }
            
            # Insert to MongoDB
            collection = self.db[self.collections["anomaly_history"]]
            result = await collection.insert_one(document)
            
            logger.info(f"Anomaly result saved with ID: {analysis_id}")
            
            # Check and cleanup old records
            await self._cleanup_old_anomalies()
            
            return analysis_id
            
        except Exception as e:
            logger.error(f"Error saving anomaly result: {e}")
            raise
    
    async def save_model_metadata(self, model_info: Dict[str, Any], 
                                 model_path: str, performance_metrics: Dict[str, Any] = None) -> str:
        """
        Save model metadata to registry
        Compatible with anomaly_detector.save_model()
        
        Args:
            model_info: Model information from detector.get_model_info()
            model_path: Path to saved model file
            performance_metrics: Optional performance metrics
            
        Returns:
            Model version ID
        """
        try:
            # Generate version ID
            version_id = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            # Get file stats
            model_file = Path(model_path)
            file_size_mb = model_file.stat().st_size / (1024 * 1024) if model_file.exists() else 0
            
            # Build document
            document = {
                "version": version_id,
                "model_type": model_info.get("model_type", "IsolationForest"),
                "parameters": model_info.get("parameters", {}),
                
                # Training information
                "training_stats": model_info.get("training_stats", {}),
                "feature_names": model_info.get("feature_names", []),
                "n_features": model_info.get("n_features", 0),
                
                # File information
                "model_path": str(model_path),
                "file_size_mb": round(file_size_mb, 2),
                "file_hash": self._calculate_file_hash(model_path),
                
                # Performance metrics
                "performance_metrics": performance_metrics or {},
                
                # Online learning info if available
                "has_historical_buffer": "training_stats" in model_info and 
                                       model_info["training_stats"].get("buffer_version") is not None,
                
                # Status
                "is_active": False,  # Will be set to True when deployed
                "created_at": datetime.utcnow(),
                "deployed_at": None,
                "retired_at": None
            }
            
            # Insert to MongoDB
            collection = self.db[self.collections["model_registry"]]
            result = await collection.insert_one(document)
            
            logger.info(f"Model metadata saved with version: {version_id}")
            
            # Keep only last N model versions
            await self._cleanup_old_models()
            
            return version_id
            
        except Exception as e:
            logger.error(f"Error saving model metadata: {e}")
            raise
    
    async def get_anomaly_history(self, filters: Dict[str, Any] = None, 
                                 limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Retrieve anomaly history with filters
        
        Args:
            filters: Query filters (time_range, host, severity, etc.)
            limit: Maximum results
            skip: Skip for pagination
            
        Returns:
            List of anomaly results
        """
        try:
            collection = self.db[self.collections["anomaly_history"]]
            
            # Build query
            query = {}
            
            if filters:
                # Time range filter
                if "start_date" in filters or "end_date" in filters:
                    date_filter = {}
                    if "start_date" in filters:
                        date_filter["$gte"] = filters["start_date"]
                    if "end_date" in filters:
                        date_filter["$lte"] = filters["end_date"]
                    query["timestamp"] = date_filter
                
                # Host filter
                if "host" in filters:
                    query["host"] = filters["host"]
                
                # Severity filter
                if "min_severity" in filters:
                    query["summary.anomaly_rate"] = {"$gte": filters["min_severity"]}
                
                # Source filter
                if "source" in filters:
                    query["source"] = filters["source"]
            
            # Execute query
            cursor = collection.find(query).sort("timestamp", DESCENDING).skip(skip).limit(limit)
            
            results = []
            async for document in cursor:
                # Convert ObjectId to string
                document["_id"] = str(document["_id"])
                results.append(document)
            
            logger.debug(f"Retrieved {len(results)} anomaly records")
            return results
            
        except Exception as e:
            logger.error(f"Error retrieving anomaly history: {e}")
            return []
    
    async def get_anomaly_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get anomaly statistics for dashboard
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Statistics dictionary
        """
        try:
            collection = self.db[self.collections["anomaly_history"]]
            
            # Date filter
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Aggregation pipeline
            pipeline = [
                {"$match": {"timestamp": {"$gte": start_date}}},
                {"$group": {
                    "_id": None,
                    "total_analyses": {"$sum": 1},
                    "total_anomalies": {"$sum": "$anomaly_count"},
                    "total_logs_analyzed": {"$sum": "$logs_analyzed"},
                    "avg_anomaly_rate": {"$avg": "$anomaly_rate"},
                    "max_anomaly_rate": {"$max": "$anomaly_rate"},
                    "hosts": {"$addToSet": "$host"},
                    "sources": {"$addToSet": "$source"}
                }},
                {"$project": {
                    "_id": 0,
                    "total_analyses": 1,
                    "total_anomalies": 1,
                    "total_logs_analyzed": 1,
                    "avg_anomaly_rate": {"$round": ["$avg_anomaly_rate", 2]},
                    "max_anomaly_rate": {"$round": ["$max_anomaly_rate", 2]},
                    "unique_hosts": {"$size": "$hosts"},
                    "unique_sources": {"$size": "$sources"}
                }}
            ]
            
            cursor = collection.aggregate(pipeline)
            stats = await cursor.to_list(length=1)
            
            if stats:
                return stats[0]
            else:
                return {
                    "total_analyses": 0,
                    "total_anomalies": 0,
                    "total_logs_analyzed": 0,
                    "avg_anomaly_rate": 0,
                    "max_anomaly_rate": 0,
                    "unique_hosts": 0,
                    "unique_sources": 0
                }
                
        except Exception as e:
            logger.error(f"Error getting anomaly statistics: {e}")
            return {}
    
    async def get_model_registry(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get model registry
        
        Args:
            active_only: Return only active models
            
        Returns:
            List of model metadata
        """
        try:
            collection = self.db[self.collections["model_registry"]]
            
            query = {"is_active": True} if active_only else {}
            
            cursor = collection.find(query).sort("created_at", DESCENDING)
            
            models = []
            async for document in cursor:
                document["_id"] = str(document["_id"])
                models.append(document)
            
            logger.debug(f"Retrieved {len(models)} models from registry")
            return models
            
        except Exception as e:
            logger.error(f"Error retrieving model registry: {e}")
            return []
    
    async def set_active_model(self, version_id: str) -> bool:
        """
        Set a model as active (deploy)
        
        Args:
            version_id: Model version ID
            
        Returns:
            Success status
        """
        try:
            collection = self.db[self.collections["model_registry"]]
            
            # Deactivate all models
            await collection.update_many(
                {"is_active": True},
                {"$set": {"is_active": False, "retired_at": datetime.utcnow()}}
            )
            
            # Activate specified model
            result = await collection.update_one(
                {"version": version_id},
                {"$set": {"is_active": True, "deployed_at": datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Model {version_id} set as active")
                return True
            else:
                logger.warning(f"Model {version_id} not found")
                return False
                
        except Exception as e:
            logger.error(f"Error setting active model: {e}")
            return False
    
    async def save_user_feedback(self, analysis_id: str, feedback: Dict[str, Any]) -> bool:
        """
        Save user feedback for an analysis
        
        Args:
            analysis_id: Analysis ID
            feedback: User feedback data
            
        Returns:
            Success status
        """
        try:
            collection = self.db[self.collections["user_feedback"]]
            
            document = {
                "analysis_id": analysis_id,
                "feedback": feedback,
                "timestamp": datetime.utcnow()
            }
            
            await collection.insert_one(document)
            logger.info(f"Feedback saved for analysis: {analysis_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
            return False
    
    async def _cleanup_old_anomalies(self):
        """Remove anomaly records older than retention period"""
        try:
            collection = self.db[self.collections["anomaly_history"]]
            
            cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_POLICY["anomaly_history_days"])
            
            result = await collection.delete_many({"timestamp": {"$lt": cutoff_date}})
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} old anomaly records")
                
        except Exception as e:
            logger.error(f"Error during anomaly cleanup: {e}")
    
    async def _cleanup_old_models(self):
        """Keep only last N model versions"""
        try:
            collection = self.db[self.collections["model_registry"]]
            
            # Get all models sorted by creation date
            cursor = collection.find({}).sort("created_at", DESCENDING)
            models = await cursor.to_list(length=None)
            
            max_versions = RETENTION_POLICY["model_versions_count"]
            
            if len(models) > max_versions:
                # Delete old inactive models
                for model in models[max_versions:]:
                    if not model.get("is_active", False):
                        await collection.delete_one({"_id": model["_id"]})
                        logger.debug(f"Deleted old model version: {model['version']}")
                        
        except Exception as e:
            logger.error(f"Error during model cleanup: {e}")
    
    def _generate_analysis_id(self) -> str:
        """Generate unique analysis ID"""
        timestamp = datetime.utcnow().isoformat()
        return f"analysis_{hashlib.md5(timestamp.encode()).hexdigest()[:12]}"
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate file hash for integrity check"""
        try:
            file_path = Path(file_path)
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    return hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
        return "unknown"
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MongoDB"""
        return self._connected

    @property
    def database(self):
        """
        Getter for compatibility (returns self.db)
        Needed by external components expecting 'database' attribute
        """
        return self.db