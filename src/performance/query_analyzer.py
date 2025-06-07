import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class QueryPerformanceAnalyzer:
    """MongoDB sorgu performans analizörü"""
    
    def __init__(self, db_connector=None):
        """
        QueryPerformanceAnalyzer başlat
        
        Args:
            db_connector: MongoDBConnector instance
        """
        self.db_connector = db_connector
        self.logger = logger
        
    def set_db_connector(self, db_connector):
        """Database connector'ı ayarla"""
        self.db_connector = db_connector
        
    def analyze_query(self, collection_name: str, query: Dict[str, Any], 
                     operation: str = "find", options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Sorgunun execution plan'ını analiz et
        
        Args:
            collection_name: Koleksiyon adı
            query: MongoDB sorgusu
            operation: İşlem tipi (find, aggregate, vb.)
            options: Ek seçenekler (limit, sort, vb.)
            
        Returns:
            Dict: Analiz sonuçları
        """
        try:
            if not self.db_connector or not self.db_connector.is_connected():
                return {"error": "Database bağlantısı yok"}
                
            collection = self.db_connector.database[collection_name]
            
            # Explain komutu çalıştır
            if operation == "find":
                explain_result = self._explain_find(collection, query, options)
            elif operation == "aggregate":
                explain_result = self._explain_aggregate(collection, query)
            else:
                return {"error": f"Desteklenmeyen operasyon: {operation}"}
                
            # Sonuçları analiz et
            analysis = self._analyze_explain_result(explain_result, collection_name, query)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Query analiz hatası: {e}")
            return {"error": str(e)}
    
    def _explain_find(self, collection, query: Dict, options: Dict = None) -> Dict:
        """Find sorgusu için explain çalıştır"""
        if options is None:
            options = {}
            
        cursor = collection.find(query)
        
        # Options uygula
        if "sort" in options and options["sort"]:
            cursor = cursor.sort(list(options["sort"].items()))
        if "limit" in options and options["limit"]:
            cursor = cursor.limit(options["limit"])
            
        # Explain çalıştır
        return cursor.explain()
    
    def _explain_aggregate(self, collection, pipeline: List[Dict]) -> Dict:
        """Aggregate pipeline için explain çalıştır"""
        return collection.aggregate(pipeline, explain=True)
    
    def _analyze_explain_result(self, explain_result: Dict, collection_name: str, 
                               query: Dict) -> Dict[str, Any]:
        """Explain sonucunu analiz et ve öneriler üret"""
        analysis = {
            "collection": collection_name,
            "query": query,
            "timestamp": datetime.now().isoformat()
        }
        
        # executionStats varsa analiz et
        if "executionStats" in explain_result:
            stats = explain_result["executionStats"]
            
            analysis["execution_stats"] = {
                "execution_time_ms": stats.get("executionTimeMillis", 0),
                "total_docs_examined": stats.get("totalDocsExamined", 0),
                "total_keys_examined": stats.get("totalKeysExamined", 0),
                "docs_returned": stats.get("nReturned", 0),
                "execution_success": stats.get("executionSuccess", False)
            }
            
            # Performans skoru hesapla
            analysis["performance_score"] = self._calculate_performance_score(stats)
            
            # Stage analizi
            if "executionStages" in stats:
                analysis["stages"] = self._analyze_stages(stats["executionStages"])
                
        # Winning plan analizi
        if "queryPlanner" in explain_result and "winningPlan" in explain_result["queryPlanner"]:
            winning_plan = explain_result["queryPlanner"]["winningPlan"]
            analysis["winning_plan"] = self._analyze_winning_plan(winning_plan)
            
        # Öneriler üret
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        # Genel değerlendirme
        analysis["overall_assessment"] = self._generate_assessment(analysis)
        
        return analysis
    
    def _calculate_performance_score(self, stats: Dict) -> Dict[str, Any]:
        """Performans skoru hesapla (0-100)"""
        score = 100
        reasons = []
        
        # Execution time kontrolü
        exec_time = stats.get("executionTimeMillis", 0)
        if exec_time > 1000:
            score -= 30
            reasons.append(f"Yüksek çalışma süresi: {exec_time}ms")
        elif exec_time > 500:
            score -= 15
            reasons.append(f"Orta seviye çalışma süresi: {exec_time}ms")
            
        # Doküman tarama oranı
        docs_examined = stats.get("totalDocsExamined", 0)
        docs_returned = stats.get("nReturned", 0)
        
        if docs_returned > 0:
            scan_ratio = docs_examined / docs_returned
            if scan_ratio > 100:
                score -= 30
                reasons.append(f"Çok yüksek tarama oranı: {scan_ratio:.1f}:1")
            elif scan_ratio > 10:
                score -= 15
                reasons.append(f"Yüksek tarama oranı: {scan_ratio:.1f}:1")
                
        # Index kullanımı
        keys_examined = stats.get("totalKeysExamined", 0)
        if docs_examined > 0 and keys_examined == 0:
            score -= 25
            reasons.append("Index kullanılmıyor (COLLSCAN)")
            
        return {
            "score": max(0, score),
            "reasons": reasons,
            "level": self._get_performance_level(score)
        }
    
    def _get_performance_level(self, score: int) -> str:
        """Performans seviyesini belirle"""
        if score >= 90:
            return "Mükemmel"
        elif score >= 70:
            return "İyi"
        elif score >= 50:
            return "Orta"
        elif score >= 30:
            return "Düşük"
        else:
            return "Kritik"
    
    def _analyze_stages(self, stage: Dict, depth: int = 0) -> List[Dict]:
        """Execution stage'lerini analiz et"""
        stages = []
        
        stage_info = {
            "stage": stage.get("stage", "UNKNOWN"),
            "docs_examined": stage.get("docsExamined", 0),
            "keys_examined": stage.get("keysExamined", 0),
            "works": stage.get("works", 0),
            "depth": depth
        }
        
        # Özel stage analizi
        if stage_info["stage"] == "COLLSCAN":
            stage_info["warning"] = "Collection scan - Index kullanılmıyor!"
        elif stage_info["stage"] == "IXSCAN":
            stage_info["index_name"] = stage.get("indexName", "")
            stage_info["info"] = "Index scan - Performanslı"
            
        stages.append(stage_info)
        
        # Alt stage'leri analiz et
        if "inputStage" in stage:
            stages.extend(self._analyze_stages(stage["inputStage"], depth + 1))
        
        return stages
    
    def _analyze_winning_plan(self, plan: Dict) -> Dict[str, Any]:
        """Winning plan'ı analiz et"""
        analysis = {
            "stage": plan.get("stage", "UNKNOWN"),
            "index_used": False,
            "index_name": None
        }
        
        # Index kullanımını kontrol et
        if "inputStage" in plan and plan["inputStage"].get("stage") == "IXSCAN":
            analysis["index_used"] = True
            analysis["index_name"] = plan["inputStage"].get("indexName")
        elif plan.get("stage") == "IXSCAN":
            analysis["index_used"] = True
            analysis["index_name"] = plan.get("indexName")
            
        return analysis
    
    def _generate_recommendations(self, analysis: Dict) -> List[Dict[str, str]]:
        """Performans önerileri üret"""
        recommendations = []
        
        # Execution stats varsa
        if "execution_stats" in analysis:
            stats = analysis["execution_stats"]
            
            # Yavaş sorgu kontrolü
            if stats["execution_time_ms"] > 500:
                recommendations.append({
                    "type": "performance",
                    "priority": "high",
                    "message": "Sorgu yavaş çalışıyor. Index eklemeyi düşünün.",
                    "detail": f"Mevcut süre: {stats['execution_time_ms']}ms, Hedef: <100ms"
                })
                
            # Collection scan kontrolü
            if "stages" in analysis:
                for stage in analysis["stages"]:
                    if stage["stage"] == "COLLSCAN":
                        recommendations.append({
                            "type": "index",
                            "priority": "critical",
                            "message": "Collection scan tespit edildi! Index eklenmeli.",
                            "detail": "Tüm dokümanlar taranıyor, bu çok verimsiz."
                        })
                        
                        # Query'den index önerisi çıkar
                        index_suggestion = self._suggest_index(analysis["query"])
                        if index_suggestion:
                            recommendations.append({
                                "type": "index_suggestion",
                                "priority": "high",
                                "message": f"Önerilen index: {index_suggestion['fields']}",
                                "detail": index_suggestion['reason']
                            })
                        break
                        
            # Tarama oranı kontrolü
            if stats["total_docs_examined"] > 0 and stats["docs_returned"] > 0:
                scan_ratio = stats["total_docs_examined"] / stats["docs_returned"]
                if scan_ratio > 10:
                    recommendations.append({
                        "type": "efficiency",
                        "priority": "medium",
                        "message": f"Yüksek tarama oranı: {scan_ratio:.1f}:1",
                        "detail": "Daha spesifik sorgular veya uygun index kullanın."
                    })
                    
        return recommendations
    
    def _suggest_index(self, query: Dict) -> Optional[Dict[str, Any]]:
        """Query'ye göre index önerisi üret"""
        if not query:
            return None
            
        # Basit index önerisi - query'deki ilk birkaç alan
        fields = []
        for key in list(query.keys())[:3]:  # İlk 3 alan
            if not key.startswith("$"):
                fields.append((key, 1))
                
        if fields:
            return {
                "fields": dict(fields),
                "reason": f"Sorgudaki {', '.join([f[0] for f in fields])} alanları için index önerilir."
            }
            
        return None
    
    def _generate_assessment(self, analysis: Dict) -> str:
        """Genel değerlendirme metni oluştur"""
        if "performance_score" not in analysis:
            return "Performans analizi yapılamadı."
            
        score = analysis["performance_score"]["score"]
        level = analysis["performance_score"]["level"]
        
        assessment = f"Sorgu performansı: {level} ({score}/100)\n"
        
        if "execution_stats" in analysis:
            stats = analysis["execution_stats"]
            assessment += f"Çalışma süresi: {stats['execution_time_ms']}ms\n"
            assessment += f"Taranan doküman: {stats['total_docs_examined']}\n"
            assessment += f"Dönen doküman: {stats['docs_returned']}"
            
        return assessment
    
    def get_slow_queries_profile(self, threshold_ms: int = 100) -> List[Dict[str, Any]]:
        """Profiling koleksiyonundan yavaş sorguları getir"""
        try:
            if not self.db_connector or not self.db_connector.is_connected():
                return []
                
            # system.profile koleksiyonunu kontrol et
            profile_collection = self.db_connector.database.system.profile
            
            # Yavaş sorguları bul
            slow_queries = list(profile_collection.find({
                "millis": {"$gte": threshold_ms}
            }).sort("ts", -1).limit(10))
            
            # Sonuçları formatla
            formatted_queries = []
            for query in slow_queries:
                formatted_queries.append({
                    "timestamp": query.get("ts"),
                    "duration_ms": query.get("millis"),
                    "operation": query.get("op"),
                    "namespace": query.get("ns"),
                    "command": query.get("command", {}),
                    "docs_examined": query.get("docsExamined", 0)
                })
                
            return formatted_queries
            
        except Exception as e:
            self.logger.error(f"Slow query profile hatası: {e}")
            return []