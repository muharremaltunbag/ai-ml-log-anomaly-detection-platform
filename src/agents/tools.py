from typing import Dict, Any, List, Optional
from langchain.tools import Tool
from pydantic import BaseModel, Field  # pydantic_v1 yerine pydantic
from ..connectors.mongodb_connector import MongoDBConnector
from .schema_analyzer import SchemaAnalyzer
from .query_validator import QueryValidator
from bson import ObjectId
from datetime import datetime
from decimal import Decimal
import json
import logging

logger = logging.getLogger(__name__)

def mongo_json_encoder(obj):
    """MongoDB tiplerini JSON uyumlu hale getir"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# MongoDB işlem fonksiyonları
def execute_query(
    db_connector: MongoDBConnector,
    validator: QueryValidator,
    collection: str,
    query: Dict,
    operation: str,
    options: Dict
) -> str:
    """MongoDB sorgusunu çalıştır"""
    try:
        # Sorguyu validate et
        is_valid, message = validator.validate_query(query, operation, collection)
        if not is_valid:
            return f"Güvenlik hatası: {message}"
        
        # Database bağlantısını kontrol et
        if not db_connector.is_connected():
            return "Veritabanı bağlantısı yok"
        
        # Koleksiyonu al
        collection_obj = db_connector.database[collection]
        
        # İşlemi çalıştır
        if operation == "find":
            limit = options.get("limit", 100)
            sort = options.get("sort", None)
            projection = options.get("projection", None)
            
            cursor = collection_obj.find(query, projection)
            if sort:
                cursor = cursor.sort(list(sort.items()))
            cursor = cursor.limit(limit)
            
            results = list(cursor)
            return json.dumps({
                "success": True,
                "count": len(results),
                "data": results
            }, default=mongo_json_encoder, ensure_ascii=False, indent=2)
            
        elif operation == "findOne":
            result = collection_obj.find_one(query, options.get("projection"))
            return json.dumps({
                "success": True,
                "data": result
            }, default=mongo_json_encoder, ensure_ascii=False, indent=2)
            
        elif operation == "countDocuments":
            count = collection_obj.count_documents(query)
            return json.dumps({
                "success": True,
                "count": count
            }, default=mongo_json_encoder, ensure_ascii=False)
            
        elif operation == "aggregate":
            # Query aggregate pipeline olmalı
            if not isinstance(query, list):
                # Eğer query dict ise ve içinde pipeline varsa, onu kullan
                if isinstance(query, dict) and "pipeline" in query:
                    query = query["pipeline"]
                else:
                    return "Aggregate için pipeline (list) gerekli"
            
            results = list(collection_obj.aggregate(query))
            return json.dumps({
                "success": True,
                "count": len(results),
                "data": results
            }, default=mongo_json_encoder, ensure_ascii=False, indent=2)
            
        else:
            return f"Desteklenmeyen operasyon: {operation}"
            
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return f"Hata: {str(e)}"

def view_schema(
    db_connector: MongoDBConnector,
    analyzer: SchemaAnalyzer,
    collection: Optional[str],
    detailed: bool
) -> str:
    """Koleksiyon şemasını görüntüle"""
    try:
        if not db_connector.is_connected():
            return "Veritabanı bağlantısı yok"
        
        # Analyzer'a database bağlantısını ver
        analyzer.set_database(db_connector.database)
        
        # Tek koleksiyon mu yoksa tümü mü?
        if collection:
            # Detaylı analiz isteniyorsa advanced metodu kullan
            if detailed:
                schema_info = analyzer.analyze_collection_schema_advanced(collection)
            else:
                schema_info = analyzer.analyze_collection_schema(collection)
            
            return json.dumps(schema_info, default=mongo_json_encoder, ensure_ascii=False, indent=2)
        else:
            # Tüm koleksiyonları listele
            collections = analyzer.get_available_collections()
            schemas = {}
            
            for coll in collections[:10]:  # İlk 10 koleksiyon
                schemas[coll] = {
                    "document_count": db_connector.database[coll].count_documents({}),
                    "sample_fields": list(
                        db_connector.database[coll].find_one() or {}
                    ).keys()[:10]
                }
            
            return json.dumps({
                "total_collections": len(collections),
                "showing": len(schemas),
                "collections": schemas
            }, default=mongo_json_encoder, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Schema view error: {e}")
        return f"Hata: {str(e)}"

def manage_indexes(
    db_connector: MongoDBConnector,
    collection: str,
    action: str,
    index_spec: Optional[Dict]
) -> str:
    """Index işlemlerini yönet"""
    try:
        if not db_connector.is_connected():
            return "Veritabanı bağlantısı yok"
        
        collection_obj = db_connector.database[collection]
        
        if action == "list":
            indexes = []
            for index in collection_obj.list_indexes():
                indexes.append({
                    "name": index.get("name"),
                    "keys": index.get("key"),
                    "unique": index.get("unique", False),
                    "sparse": index.get("sparse", False)
                })
            
            return json.dumps({
                "success": True,
                "collection": collection,
                "indexes": indexes
            }, default=mongo_json_encoder, ensure_ascii=False, indent=2)
            
        elif action == "create":
            if not index_spec:
                return "Index tanımı gerekli"
            
            # Index oluştur
            index_name = collection_obj.create_index(
                list(index_spec.items()),
                background=True
            )
            
            return json.dumps({
                "success": True,
                "message": f"Index oluşturuldu: {index_name}",
                "index": index_spec
            }, default=mongo_json_encoder, ensure_ascii=False)
            
        elif action == "drop":
            if not index_spec or "name" not in index_spec:
                return "Index adı gerekli"
            
            collection_obj.drop_index(index_spec["name"])
            
            return json.dumps({
                "success": True,
                "message": f"Index silindi: {index_spec['name']}"
            }, default=mongo_json_encoder, ensure_ascii=False)
            
        else:
            return f"Geçersiz index işlemi: {action}"
            
    except Exception as e:
        logger.error(f"Index management error: {e}")
        return f"Hata: {str(e)}"

# Tool oluşturma fonksiyonları
def create_query_tool(db_connector: MongoDBConnector, validator: QueryValidator) -> Tool:
    """Query çalıştırma tool'u oluştur"""
    def _run(args_input) -> str:
        """Esnek argüman alan wrapper fonksiyon"""
        try:
            # Debug için log
            logger.info(f"mongodb_query received: {type(args_input)} - {args_input}")
            
            # String kontrolü
            if isinstance(args_input, str):
                try:
                    import json
                    args_dict = json.loads(args_input)
                except:
                    return "Hata: Geçerli bir JSON formatı belirtin"
            else:
                args_dict = args_input
            
            # Format dönüşüm katmanı - ESKİ FORMATLARI DESTEKLE
            collection = ""
            query = {}
            operation = "find"
            options = {}
            
            # Eski format kontrolü ve dönüşümü
            if "find" in args_dict and "collection" not in args_dict:
                # Eski: {"find": "products", "filter": {...}}
                collection = args_dict.get("find", "")
                query = args_dict.get("filter", {})
                operation = "find"
                options = args_dict.get("limit", {})
                if isinstance(options, int):
                    options = {"limit": options}
            
            elif "count" in args_dict and "collection" not in args_dict:
                # Eski: {"count": "products", "filter": {...}}
                collection = args_dict.get("count", "")
                query = args_dict.get("filter", {})
                operation = "countDocuments"  # count'u countDocuments'e çevir
                
            elif "aggregate" in args_dict and "collection" not in args_dict:
                # Eski: {"aggregate": "products", "pipeline": [...]}
                collection = args_dict.get("aggregate", "")
                query = args_dict.get("pipeline", [])
                operation = "aggregate"
                
            else:
                # Yeni format veya standart format
                collection = args_dict.get("collection", "")
                query = args_dict.get("query", {})
                operation = args_dict.get("operation", "find")
                options = args_dict.get("options", {})
                
                # Filter/query karışıklığını düzelt
                if "filter" in args_dict and not query:
                    query = args_dict.get("filter", {})
                
                # Options içinde filter varsa taşı
                if "filter" in options:
                    query = options.pop("filter")
                    
                # count operation'ını countDocuments'e çevir
                if operation == "count":
                    operation = "countDocuments"
            
            # Koleksiyon adı kontrolü
            if not collection:
                return "Hata: Koleksiyon adı belirtilmedi"
            
            return execute_query(
                db_connector,
                validator,
                collection,
                query,
                operation,
                options
            )
        except Exception as e:
            logger.error(f"mongodb_query error: {e}")
            return f"Tool hatası: {str(e)}"
    
    return Tool(
        name="mongodb_query",
        description="""MongoDB'de sorgu çalıştır. 
        Doğru format: {"collection": "koleksiyon_adı", "query": {filtre}, "operation": "işlem_tipi", "options": {}}
        İşlem tipleri: find, findOne, countDocuments, aggregate""",
        func=_run
    )

def create_schema_tool(db_connector: MongoDBConnector, analyzer: SchemaAnalyzer) -> Tool:
    """Schema görüntüleme tool'u oluştur"""
    def _run(args_input) -> str:
        """Esnek argüman alan wrapper"""
        try:
            # Debug için log
            logger.info(f"view_schema received: {type(args_input)} - {args_input}")
            
            # String kontrolü
            if isinstance(args_input, str):
                # Eğer sadece koleksiyon adı geldiyse
                if not args_input.startswith('{'):
                    collection = args_input.strip()
                    detailed = False
                else:
                    # JSON string ise parse et
                    try:
                        import json
                        args_dict = json.loads(args_input)
                        collection = args_dict.get("collection", None)
                        detailed = args_dict.get("detailed", False)
                    except:
                        collection = args_input
                        detailed = False
            else:
                # Dict ise normal parse et
                collection = args_input.get("collection", None)
                detailed = args_input.get("detailed", False)
            
            return view_schema(
                db_connector,
                analyzer,
                collection,
                detailed
            )
        except Exception as e:
            logger.error(f"view_schema error: {e}")
            return f"Tool hatası: {str(e)}"
    
    return Tool(
        name="view_schema",
        description="""MongoDB koleksiyonlarının şema yapısını görüntüle.""",
        func=_run
    )

def create_index_tool(db_connector: MongoDBConnector) -> Tool:
    """Index yönetimi tool'u oluştur"""
    def _run(args_input) -> str:
        """Esnek argüman alan wrapper"""
        try:
            # Debug için log
            logger.info(f"manage_indexes received: {type(args_input)} - {args_input}")
            
            # String kontrolü
            if isinstance(args_input, str):
                # Eğer sadece koleksiyon adı girilmişse (JSON olmayan string)
                if not args_input.startswith('{'):
                    args_dict = {
                        "collection": args_input.strip(),
                        "action": "list",
                        "index_spec": None
                    }
                else:
                    # JSON string ise parse et
                    try:
                        import json
                        args_dict = json.loads(args_input)
                    except:
                        return "Hata: Geçerli bir JSON formatı belirtin"
            else:
                args_dict = args_input
            
            collection = args_dict.get("collection", "")
            action = args_dict.get("action", "list")
            index_spec = args_dict.get("index_spec", None)
            
            return manage_indexes(
                db_connector,
                collection,
                action,
                index_spec
            )
        except Exception as e:
            logger.error(f"manage_indexes error: {e}")
            return f"Tool hatası: {str(e)}"
    
    return Tool(
        name="manage_indexes",
        description="""MongoDB index işlemleri.""",
        func=_run
    )

def get_all_tools(
    db_connector: MongoDBConnector,
    validator: QueryValidator,
    analyzer: SchemaAnalyzer
) -> List[Tool]:
    """Tüm tool'ları döndür"""
    return [
        create_query_tool(db_connector, validator),
        create_schema_tool(db_connector, analyzer),
        create_index_tool(db_connector)
    ]