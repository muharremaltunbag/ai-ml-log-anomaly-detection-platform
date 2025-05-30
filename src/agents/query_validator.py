import re
from typing import Dict, List, Any, Tuple, Set
import logging

class QueryValidator:
    """MongoDB sorgu güvenlik validatörü - Dengeli yaklaşım"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Genişletilmiş izin verilen operatörler
        self.allowed_operators = {
            # Karşılaştırma
            '$eq', '$ne', '$gt', '$gte', '$lt', '$lte',
            '$in', '$nin', '$exists', '$type',
            # Mantıksal
            '$and', '$or', '$not', '$nor',
            # Dizi
            '$all', '$elemMatch', '$size',
            # String/Regex
            '$regex', '$text', '$search',
            # Aggregation
            '$match', '$group', '$sort', '$limit', '$skip',
            '$project', '$unwind', '$lookup', '$count',
            '$addFields', '$set', '$unset',
            # Update
            '$set', '$unset', '$inc', '$push', '$pull',
            '$addToSet', '$pop', '$rename'
        }
        
        # Sadece gerçekten tehlikeli olanlar
        self.dangerous_operators = {
            '$where',      # Direkt JS kodu
            '$function',   # Custom JS fonksiyon
            '$accumulator', # Custom aggregation JS
            '$system'      # System koleksiyonları
        }
        
        
        self.allowed_operations = {
            # Okuma
            'find', 'findOne', 'countDocuments', 
            'distinct', 'aggregate',
            # Yazma (kontrollü)
            'insertOne', 'insertMany',
            'updateOne', 'updateMany', 
            'deleteOne', 'deleteMany',
            'replaceOne',
            # Index
            'createIndex', 'dropIndex', 'listIndexes'
        }
        
        # Hassas koleksiyonlar (bunlara ekstra dikkat)
        self.sensitive_collections = {
            'users', 'permissions', 'audit_logs', 'system'
        }
    
    def validate_query(self, query: Dict[str, Any], 
                      operation: str = 'find',
                      collection: str = '') -> Tuple[bool, str]:
        """Sorguyu güvenlik açısından kontrol et"""
        try:
            # Operation dönüşümü (eski format desteği)
            if operation == "count":
                operation = "countDocuments"
                
            # Operasyon kontrolü
            if operation not in self.allowed_operations:
                return False, f"İzin verilmeyen operasyon: {operation}"
            
            # Hassas koleksiyon kontrolü
            if collection in self.sensitive_collections:
                if operation in ['deleteMany', 'updateMany']:
                    return False, f"Hassas koleksiyonda toplu işlem: {collection}"
            
            # Tehlikeli operatör kontrolü
            if self._contains_dangerous_operators(query):
                return False, "Güvenlik riski olan operatör tespit edildi"
            
            # Derinlik kontrolü (8'e çıkarıldı)
            if self._check_nested_depth(query) > 8:
                return False, "Sorgu çok karmaşık (max 8 seviye)"
            
            # Sadece açık JS injection kontrolü
            if self._contains_obvious_javascript(str(query)):
                return False, "JavaScript injection tespit edildi"
            
            # Aggregation pipeline kontrolü
            if operation == 'aggregate' and isinstance(query, list):
                return self._validate_aggregation_pipeline(query)
            
            return True, "Sorgu onaylandı"
            
        except Exception as e:
            self.logger.error(f"Validasyon hatası: {e}")
            return False, f"Validasyon hatası: {str(e)}"
    
    def _validate_aggregation_pipeline(self, pipeline: List[Dict]) -> Tuple[bool, str]:
        """Aggregation pipeline özel kontrolü"""
        for stage in pipeline:
            if not isinstance(stage, dict):
                return False, "Geçersiz pipeline aşaması"
            
            stage_op = list(stage.keys())[0] if stage else None
            if stage_op and stage_op not in self.allowed_operators:
                return False, f"İzin verilmeyen aggregation operatörü: {stage_op}"
        
        return True, "Pipeline onaylandı"
    
    def _contains_dangerous_operators(self, obj: Any) -> bool:
        """Sadece gerçekten tehlikeli operatörleri kontrol et"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in self.dangerous_operators:
                    return True
                if self._contains_dangerous_operators(value):
                    return True
        elif isinstance(obj, list):
            for item in obj:
                if self._contains_dangerous_operators(item):
                    return True
        return False
    
    def _check_nested_depth(self, obj: Any, depth: int = 0) -> int:
        """Nesne derinliğini kontrol et (limit artırıldı)"""
        if depth > 15:  # Sonsuz döngü koruması
            return depth
        
        if isinstance(obj, dict):
            return max([self._check_nested_depth(v, depth + 1) 
                       for v in obj.values()], default=depth)
        elif isinstance(obj, list):
            return max([self._check_nested_depth(item, depth + 1) 
                       for item in obj], default=depth)
        return depth
    
    def _contains_obvious_javascript(self, query_str: str) -> bool:
        """Sadece açık JS injection kontrolü"""
        dangerous_patterns = [
            r'function\s*\(',
            r'eval\s*\(',
            r'Function\s*\(',
            r'process\.exit',
            r'require\s*\('
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, query_str, re.IGNORECASE):
                return True
        return False
    
    def sanitize_input(self, user_input: str) -> str:
        """Kullanıcı girdisini temizle"""
        # Temel temizleme
        sanitized = user_input.strip()
        # Çift tırnakları escape et
        sanitized = sanitized.replace('"', '\\"')
        return sanitized