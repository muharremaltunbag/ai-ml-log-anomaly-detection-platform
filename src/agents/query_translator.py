from typing import Dict, List, Any, Optional, Tuple
from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
import json
import logging

class QueryTranslator:
    """Doğal dil → MongoDB sorgu dönüştürücü"""
    
    def __init__(self, llm: Optional[ChatOpenAI] = None):
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        
        # Sorgu çevirisi için sistem prompt'u
        self.system_prompt = """
        Sen bir MongoDB sorgu uzmanısın. Kullanıcının doğal dil sorgusunu MongoDB sorgusuna çeviriyorsun.

        TEMEL KURALLAR:
        1. Sadece geçerli MongoDB JSON sorguları üret
        2. $where, $function gibi kod çalıştıran operatörleri KULLANMA
        3. Kullanıcı hata yaptıysa veya eksik bilgi verdiyse, en mantıklı tahmini yap

        ANLAMA STRATEJİLERİ:
        - Yazım hatalarını tolere et (ör: "kullanıclar", "kullanicilar", "users" → users koleksiyonu)
        - Eş anlamlıları tanı (ör: "müşteri", "client", "customer" → customers koleksiyonu)
        - Alan adlarını tahmin et (ör: "yaşı 30'dan büyük" → age, yas, year_of_birth alanlarını düşün)
        - Bağlamdan çıkarım yap (ör: "aktif olanlar" → status: "active" veya isActive: true)

        ÖRNEKLER:

        Kullanıcı: "30 yaşından büyük aktif kullanıcıları getir"
        Çeviri: {{
            "collection": "users",
            "operation": "find",
            "query": {{"age": {{"$gt": 30}}, "status": "active"}},
            "options": {{}},
            "explanation": "30 yaşından büyük ve aktif durumda olan kullanıcıları bulur"
        }}

        Kullanıcı: "son 1 ayda kayıt olan müşteriler kaç tane"
        Çeviri: {{
            "collection": "customers",
            "operation": "countDocuments",
            "query": {{"createdAt": {{"$gte": {{"$date": "30 days ago"}}}}}},
            "options": {{}},
            "explanation": "Son 30 günde oluşturulan müşteri kayıtlarını sayar"
        }}

        Kullanıcı: "ürünlerde stok güncelle laptop için 50 yap"
        Çeviri: {{
            "collection": "products",
            "operation": "updateMany",
            "query": {{"name": {{"$regex": "laptop", "$options": "i"}}}},
            "update": {{"$set": {{"stock": 50}}}},
            "options": {{}},
            "explanation": "İsminde 'laptop' geçen tüm ürünlerin stok miktarını 50 olarak günceller"
        }}

        MEVCUT KOLEKSİYONLAR: {collections}
        {schema_context}

        YANIT FORMATI:
        {{
            "collection": "tahmin edilen koleksiyon adı",
            "operation": "find/aggregate/update/insert/delete/countDocuments",
            "query": {{MongoDB sorgu objesi}},
            "update": {{update operasyonları için}},
            "options": {{limit, sort, projection vb.}},
            "explanation": "Ne yaptığının Türkçe açıklaması",
            "assumptions": ["yaptığın tahminler listesi"]
        }}
        """
    
    def set_llm(self, llm: ChatOpenAI):
        """LLM bağlantısını ayarla"""
        self.llm = llm
    
    def translate_query(self, 
                       natural_language_query: str,
                       available_collections: List[str],
                       schema_hints: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Doğal dil sorgusunu MongoDB sorgusuna çevir
        
        Args:
            natural_language_query: Kullanıcının doğal dil sorusu
            available_collections: Mevcut koleksiyon listesi
            schema_hints: Koleksiyon şema bilgileri (opsiyonel)
            
        Returns:
            Dict: MongoDB sorgu bilgileri veya hata
        """
        try:
            # Prompt hazırla
            messages = self._prepare_translation_prompt(
                natural_language_query,
                available_collections,
                schema_hints
            )
            
            # LLM'den yanıt al
            response = self.llm.invoke(messages)
            
            # JSON parse et
            translation = self._parse_llm_response(response.content)
            
            # Çeviri logla
            self.logger.info(
                f"Sorgu çevirisi: '{natural_language_query[:50]}...' → "
                f"{translation.get('operation', 'unknown')} on {translation.get('collection', 'unknown')}"
            )
            
            return translation
            
        except Exception as e:
            self.logger.error(f"Çeviri hatası: {e}")
            return {
                "error": str(e),
                "original_query": natural_language_query
            }
            
    def _prepare_translation_prompt(self,
                              query: str,
                              collections: List[str],
                              schema_hints: Optional[Dict] = None) -> List[BaseMessage]:
        """Çeviri için prompt hazırla"""
        
        # Koleksiyon listesini ekle
        collections_str = ", ".join(collections) if collections else "Koleksiyon bilgisi yok"
        
        # Schema bilgilerini formatla
        schema_context = ""
        if schema_hints:
            schema_context = "\nSCHEMA BİLGİLERİ:\n"
            for coll, fields in schema_hints.items():
                if isinstance(fields, dict) and "fields" in fields:
                    field_names = list(fields["fields"].keys())[:10]  # İlk 10 alan
                    schema_context += f"- {coll}: {', '.join(field_names)}\n"
        
        # System prompt'u formatla
        formatted_system = self.system_prompt.format(
            collections=collections_str,
            schema_context=schema_context
        )
        
        return [
            SystemMessage(content=formatted_system),
            HumanMessage(content=query)
        ]
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """LLM yanıtını parse et ve doğrula"""
        try:
            # JSON'u parse et
            translation = json.loads(response)
            
            # Zorunlu alanları kontrol et
            required_fields = ["collection", "operation", "query"]
            for field in required_fields:
                if field not in translation:
                    raise ValueError(f"Eksik alan: {field}")
            
            # Operation'ı doğrula
            valid_operations = [
                "find", "findOne", "aggregate", "insertOne", "insertMany",
                "updateOne", "updateMany", "deleteOne", "deleteMany",
                "countDocuments", "distinct"
            ]
            
            if translation["operation"] not in valid_operations:
                raise ValueError(f"Geçersiz operation: {translation['operation']}")
            
            # Options'ı varsayılan olarak ekle
            if "options" not in translation:
                translation["options"] = {}
            
            return translation
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse hatası: {e}")
            # Fallback: Basit bir find sorgusu oluştur
            return {
                "collection": "unknown",
                "operation": "find",
                "query": {},
                "options": {},
                "error": f"Parse hatası: {str(e)}",
                "raw_response": response[:200]
            }
            
    def optimize_query(self, translation: Dict[str, Any]) -> Dict[str, Any]:
        """Çevrilmiş sorguyu optimize et"""
        try:
            operation = translation.get("operation")
            query = translation.get("query", {})
            options = translation.get("options", {})
            
            # Find sorgularını optimize et
            if operation in ["find", "findOne"]:
                # Varsayılan limit ekle (güvenlik için)
                if "limit" not in options and operation == "find":
                    options["limit"] = 100
                    translation["options"] = options
                
                # Boş sorguları logla
                if not query:
                    self.logger.warning("Boş sorgu tespit edildi, tüm dokümanlar dönecek")
            
            # Aggregate pipeline'ı optimize et
            elif operation == "aggregate":
                pipeline = translation.get("query", [])
                if isinstance(pipeline, list) and len(pipeline) > 0:
                    # $match varsa başa al (performans)
                    match_stages = [s for s in pipeline if "$match" in s]
                    other_stages = [s for s in pipeline if "$match" not in s]
                    if match_stages and pipeline[0] not in match_stages:
                        translation["query"] = match_stages + other_stages
            
            return translation
            
        except Exception as e:
            self.logger.error(f"Optimizasyon hatası: {e}")
            return translation
    
    def explain_query(self, translation: Dict[str, Any]) -> str:
        """Sorguyu kullanıcı dostu şekilde açıkla"""
        try:
            operation = translation.get("operation", "bilinmeyen")
            collection = translation.get("collection", "bilinmeyen")
            query = translation.get("query", {})
            
            # Temel açıklama
            explanation = translation.get("explanation", "")
            if not explanation:
                explanation = f"{collection} koleksiyonunda {operation} işlemi"
            
            # Detayları ekle
            details = []
            
            # Filtre detayları
            if query and operation in ["find", "findOne", "updateOne", "updateMany", "deleteOne", "deleteMany"]:
                details.append(f"Filtre: {self._summarize_query(query)}")
            
            # Limit/Sort detayları
            options = translation.get("options", {})
            if "limit" in options:
                details.append(f"Limit: {options['limit']}")
            if "sort" in options:
                details.append(f"Sıralama: {options['sort']}")
            
            # Update detayları
            if "update" in translation:
                details.append(f"Güncelleme: {self._summarize_query(translation['update'])}")
            
            if details:
                explanation += "\n" + "\n".join(f"  • {d}" for d in details)
            
            return explanation
            
        except Exception as e:
            return f"Açıklama oluşturulamadı: {str(e)}"
    
    def _summarize_query(self, query_obj: Dict, max_depth: int = 2) -> str:
        """Query objesini özetle"""
        if max_depth <= 0:
            return "..."
        
        parts = []
        for key, value in query_obj.items():
            if isinstance(value, dict):
                inner = self._summarize_query(value, max_depth - 1)
                parts.append(f"{key}: {inner}")
            elif isinstance(value, list):
                parts.append(f"{key}: [{len(value)} öğe]")
            else:
                parts.append(f"{key}: {value}")
        
        return "{" + ", ".join(parts) + "}"