#src/performance/query_analyzer.py
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
        """Aggregate pipeline için explain çalıştır - GÜNCELLENMİŞ"""
        try:
            # Yeni MongoDB sürümlerinde explain parametresi yerine command kullan
            explain_result = collection.database.command(
                'explain',
                {
                    'aggregate': collection.name,
                    'pipeline': pipeline,
                    'cursor': {}
                },
                verbosity='executionStats'
            )
            return explain_result
        except Exception as e:
            # Fallback: eski yöntem
            try:
                return collection.aggregate(pipeline, explain=True)
            except:
                logger.error(f"Aggregate explain hatası: {e}")
                # En azından temel bilgileri dön
                return {
                    "executionStats": {
                        "executionTimeMillis": 0,
                        "totalDocsExamined": 0,
                        "totalKeysExamined": 0,
                        "nReturned": 0,
                        "executionSuccess": False
                    },
                    "error": f"Explain desteklenmiyor: {str(e)}"
                }
    
    def _analyze_explain_result(self, explain_result: Dict, collection_name: str, 
                               query: Dict) -> Dict[str, Any]:
        """Explain sonucunu analiz et ve öneriler üret - GELİŞTİRİLMİŞ"""
        analysis = {
            "collection": collection_name,
            "query": query,
            "timestamp": datetime.now().isoformat()
        }
        
        # executionStats varsa detaylı analiz et
        if "executionStats" in explain_result:
            stats = explain_result["executionStats"]
            
            # Temel metrikler
            exec_time = stats.get("executionTimeMillis", 0)
            docs_examined = stats.get("totalDocsExamined", 0)
            docs_returned = stats.get("nReturned", 0)
            keys_examined = stats.get("totalKeysExamined", 0)
            
            # Verimlilik hesapla - YENİ
            efficiency = self._calculate_efficiency(docs_examined, docs_returned, keys_examined)
            
            analysis["execution_stats"] = {
                "execution_time_ms": exec_time,
                "total_docs_examined": docs_examined,
                "total_keys_examined": keys_examined,
                "docs_returned": docs_returned,
                "execution_success": stats.get("executionSuccess", False),
                "efficiency_percent": efficiency  # YENİ
            }
            
            # Geliştirilmiş performans skoru
            analysis["performance_score"] = self._calculate_enhanced_performance_score(
                stats, efficiency
            )
            
            # Stage analizi - execution tree olarak - YENİ
            if "executionStages" in stats:
                analysis["stages"] = self._analyze_stages(stats["executionStages"])
                analysis["execution_tree"] = self._build_execution_tree(stats["executionStages"])
                
        # Winning plan analizi
        if "queryPlanner" in explain_result and "winningPlan" in explain_result["queryPlanner"]:
            winning_plan = explain_result["queryPlanner"]["winningPlan"]
            analysis["winning_plan"] = self._analyze_winning_plan(winning_plan)
            
        # Öneriler üret
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        # İyileştirme tahmini - YENİ
        if analysis["recommendations"]:
            analysis["improvement_estimate"] = self._estimate_improvement(analysis)
        
        # Genel değerlendirme
        analysis["overall_assessment"] = self._generate_assessment(analysis)
        
        return analysis
    
    def _calculate_efficiency(self, docs_examined: int, docs_returned: int, keys_examined: int) -> float:
        """Sorgu verimliliğini hesapla - YENİ"""
        if docs_examined == 0:
            return 100.0
            
        # Temel verimlilik: dönen/taranan oranı
        basic_efficiency = (docs_returned / docs_examined) * 100 if docs_returned > 0 else 0
        
        # Index kullanımı bonusu
        if keys_examined > 0:
            # Index kullanılıyor, bonus ekle
            index_bonus = min(20, (keys_examined / docs_examined) * 20)
            efficiency = min(100, basic_efficiency + index_bonus)
        else:
            # Index kullanılmıyor, ceza
            efficiency = basic_efficiency * 0.7
            
        return round(efficiency, 2)
    
    def _calculate_enhanced_performance_score(self, stats: Dict, efficiency: float) -> Dict[str, Any]:
        """Geliştirilmiş performans skoru hesapla - GELİŞTİRİLMİŞ"""
        score = 100
        reasons = []
        detailed_scores = {}
        
        # 1. Execution Time Skoru (30 puan)
        exec_time = stats.get("executionTimeMillis", 0)
        time_score = 30
        if exec_time > 1000:
            time_score = 0
            reasons.append(f"Çok yüksek çalışma süresi: {exec_time}ms")
        elif exec_time > 500:
            time_score = 10
            reasons.append(f"Yüksek çalışma süresi: {exec_time}ms")
        elif exec_time > 100:
            time_score = 20
            reasons.append(f"Orta seviye çalışma süresi: {exec_time}ms")
        detailed_scores["time"] = time_score
        
        # 2. Verimlilik Skoru (30 puan)
        efficiency_score = min(30, efficiency * 0.3)
        if efficiency < 10:
            reasons.append(f"Çok düşük verimlilik: %{efficiency}")
        elif efficiency < 50:
            reasons.append(f"Düşük verimlilik: %{efficiency}")
        detailed_scores["efficiency"] = round(efficiency_score)
        
        # 3. Index Kullanım Skoru (25 puan)
        keys_examined = stats.get("totalKeysExamined", 0)
        docs_examined = stats.get("totalDocsExamined", 0)
        index_score = 25
        if docs_examined > 0 and keys_examined == 0:
            index_score = 0
            reasons.append("Index kullanılmıyor (COLLSCAN)")
        elif keys_examined > docs_examined * 2:
            index_score = 15
            reasons.append("Index verimsiz kullanılıyor")
        detailed_scores["index"] = index_score
        
        # 4. Sonuç Boyutu Skoru (15 puan)
        docs_returned = stats.get("nReturned", 0)
        result_score = 15
        if docs_returned > 10000:
            result_score = 5
            reasons.append(f"Çok fazla sonuç döndürülüyor: {docs_returned}")
        elif docs_returned > 1000:
            result_score = 10
            reasons.append(f"Fazla sonuç döndürülüyor: {docs_returned}")
        detailed_scores["result_size"] = result_score
        
        # Toplam skor
        total_score = sum(detailed_scores.values())
        
        return {
            "score": max(0, min(100, total_score)),
            "reasons": reasons,
            "level": self._get_performance_level(total_score),
            "detailed_scores": detailed_scores  # YENİ
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
    
    def _build_execution_tree(self, stage: Dict, depth: int = 0) -> Dict:
        """Execution tree oluştur - YENİ"""
        tree = {
            "stage": stage.get("stage", "UNKNOWN"),
            "depth": depth,
            "docs_examined": stage.get("docsExamined", 0),
            "keys_examined": stage.get("keysExamined", 0),
            "execution_time": stage.get("executionTimeMillisEstimate", 0),
            "works": stage.get("works", 0),
            "children": []
        }
        
        # Stage'e özel bilgiler
        stage_type = tree["stage"]
        
        if stage_type == "IXSCAN":
            tree["index_name"] = stage.get("indexName", "")
            tree["index_bounds"] = stage.get("indexBounds", {})
            tree["direction"] = stage.get("direction", "forward")
            tree["stage_info"] = "Index Scan - Performanslı"
            
        elif stage_type == "COLLSCAN":
            tree["stage_info"] = "Collection Scan - Verimsiz!"
            tree["filter"] = stage.get("filter", {})
            
        elif stage_type == "SORT":
            tree["sort_pattern"] = stage.get("sortPattern", {})
            tree["memory_used"] = stage.get("memUsage", 0)
            tree["stage_info"] = "In-memory sort"
            
        elif stage_type == "FETCH":
            tree["stage_info"] = "Document fetch"
            tree["filter"] = stage.get("filter", {})
            
        elif stage_type == "COUNT":
            tree["stage_info"] = "Count operation"
            
        # Alt stage'leri işle
        if "inputStage" in stage:
            child_tree = self._build_execution_tree(stage["inputStage"], depth + 1)
            tree["children"].append(child_tree)
            
        # Birden fazla input stage varsa (örn: $or)
        if "inputStages" in stage:
            for input_stage in stage["inputStages"]:
                child_tree = self._build_execution_tree(input_stage, depth + 1)
                tree["children"].append(child_tree)
        
        return tree
    
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
            
        # Birden fazla input stage varsa
        if "inputStages" in stage:
            for input_stage in stage["inputStages"]:
                stages.extend(self._analyze_stages(input_stage, depth + 1))
        
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
    
    def _estimate_improvement(self, analysis: Dict) -> Dict[str, Any]:
        """İyileştirme tahmini yap - YENİ"""
        if "execution_stats" not in analysis:
            return {}
            
        current_time = analysis["execution_stats"]["execution_time_ms"]
        current_docs_examined = analysis["execution_stats"]["total_docs_examined"]
        docs_returned = analysis["execution_stats"]["docs_returned"]
        
        improvement = {
            "current_time_ms": current_time,
            "estimated_time_ms": current_time,
            "improvement_percent": 0,
            "docs_examined_reduction": 0
        }
        
        # COLLSCAN varsa ve index önerisi varsa
        has_collscan = any(stage["stage"] == "COLLSCAN" for stage in analysis.get("stages", []))
        has_index_recommendation = any(rec["type"] == "index" for rec in analysis.get("recommendations", []))
        
        if has_collscan and has_index_recommendation:
            # Index ile yaklaşık %95 iyileşme
            improvement["estimated_time_ms"] = max(1, current_time * 0.05)
            improvement["improvement_percent"] = 95
            
            # Taranacak doküman sayısı da azalacak
            if docs_returned > 0:
                improvement["estimated_docs_examined"] = docs_returned
                improvement["docs_examined_reduction"] = current_docs_examined - docs_returned
        
        elif current_time > 100:
            # Genel optimizasyon ile %30 iyileşme
            improvement["estimated_time_ms"] = current_time * 0.7
            improvement["improvement_percent"] = 30
            
        return improvement
    
    def _generate_recommendations(self, analysis: Dict) -> List[Dict[str, str]]:
        """Performans önerileri üret - GELİŞTİRİLMİŞ"""
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
            
            # Düşük verimlilik kontrolü - YENİ
            if stats.get("efficiency_percent", 100) < 10:
                recommendations.append({
                    "type": "efficiency",
                    "priority": "high",
                    "message": f"Çok düşük sorgu verimliliği: %{stats['efficiency_percent']}",
                    "detail": "Sorgu çok fazla gereksiz doküman tarıyor."
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
        """Genel değerlendirme metni oluştur - GELİŞTİRİLMİŞ"""
        if "performance_score" not in analysis:
            return "Performans analizi yapılamadı."
            
        score = analysis["performance_score"]["score"]
        level = analysis["performance_score"]["level"]
        
        assessment = f"Sorgu performansı: {level} ({score}/100)\n"
        
        # Detaylı skorlar - YENİ
        if "detailed_scores" in analysis["performance_score"]:
            scores = analysis["performance_score"]["detailed_scores"]
            assessment += f"\nDetaylı Skorlar:\n"
            assessment += f"- Zaman: {scores.get('time', 0)}/30\n"
            assessment += f"- Verimlilik: {scores.get('efficiency', 0)}/30\n"
            assessment += f"- Index Kullanımı: {scores.get('index', 0)}/25\n"
            assessment += f"- Sonuç Boyutu: {scores.get('result_size', 0)}/15\n"
        
        if "execution_stats" in analysis:
            stats = analysis["execution_stats"]
            assessment += f"\nÇalışma süresi: {stats['execution_time_ms']}ms\n"
            assessment += f"Taranan doküman: {stats['total_docs_examined']}\n"
            assessment += f"Dönen doküman: {stats['docs_returned']}\n"
            assessment += f"Verimlilik: %{stats.get('efficiency_percent', 0)}"
            
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