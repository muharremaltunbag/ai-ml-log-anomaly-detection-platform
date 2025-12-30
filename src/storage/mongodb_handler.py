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
        # Query history collection ekleniyor
        if "query_history" not in self.collections:
            self.collections["query_history"] = "query_history"
        if "user_preferences" not in self.collections:
            self.collections["user_preferences"] = "user_preferences"
        
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
            
            # Query history indexes
            query_collection = self.db[self.collections.get("query_history", "query_history")]
            await query_collection.create_index([("timestamp", DESCENDING)])
            await query_collection.create_index([("user_id", ASCENDING)])
            await query_collection.create_index([("query_type", ASCENDING)])
            await query_collection.create_index([("session_id", ASCENDING)])

            # User preferences indexes
            prefs_collection = self.db[self.collections.get("user_preferences", "user_preferences")]
            await prefs_collection.create_index([("user_id", ASCENDING)])
            
            logger.debug("MongoDB indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    async def save_anomaly_result(self, analysis_result: Dict[str, Any], 
                                  source_info: Dict[str, Any] = None,
                                  model_info: Dict[str, Any] = None) -> str:
        """
        Save anomaly analysis result to MongoDB
        Compatible with anomaly_tools.analyze_mongodb_logs() output

        Args:
            analysis_result: Result from analyze_mongodb_logs
            source_info: Additional source metadata
            model_info: Model metadata (version, path, ensemble info, etc.)

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
                
                # Store both filtered and unfiltered anomalies
                "critical_anomalies_display": data.get("critical_anomalies", [])[:100],  # UI için ilk 100
                "critical_anomalies_full": data.get("critical_anomalies", []),  # Filtrelenmiş TÜM anomaliler
                "critical_count": len(data.get("critical_anomalies", [])),
                "unfiltered_anomalies": data.get("unfiltered_anomalies", []),  # Filtrelenmemiş TÜM anomaliler
                "unfiltered_count": data.get("unfiltered_count", 0),
                
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

                # Model metadata
                "model_metadata": {
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
                # Metadata
                "created_at": datetime.utcnow(),
                "ttl_date": datetime.utcnow() + timedelta(days=RETENTION_POLICY["anomaly_history_days"])
            }
            # Insert to MongoDB
            collection = self.db[self.collections["anomaly_history"]]

            # [SAFETY] MongoDB 16MB limit koruması.
            # Döküman çok büyükse veriyi bozmadan en kritik kısımları koru.
            if len(document.get("unfiltered_anomalies", [])) > 10000:
                logger.warning(f"Analysis {analysis_id} is too large. Truncating for MongoDB safety.")
                document["unfiltered_anomalies"] = document["unfiltered_anomalies"][:10000]
                document["is_truncated_in_db"] = True

            result = await collection.insert_one(document)
            logger.info(f"Anomaly result saved with ID: {analysis_id}")

            # [STABILITY] Temizlik işlemini arka plana at.
            # Kullanıcı temizliğin bitmesini beklemeden hemen cevabını alsın.
            asyncio.create_task(self._cleanup_old_anomalies())

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

                # Analysis ID filter (exact match)
                if "analysis_id" in filters:
                    query["analysis_id"] = filters["analysis_id"]

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

    async def save_query_history(self, query_item: Dict[str, Any]) -> str:
        """
        Save user query to history
        
        Args:
            query_item: Query data including query, result, type, etc.
            
        Returns:
            Query ID
        """
        try:
            collection = self.db[self.collections.get("query_history", "query_history")]
            
            # Generate unique query ID
            query_id = f"query_{hashlib.md5(str(datetime.utcnow().timestamp()).encode()).hexdigest()[:12]}"
            
            # Build document
            document = {
                "query_id": query_id,
                "timestamp": datetime.utcnow(),
                "query": query_item.get("query", ""),
                "query_type": query_item.get("type", "chatbot"),
                "category": query_item.get("category", "chatbot"),
                "result": query_item.get("result", {}),
                "durum": query_item.get("durum", "tamamlandı"),
                "işlem": query_item.get("işlem", ""),
                "user_id": query_item.get("user_id"),
                "session_id": query_item.get("session_id"),
                "execution_time": query_item.get("executionTime"),
                "has_visualization": query_item.get("hasVisualization", False),
                "storage_id": query_item.get("storage_id"),
                "ttl_date": datetime.utcnow() + timedelta(days=90)
            }
            
            # ML data varsa ekle
            if "mlData" in query_item:
                document["ml_data"] = query_item["mlData"]
            if "aiExplanation" in query_item:
                document["ai_explanation"] = query_item["aiExplanation"]
            
            # Insert to MongoDB
            await collection.insert_one(document)
            logger.info(f"Query saved with ID: {query_id}")
            
            return query_id
            
        except Exception as e:
            logger.error(f"Error saving query history: {e}")
            return ""

    async def get_query_history(self, user_id: str = None, session_id: str = None, 
                               limit: int = 50, query_type: str = None) -> List[Dict[str, Any]]:
        """
        Get user query history
        
        Args:
            user_id: Optional user ID filter
            session_id: Optional session ID filter
            limit: Maximum results
            query_type: Filter by query type (chatbot/anomaly)
            
        Returns:
            List of query history items
        """
        try:
            collection = self.db[self.collections.get("query_history", "query_history")]
            
            # Build query
            query = {}
            if user_id:
                query["user_id"] = user_id
            if session_id:
                query["session_id"] = session_id
            if query_type:
                query["query_type"] = query_type
            
            # Execute query
            cursor = collection.find(query).sort("timestamp", DESCENDING).limit(limit)
            
            results = []
            async for document in cursor:
                document["_id"] = str(document["_id"])
                results.append(document)
            
            logger.info(f"Retrieved {len(results)} query history items")
            return results
            
        except Exception as e:
            logger.error(f"Error retrieving query history: {e}")
            return []

    async def get_query_by_id(self, query_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific query by its ID
        
        Args:
            query_id: Unique query ID
            
        Returns:
            Query document or None if not found
        """
        try:
            collection = self.db[self.collections.get("query_history", "query_history")]
            
            # Query ID ile ara
            document = await collection.find_one({"query_id": query_id})
            
            if document:
                # ObjectId'yi string'e çevir
                document["_id"] = str(document["_id"])
                logger.debug(f"Found query: {query_id}")
                return document
            
            logger.debug(f"Query not found: {query_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting query by ID: {e}")
            return None

    async def delete_query_history_item(self, query_id: str) -> bool:
        """
        Delete a specific query from history
        
        Args:
            query_id: Query ID to delete
            
        Returns:
            Success status
        """
        try:
            collection = self.db[self.collections.get("query_history", "query_history")]
            result = await collection.delete_one({"query_id": query_id})
            
            if result.deleted_count > 0:
                logger.info(f"Query {query_id} deleted")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deleting query: {e}")
            return False

    async def check_database_size(self) -> Dict[str, float]:
        """
        Check MongoDB database size
        
        Returns:
            Dictionary with size information in GB
        """
        try:
            # Get database stats
            stats = await self.db.command("dbStats")
            
            size_info = {
                "data_size_gb": stats.get("dataSize", 0) / (1024**3),
                "storage_size_gb": stats.get("storageSize", 0) / (1024**3),
                "index_size_gb": stats.get("indexSize", 0) / (1024**3),
                "total_size_gb": (stats.get("dataSize", 0) + stats.get("indexSize", 0)) / (1024**3),
                "collections": stats.get("collections", 0),
                "objects": stats.get("objects", 0)
            }
            
            logger.info(f"Database size: {size_info['total_size_gb']:.2f} GB")
            return size_info
            
        except Exception as e:
            logger.error(f"Error checking database size: {e}")
            return {}

    async def cleanup_by_size(self, max_size_gb: float = 10.0) -> int:
        """
        Clean up old data if database exceeds size limit
        
        Args:
            max_size_gb: Maximum database size in GB
            
        Returns:
            Number of deleted documents
        """
        try:
            size_info = await self.check_database_size()
            current_size = size_info.get("total_size_gb", 0)
            
            if current_size > max_size_gb:
                logger.warning(f"Database size ({current_size:.2f} GB) exceeds limit ({max_size_gb} GB)")
                
                # Delete oldest records first (FIFO)
                deleted_count = 0
                
                # Start with query history (least important)
                query_collection = self.db[self.collections.get("query_history", "query_history")]
                
                # Delete oldest 20%
                total_queries = await query_collection.count_documents({})
                to_delete = int(total_queries * 0.2)
                
                if to_delete > 0:
                    # Get oldest documents
                    oldest = await query_collection.find({}).sort("timestamp", ASCENDING).limit(to_delete).to_list(to_delete)
                    ids_to_delete = [doc["_id"] for doc in oldest]
                    
                    result = await query_collection.delete_many({"_id": {"$in": ids_to_delete}})
                    deleted_count += result.deleted_count
                    logger.info(f"Deleted {result.deleted_count} old query history items")
                
                # If still over limit, delete old anomaly records
                if current_size - (deleted_count * 0.001) > max_size_gb:  # Rough estimate
                    anomaly_collection = self.db[self.collections["anomaly_history"]]
                    
                    # Delete records older than 30 days
                    cutoff = datetime.utcnow() - timedelta(days=30)
                    result = await anomaly_collection.delete_many({"timestamp": {"$lt": cutoff}})
                    deleted_count += result.deleted_count
                    logger.info(f"Deleted {result.deleted_count} old anomaly records")
                
                return deleted_count
            
            logger.info(f"Database size ({current_size:.2f} GB) is within limit")
            return 0
            
        except Exception as e:
            logger.error(f"Error during size-based cleanup: {e}")
            return 0

    async def clear_all_analysis_history(self) -> int:
        """
        Clear ALL anomaly and DBA analysis history.
        Used when user explicitly requests 'Clear History'.
        
        Returns:
            Number of deleted documents
        """
        try:
            # anomaly_history koleksiyonunu hedefle
            collection = self.db[self.collections["anomaly_history"]]
            
            # Filtre vermeden delete_many çağırarak hepsini sil
            result = await collection.delete_many({})
            
            if result.deleted_count > 0:
                logger.info(f"🗑️ Explicitly cleared {result.deleted_count} anomaly/DBA history records")
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing analysis history: {e}")
            return 0

    async def clear_all_query_history(self) -> int:
        """
        Clear ALL chat/query history globally (Truncate collection).
        """
        try:
            collection = self.db[self.collections.get("query_history", "query_history")]
            # Filtre olmadan hepsini sil
            result = await collection.delete_many({})
            
            if result.deleted_count > 0:
                logger.info(f"🗑️ Explicitly cleared {result.deleted_count} chat query records")
            
            return result.deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing query history: {e}")
            return 0