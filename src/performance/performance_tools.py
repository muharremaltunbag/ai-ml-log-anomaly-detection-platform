# src\performance\performance_tools.py

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
                    "sonuç": {}
                }, ensure_ascii=False, indent=2)
            
            # Başarılı sonuç formatla
            formatted = {
                "durum": "başarılı",
                "işlem": operation,
                "koleksiyon": result.get("collection", ""),
                "açıklama": self._generate_enhanced_description(result),  # GELİŞTİRİLMİŞ
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
    
    def _create_progress_bar(self, value: float, max_value: float = 100, width: int = 20) -> str:
        """ASCII progress bar oluştur - YENİ"""
        percentage = min(100, (value / max_value) * 100)
        filled = int((percentage / 100) * width)
        empty = width - filled
        
        bar = "█" * filled + "░" * empty
        return f"{bar} {percentage:.0f}%"
    
    def _format_execution_tree(self, tree: Dict, indent: int = 0) -> List[str]:
        """Execution tree'yi formatla - YENİ"""
        lines = []
        prefix = "  " * indent
        
        # Stage bilgisi
        stage_name = tree.get("stage", "UNKNOWN")
        stage_emoji = {
            "COLLSCAN": "🔴",
            "IXSCAN": "🟢",
            "FETCH": "🔵",
            "SORT": "🟡",
            "COUNT": "🟣",
            "UNKNOWN": "⚪"
        }.get(stage_name, "⚪")
        
        # Stage satırı
        stage_line = f"{prefix}{stage_emoji} {stage_name}"
        if tree.get("index_name"):
            stage_line += f" ({tree['index_name']})"
        if tree.get("stage_info"):
            stage_line += f" - {tree['stage_info']}"
        lines.append(stage_line)
        
        # Metrikler
        if tree.get("docs_examined", 0) > 0 or tree.get("keys_examined", 0) > 0:
            metrics_line = f"{prefix}  📊 Docs: {tree['docs_examined']:,} | Keys: {tree['keys_examined']:,}"
            if tree.get("execution_time", 0) > 0:
                metrics_line += f" | Time: {tree['execution_time']}ms"
            lines.append(metrics_line)
        
        # Alt stage'ler
        for child in tree.get("children", []):
            lines.extend(self._format_execution_tree(child, indent + 1))
        
        return lines
    
    def _format_improvement_estimate(self, improvement: Dict) -> List[str]:
        """İyileştirme tahminini formatla - YENİ"""
        lines = []
        
        if not improvement:
            return lines
        
        current_time = improvement.get("current_time_ms", 0)
        estimated_time = improvement.get("estimated_time_ms", 0)
        improvement_percent = improvement.get("improvement_percent", 0)
        
        lines.append("\n🚀 İYİLEŞTİRME TAHMİNİ:")
        lines.append("━" * 40)
        
        # Zaman karşılaştırması
        lines.append(f"⏱️  Mevcut Süre:    {current_time}ms")
        lines.append(f"⚡ Tahmini Süre:   {estimated_time:.1f}ms")
        lines.append(f"📈 İyileşme:       %{improvement_percent}")
        
        # Görsel ilerleme
        if improvement_percent > 0:
            before_bar = self._create_progress_bar(100, 100, 15)
            after_bar = self._create_progress_bar(100 - improvement_percent, 100, 15)
            lines.append(f"\nÖnce:  {before_bar}")
            lines.append(f"Sonra: {after_bar}")
        
        # Doküman tarama iyileştirmesi
        if "docs_examined_reduction" in improvement:
            reduction = improvement["docs_examined_reduction"]
            if reduction > 0:
                lines.append(f"\n📉 {reduction:,} daha az doküman taranacak")
        
        return lines
    
    def _generate_enhanced_description(self, result: Dict[str, Any]) -> str:
        """Geliştirilmiş analiz açıklaması - YENİ"""
        desc_parts = []
        
        # BAŞLIK
        desc_parts.append("📊 QUERY PERFORMANCE ANALİZİ")
        desc_parts.append("=" * 50)
        
        # 1. PERFORMANS SKORU
        if "performance_score" in result:
            score_info = result["performance_score"]
            score = score_info["score"]
            level = score_info["level"]
            
            # Ana skor
            desc_parts.append(f"\n⚡ PERFORMANS SKORU: {self._create_progress_bar(score)}")
            desc_parts.append(f"   Seviye: {level} ({score}/100)")
            
            # Detaylı skorlar
            if "detailed_scores" in score_info:
                desc_parts.append("\n📈 Detaylı Skorlar:")
                scores = score_info["detailed_scores"]
                desc_parts.append(f"   • Zaman:         {self._create_progress_bar(scores.get('time', 0), 30, 10)} ({scores.get('time', 0)}/30)")
                desc_parts.append(f"   • Verimlilik:    {self._create_progress_bar(scores.get('efficiency', 0), 30, 10)} ({scores.get('efficiency', 0)}/30)")
                desc_parts.append(f"   • Index:         {self._create_progress_bar(scores.get('index', 0), 25, 10)} ({scores.get('index', 0)}/25)")
                desc_parts.append(f"   • Sonuç Boyutu:  {self._create_progress_bar(scores.get('result_size', 0), 15, 10)} ({scores.get('result_size', 0)}/15)")
            
            # Tespit edilen sorunlar
            if score_info.get("reasons"):
                desc_parts.append("\n⚠️  Tespit Edilen Sorunlar:")
                for reason in score_info["reasons"]:
                    desc_parts.append(f"   • {reason}")
        
        # 2. EXECUTION İSTATİSTİKLERİ
        if "execution_stats" in result:
            stats = result["execution_stats"]
            desc_parts.append(f"\n📊 EXECUTION METRİKLERİ:")
            desc_parts.append("─" * 40)
            desc_parts.append(f"⏱️  Çalışma Süresi:     {stats['execution_time_ms']}ms")
            desc_parts.append(f"📄 Taranan Doküman:    {stats['total_docs_examined']:,}")
            desc_parts.append(f"🔑 Taranan Index Key:  {stats['total_keys_examined']:,}")
            desc_parts.append(f"✅ Dönen Doküman:      {stats['docs_returned']:,}")
            
            # Verimlilik - YENİ
            efficiency = stats.get("efficiency_percent", 0)
            desc_parts.append(f"📈 Verimlilik:         {self._create_progress_bar(efficiency, 100, 15)} %{efficiency}")
        
        # 3. EXECUTION PLAN
        if "execution_tree" in result:
            desc_parts.append(f"\n🔍 EXECUTION PLAN:")
            desc_parts.append("─" * 40)
            tree_lines = self._format_execution_tree(result["execution_tree"])
            desc_parts.extend(tree_lines)
        elif "winning_plan" in result:
            # Eski format için fallback
            plan = result["winning_plan"]
            desc_parts.append(f"\n🔍 EXECUTION PLAN:")
            if plan["index_used"]:
                desc_parts.append(f"   🟢 Index kullanılıyor: {plan['index_name']}")
            else:
                desc_parts.append("   🔴 Index kullanılmıyor (Collection Scan)")
        
        # 4. İYİLEŞTİRME TAHMİNİ - YENİ
        if "improvement_estimate" in result:
            improvement_lines = self._format_improvement_estimate(result["improvement_estimate"])
            desc_parts.extend(improvement_lines)
        
        return "\n".join(desc_parts)
    
    def _generate_description(self, result: Dict[str, Any]) -> str:
        """Eski format için backward compatibility"""
        # Eğer yeni özellikler yoksa eski formatı kullan
        if not any(key in result for key in ["execution_tree", "improvement_estimate"]):
            return self._generate_old_description(result)
        # Yeni özellikler varsa geliştirilmiş formatı kullan
        return self._generate_enhanced_description(result)
    
    def _generate_old_description(self, result: Dict[str, Any]) -> str:
        """Eski format - backward compatibility için"""
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
        """Önerileri Türkçe formatla - GELİŞTİRİLMİŞ"""
        formatted = []
        
        if not recommendations:
            return formatted
        
        # Öncelik sırasına göre sırala
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_recs = sorted(recommendations, 
                           key=lambda x: priority_order.get(x.get("priority", "low"), 3))
        
        # Öneri başlığı
        formatted.append("\n💡 ÖNERİLER:")
        formatted.append("─" * 40)
        
        for rec in sorted_recs:
            priority = rec.get("priority", "low")
            priority_emoji = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "💡",
                "low": "ℹ️"
            }.get(priority, "")
            
            # Öneri tipi başlığı
            rec_type = rec.get("type", "general")
            type_label = {
                "index": "INDEX",
                "index_suggestion": "INDEX ÖNERİSİ",
                "performance": "PERFORMANS",
                "efficiency": "VERİMLİLİK"
            }.get(rec_type, "GENEL")
            
            formatted.append(
                f"{priority_emoji} [{priority.upper()} - {type_label}] {rec['message']}"
            )
            if rec.get('detail'):
                formatted.append(f"   📝 {rec['detail']}")
        
        return formatted
    
    def _handle_performance_args(self, *args, **kwargs) -> Dict[str, Any]:
        """Agent'tan gelen farklı argüman formatlarını handle et - YENİ"""
        # Eğer tek dict argüman geldiyse
        if len(args) == 1 and isinstance(args[0], dict):
            return args[0]
        
        # Eğer birden fazla argüman geldiyse
        elif len(args) >= 1:
            # İlk 4 argümanı al: collection, query, operation, options
            result = {
                "collection": args[0] if len(args) > 0 else "",
                "query": args[1] if len(args) > 1 else {},
                "operation": args[2] if len(args) > 2 else "find",
                "options": args[3] if len(args) > 3 else {}
            }
            return result
        
        # kwargs varsa kullan
        elif kwargs:
            return kwargs
        
        # Boş dict dön
        return {}
    
    def analyze_query_performance(self, *args, **kwargs) -> str:
        """Sorgu performansını analiz et - GÜNCELLENMİŞ"""
        try:
            # Önce argümanları normalize et
            if len(args) == 1 and not kwargs:
                # Tek argüman durumu (eski format)
                args_input = args[0]
                
                # String ise parse et
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
            else:
                # Birden fazla argüman durumu (yeni format)
                args_dict = self._handle_performance_args(*args, **kwargs)
            
            # Debug log
            logger.info(f"Performance analysis args: {args_dict}")
            
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
            logger.error(f"Query performance analysis hatası: {e}", exc_info=True)
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
                desc = f"⏱️ {threshold_ms}ms'den uzun süren {len(slow_queries)} sorgu bulundu:\n"
                desc += "─" * 40 + "\n"
                for i, query in enumerate(slow_queries[:5], 1):  # İlk 5 sorgu
                    duration = query['duration_ms']
                    # Süreye göre emoji
                    time_emoji = "🔴" if duration > 1000 else "🟡" if duration > 500 else "🟢"
                    
                    desc += f"\n{i}. {time_emoji} {query['operation']} - {query['namespace']}"
                    desc += f" ({duration}ms)"
                    if query['docs_examined'] > 0:
                        desc += f"\n   📄 {query['docs_examined']:,} doküman tarandı"
            else:
                desc = f"✅ {threshold_ms}ms'den uzun süren sorgu bulunamadı."
            
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