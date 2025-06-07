from typing import Dict, Any, List, Optional
from langchain.tools import Tool
import json
import logging
from .query_analyzer import QueryPerformanceAnalyzer

logger = logging.getLogger(__name__)

class PerformanceTools:
    """MongoDB Performance Analysis için LangChain Tool'ları"""
    
    def __init__(self, db_connector=None):
        """
        PerformanceTools başlat
        
        Args:
            db_connector: MongoDBConnector instance
        """
        self.analyzer = QueryPerformanceAnalyzer(db_connector)
        self.db_connector = db_connector
        logger.info("PerformanceTools başlatıldı")
    
    def _format_result(self, result: Dict[str, Any], operation: str) -> str:
        """Sonuçları MongoDB Agent formatına uygun şekilde formatla"""
        try:
            if "error" in result:
                return json.dumps({
                    "durum": "hata",
                    "işlem": operation,
                    "açıklama": result.get("error", "Bilinmeyen hata"),
                    "sonuç": None
                }, ensure_ascii=False, indent=2)
            
            # Başarılı sonuç formatla
            formatted = {
                "durum": "başarılı",
                "işlem": operation,
                "koleksiyon": result.get("collection", ""),
                "açıklama": self._generate_description(result),
                "sonuç": result,
                "öneriler": self._format_recommendations(result.get("recommendations", []))
            }
            
            return json.dumps(formatted, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Format hatası: {e}")
            return json.dumps({
                "durum": "hata",
                "işlem": operation,
                "açıklama": f"Format hatası: {str(e)}",
                "sonuç": str(result)
            }, ensure_ascii=False, indent=2)
    
    def _generate_description(self, result: Dict[str, Any]) -> str:
        """Analiz sonucunu Türkçe açıklama olarak oluştur"""
        desc_parts = []
        
        # Performans skoru
        if "performance_score" in result:
            score_info = result["performance_score"]
            desc_parts.append(
                f"Sorgu performans skoru: {score_info['score']}/100 ({score_info['level']})"
            )
            if score_info.get("reasons"):
                desc_parts.append("Tespit edilen sorunlar:")
                for reason in score_info["reasons"]:
                    desc_parts.append(f"- {reason}")
        
        # Execution stats
        if "execution_stats" in result:
            stats = result["execution_stats"]
            desc_parts.append(f"\nÇalışma istatistikleri:")
            desc_parts.append(f"- Çalışma süresi: {stats['execution_time_ms']}ms")
            desc_parts.append(f"- Taranan doküman sayısı: {stats['total_docs_examined']}")
            desc_parts.append(f"- Taranan index key sayısı: {stats['total_keys_examined']}")
            desc_parts.append(f"- Dönen doküman sayısı: {stats['docs_returned']}")
        
        # Winning plan
        if "winning_plan" in result:
            plan = result["winning_plan"]
            if plan["index_used"]:
                desc_parts.append(f"\nKullanılan index: {plan['index_name']}")
            else:
                desc_parts.append("\n⚠️ Index kullanılmıyor (Collection Scan)")
        
        return "\n".join(desc_parts)
    
    def _format_recommendations(self, recommendations: List[Dict]) -> List[str]:
        """Önerileri Türkçe formatla"""
        formatted = []
        
        # Öncelik sırasına göre sırala
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_recs = sorted(recommendations, 
                           key=lambda x: priority_order.get(x.get("priority", "low"), 3))
        
        for rec in sorted_recs:
            priority = rec.get("priority", "low")
            priority_emoji = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "💡",
                "low": "ℹ️"
            }.get(priority, "")
            
            formatted.append(
                f"{priority_emoji} [{priority.upper()}] {rec['message']} - {rec.get('detail', '')}"
            )
        
        return formatted
    
    def analyze_query_performance(self, args_input) -> str:
        """Sorgu performansını analiz et"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    return self._format_result(
                        {"error": "Geçerli JSON formatı gerekli"},
                        "query_performance_analysis"
                    )
            else:
                args_dict = args_input
            
            # Parametreleri al
            collection = args_dict.get("collection", "")
            query = args_dict.get("query", {})
            operation = args_dict.get("operation", "find")
            options = args_dict.get("options", {})
            
            if not collection:
                return self._format_result(
                    {"error": "Koleksiyon adı belirtilmeli"},
                    "query_performance_analysis"
                )
            
            # Analizi yap
            result = self.analyzer.analyze_query(collection, query, operation, options)
            
            return self._format_result(result, "query_performance_analysis")
            
        except Exception as e:
            logger.error(f"Query performance analysis hatası: {e}")
            return self._format_result({"error": str(e)}, "query_performance_analysis")
    
    def get_slow_queries(self, args_input) -> str:
        """Yavaş sorguları listele"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"threshold_ms": 100}
            else:
                args_dict = args_input
            
            threshold_ms = args_dict.get("threshold_ms", 100)
            
            # Yavaş sorguları al
            slow_queries = self.analyzer.get_slow_queries_profile(threshold_ms)
            
            # Sonucu formatla
            result = {
                "threshold_ms": threshold_ms,
                "query_count": len(slow_queries),
                "queries": slow_queries
            }
            
            # Açıklama oluştur
            if slow_queries:
                desc = f"{threshold_ms}ms'den uzun süren {len(slow_queries)} sorgu bulundu:\n"
                for i, query in enumerate(slow_queries[:5], 1):  # İlk 5 sorgu
                    desc += f"\n{i}. {query['operation']} - {query['namespace']}"
                    desc += f" ({query['duration_ms']}ms)"
                    if query['docs_examined'] > 0:
                        desc += f" - {query['docs_examined']} doküman tarandı"
            else:
                desc = f"{threshold_ms}ms'den uzun süren sorgu bulunamadı."
            
            formatted_result = {
                "durum": "başarılı",
                "işlem": "slow_query_analysis",
                "açıklama": desc,
                "sonuç": result
            }
            
            return json.dumps(formatted_result, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Slow query analysis hatası: {e}")
            return self._format_result({"error": str(e)}, "slow_query_analysis")


def create_performance_tools(db_connector=None) -> List[Tool]:
    """Performance tool'larını oluştur"""
    
    performance = PerformanceTools(db_connector)
    
    tools = [
        Tool(
            name="analyze_query_performance",
            description="""MongoDB sorgusunun performansını analiz et.
            Argüman: {
                "collection": "koleksiyon_adı",
                "query": {sorgu},
                "operation": "find|aggregate",
                "options": {"limit": 10, "sort": {"field": 1}}
            }
            Örnek: {"collection": "products", "query": {"price": {"$gt": 100}}, "operation": "find"}""",
            func=performance.analyze_query_performance
        ),
        
        Tool(
            name="get_slow_queries", 
            description="""Yavaş çalışan sorguları listele.
            Argüman: {"threshold_ms": 100}
            Örnek: {"threshold_ms": 500} - 500ms'den uzun süren sorguları göster""",
            func=performance.get_slow_queries
        )
    ]
    
    return tools