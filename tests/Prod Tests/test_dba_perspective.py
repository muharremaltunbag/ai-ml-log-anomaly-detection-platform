# tests/test_dba_perspective.py

import sys
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")

from src.anomaly.log_reader import OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
import pandas as pd
import re

class DBAFunctionalTest:
    """DBA perspektifinden fonksiyonel test"""
    
    def __init__(self):
        self.reader = OpenSearchProxyReader()
        self.fe = MongoDBFeatureEngineer()
        self.detector = MongoDBAnomalyDetector()
        
        # DBA'nin arayacağı kritik pattern'ler
        self.critical_patterns = {
            "OOM": r"Out of memory|OOM|memory allocation failed",
            "AUTH_FAIL": r"Authentication failed|Unauthorized",
            "COLLSCAN": r"COLLSCAN|planSummary.*COLLSCAN",
            "SLOW_QUERY": r"Slow query|durationMillis:[1-9]\d{4}",
            "SHUTDOWN": r"shutdown|dbexit|stopping",
            "ASSERTION": r"assertion|assert|invariant",
            "FATAL": r"fatal|FATAL|Fatal",
            "REPL_LAG": r"replication lag|behind|cannot keep up"
        }
        
    def test_critical_pattern_detection(self):
        """Kritik pattern'lerin yakalanma testi"""

        print("\n" + "="*60)
        print("DBA CRITICAL PATTERN DETECTION TEST")
        print("="*60)

        # 1. OpenSearch bağlantısı
        if not self.reader.connect():
            print("❌ Cannot connect to OpenSearch")
            return False

        # 2. Son 24 saatteki logları çek
        print("\n[1] Fetching last 24 hours of logs...")
        df_all = self.reader.read_logs(limit=5000, last_hours=24)

        if df_all.empty:
            print("❌ No logs retrieved")
            return False

        print(f"✅ Retrieved {len(df_all)} logs")

        # 3. DBA pattern analizi (ML öncesi)
        print("\n[2] DBA Pattern Analysis (Manual Check)...")
        dba_findings = self._analyze_with_dba_patterns(df_all)

        # 4. ML Pipeline
        print("\n[3] ML Pipeline Analysis...")
        X, enriched_df = self.fe.create_features(df_all)
        X_filtered, enriched_filtered = self.fe.apply_filters(enriched_df, X)

        # ⭐ YENİ: Feature matrix temizleme
        print("   Cleaning feature matrix...")
        enabled_features = self.fe.enabled_features
        X_clean = X_filtered[enabled_features].copy()
        for col in X_clean.columns:
            if X_clean[col].apply(lambda x: isinstance(x, dict)).any():
                print(f"   ⚠️ Removing dict column: {col}")
                X_clean = X_clean.drop(columns=[col])
        X_clean = X_clean.fillna(0)
        X_clean = X_clean.astype(float)
        print(f"   ✅ Clean features: {X_clean.shape}")

        # Model train - TEMİZ veri ile
        self.detector.train(X_clean, save_model=False, incremental=False)

        # Predict
        predictions, scores = self.detector.predict(X_clean, enriched_filtered)

        # Anomaly analysis
        analysis = self.detector.analyze_anomalies(
            enriched_filtered, X_clean, predictions, scores
        )

        # 5. Karşılaştırma
        print("\n[4] COMPARISON: DBA vs ML System")
        print("="*60)

        comparison_results = self._compare_findings(
            dba_findings, 
            analysis, 
            enriched_filtered[predictions == -1]
        )

        # 6. Detaylı Sonuç Raporu
        print("\n" + "="*60)
        print("📊 DETAILED RESULTS")
        print("="*60)

        # ML bulguları
        print(f"\n🤖 ML System Found:")
        print(f"  • Total anomalies: {analysis['summary']['n_anomalies']}")
        print(f"  • Anomaly rate: {analysis['summary']['anomaly_rate']:.1f}%")

        # Severity dağılımı
        if 'severity_distribution' in analysis:
            print(f"\n📈 Severity Distribution:")
            for level, count in analysis['severity_distribution'].items():
                if count > 0:
                    print(f"    {level}: {count}")

        # Top anomaliler
        if analysis.get('critical_anomalies'):
            print(f"\n🔴 Top 5 Critical Anomalies (by ML):")
            for i, anomaly in enumerate(analysis['critical_anomalies'][:5], 1):
                msg = anomaly.get('message', '')[:100]
                severity = anomaly.get('severity_level', 'N/A')
                score = anomaly.get('severity_score', 0)
                print(f"  {i}. [{severity}] (Score: {score:.0f}) {msg}...")

        # Performance issues
        if analysis.get('performance_alerts'):
            print(f"\n⚡ Performance Issues Detected:")
            for alert, data in analysis['performance_alerts'].items():
                if data['count'] > 0:
                    print(f"    • {alert}: {data['count']}")

        return comparison_results
        
    def _analyze_with_dba_patterns(self, df):
        """DBA pattern'leri ile manuel analiz"""
        findings = {
            "total_logs": len(df),
            "critical_findings": {},
            "pattern_counts": {}
        }
        
        for pattern_name, pattern_regex in self.critical_patterns.items():
            # msg field'ında pattern ara
            if 'msg' in df.columns:
                matches = df['msg'].str.contains(
                    pattern_regex, 
                    regex=True, 
                    case=False, 
                    na=False
                )
                count = matches.sum()
                
                if count > 0:
                    findings["pattern_counts"][pattern_name] = count
                    findings["critical_findings"][pattern_name] = {
                        "count": count,
                        "sample_logs": df[matches]['msg'].head(3).tolist()
                    }
                    
        print(f"\nDBA Manual Findings:")
        for pattern, count in findings["pattern_counts"].items():
            print(f"  • {pattern}: {count} occurrences")
            
        return findings
        
    def _compare_findings(self, dba_findings, ml_analysis, ml_anomalies_df):
        """DBA bulguları ile ML bulgularını karşılaştır - DÜZELTILMIŞ"""
        
        results = {
            "dba_found": len(dba_findings["critical_findings"]),
            "ml_found": ml_analysis["summary"]["n_anomalies"],
            "match_analysis": {}
        }
        
        # ⭐ DÜZELTME: ml_anomalies_df direkt enriched_filtered[anomaly_mask]
        # Ama burada msg sütunu YOK olabilir! Doğrudan analysis'ten alalım
        
        # Critical anomalies listesinden çek
        ml_messages = []
        if 'critical_anomalies' in ml_analysis:
            ml_messages = [a.get('message', '') for a in ml_analysis['critical_anomalies']]
        
        # Performance alerts'ten de bilgi al
        performance_info = ml_analysis.get('performance_alerts', {})
        security_info = ml_analysis.get('security_alerts', {})
        
        # Her DBA pattern'i için kontrol
        for pattern_name, pattern_data in dba_findings["critical_findings"].items():
            dba_count = pattern_data["count"]
            
            # ML yakaladı mı?
            ml_caught = 0
            
            if pattern_name == "AUTH_FAIL":
                # Analysis'teki AUTH_FAIL sayısını al
                # Feature extraction'da kaç tane var?
                if not ml_anomalies_df.empty and 'is_auth_failure' in ml_anomalies_df.columns:
                    ml_caught = ml_anomalies_df['is_auth_failure'].sum()
                    
            elif pattern_name == "SLOW_QUERY":
                # Performance alerts'ten al
                if 'slow_queries' in performance_info:
                    ml_caught = performance_info['slow_queries']['count']
                # Veya feature'dan
                elif not ml_anomalies_df.empty and 'is_slow_query' in ml_anomalies_df.columns:
                    ml_caught = ml_anomalies_df['is_slow_query'].sum()
                    
            elif pattern_name == "COLLSCAN":
                if 'collscan' in performance_info:
                    ml_caught = performance_info['collscan']['count']
                    
            # Diğer pattern'ler için de benzer mantık...
            
            catch_rate = (ml_caught / dba_count * 100) if dba_count > 0 else 0
            
            results["match_analysis"][pattern_name] = {
                "dba_found": dba_count,
                "ml_caught": ml_caught,
                "catch_rate": catch_rate
            }
            
            # Sonucu yazdır
            status = "✅" if catch_rate >= 80 else "⚠️" if catch_rate >= 50 else "❌"
            print(f"{status} {pattern_name}: DBA found {dba_count}, ML caught {ml_caught} ({catch_rate:.0f}%)")
        
        # Debug bilgisi ekle
        print(f"\n🔍 DEBUG INFO:")
        print(f"  Total ML anomalies: {ml_analysis['summary']['n_anomalies']}")
        if 'severity_distribution' in ml_analysis:
            print(f"  Severity distribution: {ml_analysis['severity_distribution']}")
        if performance_info:
            print(f"  Performance alerts: {list(performance_info.keys())}")
        
        return results

if __name__ == "__main__":
    tester = DBAFunctionalTest()
    tester.test_critical_pattern_detection()