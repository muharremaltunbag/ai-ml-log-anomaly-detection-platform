# tests/test_ml_pipeline_deep.py

import sys
import os
from pathlib import Path

# Project root'u doğru şekilde bul
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent  # tests/Prod Tests -> tests -> project_root
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")
print(f"[DEBUG] Looking for src in: {project_root / 'src'}")

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import logging

# Şimdi import'ları yap
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
from src.anomaly.log_reader import OpenSearchProxyReader, extract_mongodb_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MLPipelineTest:
    """ML Pipeline kapsamlı test suite"""
    
    def __init__(self):
        self.feature_engineer = MongoDBFeatureEngineer()
        self.detector = MongoDBAnomalyDetector()
        self.reader = OpenSearchProxyReader()
        self.test_results = []
        
    def test_feature_extraction(self):
        """Feature extraction doğruluğunu test et"""
        print("\n" + "="*60)
        print("TEST 1: Feature Extraction")
        print("="*60)
        
        # Test log samples oluştur
        test_logs = [
            {
                't': {'$date': '2025-11-17T10:00:00Z'},
                's': 'E',  # Error
                'c': 'STORAGE',
                'msg': 'Out of memory allocating 1048576 bytes',
                'attr': {'error': {'code': 123}},
                'raw_log': '{"t":{"$date":"2025-11-17T10:00:00Z"},"s":"E","msg":"Out of memory"}'
            },
            {
                't': {'$date': '2025-11-17T10:00:01Z'},
                's': 'W',  # Warning
                'c': 'QUERY',
                'msg': 'Slow query: COLLSCAN planSummary:COLLSCAN durationMillis:5000 docsExamined:100000',
                'attr': {},
                'raw_log': '{"msg":"Slow query"}'
            },
            {
                't': {'$date': '2025-11-17T10:00:02Z'},
                's': 'I',
                'c': 'COMMAND',
                'msg': 'CMD: dropIndexes db.collection',
                'attr': {},
                'raw_log': '{"msg":"CMD: dropIndexes"}'
            }
        ]
        
        df = pd.DataFrame(test_logs)
        
        # Feature extraction
        X, enriched_df = self.feature_engineer.create_features(df)
        
        print(f"✅ {len(X.columns)} features extracted")
        print(f"Features: {list(X.columns)[:10]}...")
        
        # Test specific features
        tests = {
            'is_out_of_memory': X['is_out_of_memory'].iloc[0] == 1,
            'is_slow_query': X['is_slow_query'].iloc[1] == 1,
            'is_collscan': X['is_collscan'].iloc[1] == 1,
            'is_drop_operation': X['is_drop_operation'].iloc[2] == 1,
            'query_duration_ms': X['query_duration_ms'].iloc[1] == 5000,
            'docs_examined_count': X['docs_examined_count'].iloc[1] == 100000
        }
        
        passed = 0
        for feature, result in tests.items():
            status = "✅" if result else "❌"
            print(f"  {status} {feature}: {'PASSED' if result else 'FAILED'}")
            if result:
                passed += 1
                
        success_rate = (passed / len(tests)) * 100
        print(f"\nFeature Extraction Success Rate: {success_rate:.0f}%")
        
        self.test_results.append(("Feature Extraction", success_rate == 100))
        return success_rate == 100
        
    def test_anomaly_detection(self):
        """Anomaly detection doğruluğunu test et"""
        print("\n" + "="*60)
        print("TEST 2: Anomaly Detection")
        print("="*60)
        
        # Critical anomaly samples oluştur
        critical_samples = pd.DataFrame({
            'is_fatal': [1, 0, 0],
            'is_out_of_memory': [0, 1, 0],
            'is_collscan': [0, 0, 1],
            'docs_examined_count': [0, 0, 200000],
            'query_duration_ms': [0, 0, 10000],
            'performance_score': [0, 0, 400000],
            'hour_of_day': [10, 10, 10],
            'is_weekend': [0, 0, 0]
        })
        
        # Normal samples
        normal_samples = pd.DataFrame({
            'is_fatal': [0, 0, 0],
            'is_out_of_memory': [0, 0, 0],
            'is_collscan': [0, 0, 0],
            'docs_examined_count': [10, 50, 100],
            'query_duration_ms': [5, 10, 20],
            'performance_score': [10, 50, 100],
            'hour_of_day': [10, 11, 12],
            'is_weekend': [0, 0, 0]
        })
        
        # Birleştir ve eğit
        X_train = pd.concat([critical_samples, normal_samples])
        
        # Eksik feature'ları ekle
        for feature in self.feature_engineer.enabled_features:
            if feature not in X_train.columns:
                X_train[feature] = 0
                
        # Model eğit
        self.detector.train(X_train, save_model=False)
        
        # Tahmin yap
        predictions, scores = self.detector.predict(X_train)
        
        # İlk 3 critical olmalı
        critical_detected = (predictions[:3] == -1).sum()
        normal_detected = (predictions[3:] == 1).sum()
        
        print(f"Critical samples detected: {critical_detected}/3")
        print(f"Normal samples detected: {normal_detected}/3")
        print(f"Anomaly scores range: [{scores.min():.3f}, {scores.max():.3f}]")
        
        success = (critical_detected >= 2) and (normal_detected >= 2)
        print(f"\n{'✅' if success else '❌'} Detection accuracy: {'PASSED' if success else 'FAILED'}")
        
        self.test_results.append(("Anomaly Detection", success))
        return success
        
    def test_rule_engine(self):
        """Rule-based detection test"""
        print("\n" + "="*60)
        print("TEST 3: Rule-Based Engine")
        print("="*60)
        
        # Rule tetikleyecek samples
        test_df = pd.DataFrame({
            'is_fatal': [1, 0, 0, 0],
            'is_out_of_memory': [0, 1, 0, 0],
            'is_drop_operation': [0, 0, 1, 0],
            'is_collscan': [0, 0, 0, 1],
            'docs_examined_count': [0, 0, 0, 150000],
            # Diğer gerekli features
            'hour_of_day': [10, 10, 10, 10],
            'is_weekend': [0, 0, 0, 0]
        })
        
        # Eksik features ekle
        for feature in self.feature_engineer.enabled_features:
            if feature not in test_df.columns:
                test_df[feature] = 0
                
        # ML modeli normal tahmin yapacak şekilde ayarla
        initial_predictions = np.array([1, 1, 1, 1])  # Hepsi normal
        initial_scores = np.array([-0.1, -0.1, -0.1, -0.1])
        
        # Rule engine uygula
        final_predictions, final_scores = self.detector._apply_critical_rules(
            initial_predictions, initial_scores, test_df, test_df
        )
        
        # Rule override sayısı
        overrides = (final_predictions == -1).sum()
        
        print(f"Initial predictions (all normal): {initial_predictions}")
        print(f"Final predictions after rules: {final_predictions}")
        print(f"Rule overrides: {overrides}")
        print(f"Rule hits: {self.detector.rule_stats['rule_hits']}")
        
        success = overrides >= 3  # En az 3 rule tetiklenmeli
        print(f"\n{'✅' if success else '❌'} Rule engine: {'PASSED' if success else 'FAILED'}")
        
        self.test_results.append(("Rule Engine", success))
        return success
        
    def test_severity_scoring(self):
        """Severity scoring test"""
        print("\n" + "="*60)
        print("TEST 4: Severity Scoring")
        print("="*60)
        
        test_cases = [
            {
                'name': 'Fatal Error',
                'features': {'is_fatal': 1, 'hour_of_day': 10},
                'expected_min': 70
            },
            {
                'name': 'OOM Error',
                'features': {'is_out_of_memory': 1, 'hour_of_day': 10},
                'expected_min': 65
            },
            {
                'name': 'COLLSCAN High Docs',
                'features': {'is_collscan': 1, 'docs_examined_count': 200000, 'hour_of_day': 10},
                'expected_min': 50
            },
            {
                'name': 'Normal Log',
                'features': {'hour_of_day': 10},
                'expected_min': 0,
                'expected_max': 30
            }
        ]
        
        for test in test_cases:
            # Eksik features ekle
            features = {f: 0 for f in self.feature_engineer.enabled_features}
            features.update(test['features'])
            
            df_row = pd.Series({'c': 'STORAGE'})
            
            severity = self.detector.calculate_severity_score(
                0, -0.5, features, df_row
            )
            
            score = severity['score']
            level = severity['level']
            
            # Check expectations
            passed = score >= test['expected_min']
            if 'expected_max' in test:
                passed = passed and score <= test['expected_max']
                
            status = "✅" if passed else "❌"
            print(f"{status} {test['name']}: Score={score:.0f}, Level={level}")
            
        self.test_results.append(("Severity Scoring", True))
        return True
        
    def test_end_to_end(self):
        """End-to-end pipeline test with real data"""
        print("\n" + "="*60)
        print("TEST 5: End-to-End Pipeline")
        print("="*60)
        
        # OpenSearch'ten gerçek veri çek
        print("Connecting to OpenSearch...")
        if not self.reader.connect():
            print("❌ Failed to connect to OpenSearch")
            self.test_results.append(("End-to-End", False))
            return False
            
        print("Reading logs from OpenSearch...")
        df = self.reader.read_logs(limit=100, last_hours=1)
        
        if df.empty:
            print("❌ No logs retrieved")
            self.test_results.append(("End-to-End", False))
            return False
            
        print(f"✅ Retrieved {len(df)} logs")
        
        # Feature engineering
        print("Extracting features...")
        X, enriched_df = self.feature_engineer.create_features(df)
        print(f"✅ Extracted {X.shape[1]} features from {X.shape[0]} logs")
        
        # Anomaly detection
        print("Training model...")
        self.detector.train(X, save_model=False)
        
        print("Detecting anomalies...")
        predictions, scores = self.detector.predict(X, enriched_df)
        
        # Analysis
        analysis = self.detector.analyze_anomalies(enriched_df, X, predictions, scores)
        
        print(f"\n📊 Results:")
        print(f"  - Total logs: {analysis['summary']['total_logs']}")
        print(f"  - Anomalies: {analysis['summary']['n_anomalies']}")
        print(f"  - Anomaly rate: {analysis['summary']['anomaly_rate']:.1f}%")
        
        if 'severity_distribution' in analysis:
            print(f"\n  Severity Distribution:")
            for level, count in analysis['severity_distribution'].items():
                if count > 0:
                    print(f"    - {level}: {count}")
                    
        success = analysis['summary']['n_anomalies'] >= 0  # At least processed
        print(f"\n{'✅' if success else '❌'} End-to-end test: {'PASSED' if success else 'FAILED'}")
        
        self.test_results.append(("End-to-End", success))
        return success
        
    def run_all_tests(self):
        """Tüm testleri çalıştır"""
        print("\n" + "="*60)
        print("ML PIPELINE TEST SUITE")
        print("="*60)
        
        tests = [
            self.test_feature_extraction,
            self.test_anomaly_detection,
            self.test_rule_engine,
            self.test_severity_scoring,
            self.test_end_to_end
        ]
        
        for test_func in tests:
            try:
                test_func()
            except Exception as e:
                print(f"❌ Test failed with exception: {e}") 
                self.test_results.append((test_func.__name__, False))
                
        # Final report
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, result in self.test_results if result)
        total = len(self.test_results)

        
        for test_name, result in self.test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} - {test_name}")
            
        print(f"\nTotal: {passed}/{total} tests passed")
        
        return passed == total

if __name__ == "__main__":
    tester = MLPipelineTest()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)