from typing import Dict, List, Any, Optional
from pymongo.database import Database
import logging

class SchemaAnalyzer:
    """MongoDB koleksiyon ve şema analizörü"""
    
    def __init__(self, database: Optional[Database] = None):
        self.database = database
        self.logger = logging.getLogger(__name__)
        self._schema_cache = {}
        
    def set_database(self, database: Database):
        """Database bağlantısını ayarla"""
        self.database = database
        self._schema_cache.clear()
    
    def get_available_collections(self) -> List[str]:
        """Mevcut koleksiyonları listele"""
        try:
            collections = self.database.list_collection_names()
            # Sistem koleksiyonlarını filtrele
            return [c for c in collections if not c.startswith('system.')]
        except Exception as e:
            self.logger.error(f"Koleksiyon listesi alınamadı: {e}")
            return []
    
    def analyze_collection_schema(self, collection_name: str, 
                                sample_size: int = 100) -> Dict[str, Any]:
        """Koleksiyonun şema yapısını analiz et"""
        
        # Cache kontrolü
        if collection_name in self._schema_cache:
            return self._schema_cache[collection_name]
        
        try:
            collection = self.database[collection_name]
            
            # Örnek dokümanlar al
            samples = list(collection.find().limit(sample_size))
            
            if not samples:
                return {"fields": {}, "count": 0}
            
            # Alan tiplerini analiz et
            field_info = {}
            for doc in samples:
                self._analyze_document(doc, field_info)
            
            # İstatistikleri hesapla
            schema_info = {
                "collection": collection_name,
                "document_count": collection.count_documents({}),
                "sample_size": len(samples),
                "fields": self._calculate_field_stats(field_info, len(samples)),
                "indexes": self._get_indexes(collection_name)
            }
            
            # Cache'e kaydet
            self._schema_cache[collection_name] = schema_info
            
            return schema_info
            
        except Exception as e:
            self.logger.error(f"Şema analizi hatası ({collection_name}): {e}")
            return {"error": str(e)}
    
    def analyze_collection_schema_advanced(self, collection_name: str) -> Dict[str, Any]:
        """
        Hibrit yaklaşımla detaylı schema analizi
        
        Returns:
            Dict: Schema bilgileri veya hata mesajı
        """
        try:
            collection = self.database[collection_name]
            
            # Koleksiyon boyutunu öğren
            total_docs = collection.count_documents({})
            
            if total_docs == 0:
                return {
                    "collection": collection_name,
                    "document_count": 0,
                    "fields": {},
                    "message": "Koleksiyon boş"
                }
            
            # Örnekleme stratejisini belirle
            samples = []
            sampling_methods = []
            
            # 1. HIZLI BAŞLANGIÇ: İlk 50 doküman
            quick_samples = list(collection.find().limit(50))
            samples.extend(quick_samples)
            sampling_methods.append(f"İlk {len(quick_samples)} doküman")
            
            self.logger.info(f"{collection_name}: {total_docs} doküman, hibrit analiz başladı")
            
            # 2. RASTGELE ÖRNEKLEME: Koleksiyon boyutuna göre
            if total_docs <= 1000:
                # Küçük koleksiyon: $sample kullan
                try:
                    random_samples = list(collection.aggregate([
                        {"$sample": {"size": min(100, total_docs // 10)}}
                    ]))
                    samples.extend(random_samples)
                    sampling_methods.append(f"Rastgele {len(random_samples)} doküman ($sample)")
                except Exception as e:
                    self.logger.warning(f"$sample başarısız: {e}")
                    
            else:
                # Büyük koleksiyon: Skip metoduyla dağıtılmış örnekleme
                try:
                    sample_count = min(100, total_docs // 100)
                    step = total_docs // sample_count
                    
                    for i in range(0, sample_count):
                        skip_count = i * step
                        doc = collection.find_one(skip=skip_count)
                        if doc:
                            samples.append(doc)
                    
                    sampling_methods.append(f"Dağıtılmış {sample_count} doküman (skip metodu)")
                except Exception as e:
                    self.logger.warning(f"Skip örnekleme başarısız: {e}")
            
            # 3. ALAN ANALİZİ: Toplanan örnekler üzerinde
            field_info = {}
            for doc in samples:
                self._analyze_document(doc, field_info)
            
            # 4. SONUÇLARI HESAPLA VE FORMATLA
            unique_samples = len(samples)
            
            # Alan istatistiklerini hesapla
            field_stats = self._calculate_field_stats(field_info, unique_samples)
            
            # 5. DETAYLI RAPOR OLUŞTUR
            advanced_schema_info = {
                "collection": collection_name,
                "document_count": total_docs,
                "analysis": {
                    "total_samples_analyzed": unique_samples,
                    "sampling_methods": sampling_methods,
                    "coverage_percentage": round((unique_samples / total_docs) * 100, 2)
                },
                "fields": field_stats,
                "indexes": self._get_indexes(collection_name),
                "recommendations": {
                    "frequently_null_fields": [
                        field for field, stats in field_stats.items() 
                        if stats["fill_rate"] < 50
                    ],
                    "mixed_type_fields": [
                        field for field, stats in field_stats.items() 
                        if len(stats["all_types"]) > 1
                    ]
                }
            }
            
            # Cache'e kaydet (opsiyonel)
            # self._schema_cache[f"{collection_name}_advanced"] = advanced_schema_info
            
            self.logger.info(
                f"{collection_name} analizi tamamlandı: "
                f"{unique_samples} örnek, {len(field_stats)} alan bulundu"
            )
            
            return advanced_schema_info
            
        except Exception as e:
            self.logger.error(f"Advanced schema analizi hatası: {e}")
            return {"error": str(e), "collection": collection_name}
    
    def _analyze_document(self, doc: Dict, field_info: Dict, prefix: str = ""):
        """Doküman yapısını recursive olarak analiz et"""
        for key, value in doc.items():
            field_path = f"{prefix}.{key}" if prefix else key
            
            if field_path not in field_info:
                field_info[field_path] = {
                    "types": {},
                    "examples": [],
                    "nested": isinstance(value, dict)
                }
            
            # Tip bilgisi ekle
            value_type = type(value).__name__
            field_info[field_path]["types"][value_type] = \
                field_info[field_path]["types"].get(value_type, 0) + 1
            
            # Örnek değer ekle (max 3)
            if len(field_info[field_path]["examples"]) < 3:
                if not isinstance(value, (dict, list)):
                    field_info[field_path]["examples"].append(value)
            
            # Nested objeler için recursive çağrı
            if isinstance(value, dict):
                self._analyze_document(value, field_info, field_path)
    
    def _calculate_field_stats(self, field_info: Dict, total_docs: int) -> Dict:
        """Alan istatistiklerini hesapla"""
        field_stats = {}
        
        for field, info in field_info.items():
            # En yaygın tip
            most_common_type = max(info["types"].items(), 
                                 key=lambda x: x[1])[0]
            
            # Doluluk oranı
            occurrence_count = sum(info["types"].values())
            fill_rate = (occurrence_count / total_docs) * 100
            
            field_stats[field] = {
                "primary_type": most_common_type,
                "all_types": list(info["types"].keys()),
                "fill_rate": round(fill_rate, 2),
                "examples": info["examples"],
                "is_nested": info["nested"]
            }
        
        return field_stats
    
    def _get_indexes(self, collection_name: str) -> List[Dict]:
        """Koleksiyon index bilgilerini al"""
        try:
            collection = self.database[collection_name]
            indexes = []
            
            for index in collection.list_indexes():
                indexes.append({
                    "name": index.get("name"),
                    "keys": index.get("key"),
                    "unique": index.get("unique", False)
                })
            
            return indexes
        except Exception as e:
            self.logger.error(f"Index bilgisi alınamadı: {e}")
            return []
    
    def suggest_query_fields(self, collection_name: str, 
                           user_intent: str) -> List[str]:
        """Kullanıcı amacına göre uygun alanları öner"""
        schema = self.analyze_collection_schema(collection_name)
        
        if "error" in schema:
            return []
        
        # Basit bir öneri sistemi (geliştirilecek)
        suggested_fields = []
        intent_lower = user_intent.lower()
        
        for field, stats in schema["fields"].items():
            field_lower = field.lower()
            
            # Alan adı veya örneklerde eşleşme ara
            if any(keyword in field_lower for keyword in intent_lower.split()):
                suggested_fields.append(field)
                continue
            
            # Örnek değerlerde ara
            for example in stats["examples"]:
                if str(example).lower() in intent_lower:
                    suggested_fields.append(field)
                    break
        
        return suggested_fields[:5]  # En fazla 5 öneri