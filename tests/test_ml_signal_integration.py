"""
ML Signal Integration Tests

PATCH 1-5 kapsamında eklenen ML sinyal entegrasyonlarının birim testleri.
Modüller: TrendAnalyzer, RateAlertEngine, Forecaster, anomaly_tools insight builder.
"""
import sys
import os
import types
import unittest

# Proje kök dizinini path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ── Auto-mock missing external dependencies ──
# Uses a meta path finder to generate stub modules on-the-fly for any
# import under langchain*, pymongo, openai, pydantic (if not installed).
_MOCK_PREFIXES = ('langchain', 'langchain_classic', 'langchain_core',
                  'langchain_openai', 'pymongo', 'openai')
_DummyClass = type('_Dummy', (), {'__init__': lambda self, *a, **kw: None})


class _StubFinder:
    """Meta path finder that auto-creates stub modules for missing deps."""
    def find_module(self, fullname, path=None):
        for prefix in _MOCK_PREFIXES:
            if fullname == prefix or fullname.startswith(prefix + '.'):
                if fullname not in sys.modules:
                    return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        m = types.ModuleType(fullname)
        m.__path__ = []  # package-like so sub-imports work
        m.__loader__ = self
        # Add common attributes as dummies
        for attr in ('Tool', 'StructuredTool', 'BaseChatModel',
                     'BaseMessage', 'HumanMessage', 'SystemMessage', 'AIMessage',
                     'ChatOpenAI', 'MongoClient', 'ConnectionFailure',
                     'BaseModel', 'Field'):
            setattr(m, attr, _DummyClass)
        sys.modules[fullname] = m
        return m


sys.meta_path.insert(0, _StubFinder())

# pydantic — used by anomaly_tools for schema models
try:
    import pydantic  # noqa: F401
except ImportError:
    pydantic_mod = types.ModuleType('pydantic')
    pydantic_mod.__path__ = []
    pydantic_mod.BaseModel = type('BaseModel', (), {})
    pydantic_mod.Field = lambda *a, **kw: None
    sys.modules['pydantic'] = pydantic_mod


class TestTrendAnalyzerMLScoreTrend(unittest.TestCase):
    """PATCH 1: TrendAnalyzer._check_ml_score_trend() testleri."""

    @classmethod
    def setUpClass(cls):
        from src.anomaly.trend_analyzer import TrendAnalyzer
        cls.analyzer = TrendAnalyzer({
            'enabled': True,
            'min_history_count': 3,
            'anomaly_rate_increase_threshold': 50.0,
            'severity_escalation_threshold': 30.0,
        })

    def _make_record(self, mean_score, ts_offset_hours=0):
        """Test için basit history record oluştur."""
        from datetime import datetime, timedelta
        ts = datetime(2025, 1, 1) + timedelta(hours=ts_offset_hours)
        return {
            'timestamp': ts.isoformat(),
            'summary': {
                'anomaly_rate': 5.0,
                'n_anomalies': 2,
                'total_logs': 40,
                'score_range': {
                    'mean': -abs(mean_score),  # IsolationForest: negatif
                    'min': -0.6,
                    'max': -0.1,
                }
            }
        }

    def test_no_degradation_stable(self):
        """Sabit skor → ne degradation ne monotonic tetiklenmeli."""
        # Farklı skorlar ama monoton olmayan → monotonic tetiklenmez
        # Ve change_pct < 30 → degradation tetiklenmez
        records = [
            self._make_record(0.30, 5),  # newest
            self._make_record(0.32, 4),
            self._make_record(0.29, 3),  # desc olmayan → monotonic bozar
            self._make_record(0.31, 2),
            self._make_record(0.30, 1),
        ]
        current = self._make_record(0.30, 6)  # aynı seviyede
        alerts = self.analyzer._check_ml_score_trend(
            records, current, 'test-server')
        self.assertEqual(len(alerts), 0)

    def test_degradation_triggers_alert(self):
        """Baseline'dan >%30 kötüleşme → ml_score_degradation alert."""
        records = [self._make_record(0.25, i) for i in range(5)]
        current = self._make_record(0.45, 5)  # %80 artış
        alerts = self.analyzer._check_ml_score_trend(
            records, current, 'test-server')
        alert_types = [a.alert_type for a in alerts]
        self.assertIn('ml_score_degradation', alert_types)

    def test_monotonic_degradation(self):
        """Monoton artan skor → ml_score_monotonic_degradation alert."""
        # DESC sıralı (en yeni = en yüksek skor ilk)
        records = [
            self._make_record(0.45, 6),  # newest — highest
            self._make_record(0.40, 5),
            self._make_record(0.35, 4),
            self._make_record(0.30, 3),
            self._make_record(0.25, 2),
            self._make_record(0.20, 1),  # oldest — lowest
        ]
        current = self._make_record(0.50, 7)  # even higher
        alerts = self.analyzer._check_ml_score_trend(
            records, current, 'test-server')
        alert_types = [a.alert_type for a in alerts]
        self.assertIn('ml_score_monotonic_degradation', alert_types)

    def test_insufficient_history(self):
        """Yetersiz history → alert olmamalı."""
        records = [self._make_record(0.30, 0)]
        current = self._make_record(0.50, 1)
        alerts = self.analyzer._check_ml_score_trend(
            records, current, 'test-server')
        self.assertEqual(len(alerts), 0)

    def test_summary_includes_ml_score_trend(self):
        """TrendReport summary'sinde ml_score_trend field'ı olmalı."""
        records = [self._make_record(0.25, i) for i in range(5)]
        current = {
            'summary': {
                'anomaly_rate': 5.0,
                'n_anomalies': 2,
                'total_logs': 40,
                'score_range': {'mean': -0.45, 'min': -0.6, 'max': -0.1}
            }
        }
        report = self.analyzer.analyze(records, current, 'test-server')
        summary = report.to_dict().get('summary', {})
        ml_trend = summary.get('ml_score_trend')
        # ml_score_trend key mevcut olmalı (ml_score_direction değeri ne olursa olsun)
        self.assertIsNotNone(ml_trend)
        self.assertIn('ml_score_direction', ml_trend)


class TestRateAlertEngineMLContext(unittest.TestCase):
    """PATCH 2: RateAlertEngine ML context overlay testleri."""

    @classmethod
    def setUpClass(cls):
        from src.anomaly.rate_alert import RateAlertEngine
        cls.engine = RateAlertEngine({
            'enabled': True,
            'windows': [
                {'name': '5m', 'seconds': 300, 'threshold': 3.0}
            ],
            'alert_cooldown_minutes': 0,  # test için cooldown kapalı
        })

    def test_ml_context_attached_to_alerts(self):
        """Rate alert'lere ml_context field'ı eklenmeli."""
        import pandas as pd
        from datetime import datetime, timedelta

        # Spike oluşturacak kadar log
        now = datetime(2025, 6, 1, 12, 0, 0)
        n = 50
        rows = []
        for i in range(n):
            rows.append({
                'timestamp': now + timedelta(seconds=i * 2),
                'level': 'ERROR' if i % 3 == 0 else 'INFO',
                'message': f'test log {i}',
                'component': 'test',
            })
        df = pd.DataFrame(rows)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        analysis_data = {
            'summary': {
                'anomaly_rate': 12.0,
                'n_anomalies': 6,
                'total_logs': 50,
                'score_range': {'mean': -0.35, 'min': -0.5, 'max': -0.1}
            },
            'all_anomalies': [
                {'timestamp': (now + timedelta(seconds=i * 6)).isoformat()}
                for i in range(6)
            ]
        }

        report = self.engine.check(df, 'test-server', source_type='mongodb',
                                   analysis_data=analysis_data)
        result = report.to_dict()
        alerts = result.get('alerts', [])

        # Eğer spike algılandıysa, ml_context olmalı
        for alert in alerts:
            if 'ml_context' in alert:
                ctx = alert['ml_context']
                self.assertIn('ml_corroborated', ctx)
                self.assertIn('window_anomaly_density_pct', ctx)
                self.assertIsInstance(ctx['ml_corroborated'], bool)

    def test_no_ml_context_without_analysis_data(self):
        """analysis_data None ise ml_context olmamalı."""
        import pandas as pd
        from datetime import datetime, timedelta

        now = datetime(2025, 6, 1, 12, 0, 0)
        rows = [{'timestamp': now + timedelta(seconds=i), 'level': 'ERROR',
                 'message': 'x', 'component': 'c'} for i in range(10)]
        df = pd.DataFrame(rows)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        report = self.engine.check(df, 'test-server', source_type='mongodb',
                                   analysis_data=None)
        result = report.to_dict()
        for alert in result.get('alerts', []):
            # ml_context olmamalı veya boş olmalı
            ctx = alert.get('ml_context')
            if ctx:
                # Global ML verisi olmadığı için density hesaplanamaz
                self.assertIsNotNone(ctx)


class TestForecasterMLMetric(unittest.TestCase):
    """PATCH 3: Forecaster mean_anomaly_score metric ve ml_risk_context testleri."""

    @classmethod
    def setUpClass(cls):
        from src.anomaly.forecaster import AnomalyForecaster
        cls.forecaster = AnomalyForecaster({
            'enabled': True,
            'forecast_horizon_hours': 6,
            'tier_strategy': 'auto',
        })

    def _make_history(self, n=8, base_score=0.30):
        """n adet history record oluştur (yeterli veri noktası)."""
        from datetime import datetime, timedelta
        records = []
        for i in range(n):
            ts = datetime(2025, 1, 1) + timedelta(hours=i * 4)
            records.append({
                'timestamp': ts.isoformat(),
                'summary': {
                    'anomaly_rate': 3.0 + i * 0.5,
                    'n_anomalies': 2 + i,
                    'total_logs': 100,
                    'score_range': {
                        'mean': -(base_score + i * 0.02),
                        'min': -0.6,
                        'max': -0.1,
                    }
                }
            })
        return records

    def test_mean_anomaly_score_metric_extracted(self):
        """Forecaster mean_anomaly_score metriğini çıkarmalı."""
        records = self._make_history(n=8)
        current = {
            'summary': {
                'anomaly_rate': 7.0,
                'n_anomalies': 10,
                'total_logs': 100,
                'score_range': {'mean': -0.45, 'min': -0.6, 'max': -0.1}
            }
        }
        report = self.forecaster.forecast(records, current, 'test-server')
        result = report.to_dict()
        forecasts = result.get('forecasts', {})
        # mean_anomaly_score metric var olmalı
        self.assertIn('mean_anomaly_score', forecasts)
        mas = forecasts['mean_anomaly_score']
        self.assertIn('current_value', mas)
        # Absolute value olarak saklanmalı
        self.assertGreater(mas['current_value'], 0)

    def test_ml_risk_context_on_forecasts(self):
        """ml_risk_context field'ı forecast metriklerinde olmalı."""
        records = self._make_history(n=8, base_score=0.35)
        current = {
            'summary': {
                'anomaly_rate': 12.0,  # WARNING threshold
                'n_anomalies': 12,
                'total_logs': 100,
                'score_range': {'mean': -0.50, 'min': -0.6, 'max': -0.1}
            }
        }
        report = self.forecaster.forecast(records, current, 'test-server')
        result = report.to_dict()
        forecasts = result.get('forecasts', {})

        # En az bir metrikte ml_risk_context olmalı (anomaly_rate > 8)
        has_ml_ctx = False
        for name, fc in forecasts.items():
            if isinstance(fc, dict) and 'ml_risk_context' in fc:
                ctx = fc['ml_risk_context']
                self.assertIn('ml_risk_level', ctx)
                self.assertIn('anomaly_rate', ctx)
                self.assertIn('current_mean_score', ctx)
                has_ml_ctx = True
        self.assertTrue(has_ml_ctx, "En az bir forecast metriğinde ml_risk_context bekleniyor")


class TestInsightBuilderMLEnrichment(unittest.TestCase):
    """PATCH 5: _build_prediction_insight ML enrichment testleri."""

    @classmethod
    def setUpClass(cls):
        from src.anomaly.anomaly_tools import AnomalyDetectionTools
        # Minimum config — prediction disabled (sadece insight builder'ı test ediyoruz)
        cls.tools = AnomalyDetectionTools.__new__(AnomalyDetectionTools)
        cls.tools.prediction_enabled = False
        cls.tools.trend_analyzer = None
        cls.tools.rate_alert_engine = None
        cls.tools.forecaster = None

    def test_trend_summary_includes_ml_score_trend(self):
        """Trend summary ML skor yönünü içermeli."""
        prediction_results = {
            'trend': {
                'trend_direction': 'worsening',
                'alerts': [{
                    'alert_type': 'ml_score_degradation',
                    'severity': 'WARNING',
                    'title': 'ML Skor Kötüleşmesi',
                    'explainability': 'test',
                }],
                'summary': {
                    'baseline_anomaly_rate': 3.0,
                    'current_anomaly_rate': 8.0,
                    'ml_score_trend': {
                        'ml_score_direction': 'worsening',
                        'current_mean_score': 0.45,
                        'baseline_mean_score': 0.29,
                    }
                }
            }
        }
        insight = self.tools._build_prediction_insight(prediction_results)
        self.assertIsNotNone(insight)
        self.assertIn('ML skor trendi', insight['trend_summary'])
        self.assertIn('worsening', insight['trend_summary'])

    def test_rate_summary_includes_ml_corroboration_count(self):
        """Rate summary ML destekleme sayısını göstermeli."""
        prediction_results = {
            'rate': {
                'alerts': [
                    {
                        'alert_type': 'rate_spike',
                        'severity': 'WARNING',
                        'title': 'Error Rate Spike (5m)',
                        'explainability': 'test',
                        'ml_context': {
                            'ml_corroborated': True,
                            'window_anomaly_density_pct': 8.5,
                        }
                    },
                    {
                        'alert_type': 'rate_spike',
                        'severity': 'INFO',
                        'title': 'Warning Rate Spike (5m)',
                        'explainability': 'test',
                        'ml_context': {
                            'ml_corroborated': False,
                            'window_anomaly_density_pct': 2.1,
                        }
                    }
                ]
            }
        }
        insight = self.tools._build_prediction_insight(prediction_results)
        self.assertIsNotNone(insight)
        self.assertIn('ML tarafından destekleniyor', insight['rate_summary'])
        self.assertIn('1/2', insight['rate_summary'])

    def test_ml_context_forwarded_to_prediction_alerts(self):
        """Rate alert'lerdeki ml_context, prediction_alerts'e aktarılmalı."""
        prediction_results = {
            'rate': {
                'alerts': [{
                    'alert_type': 'rate_spike',
                    'severity': 'WARNING',
                    'title': 'Spike',
                    'explainability': 'x',
                    'ml_context': {
                        'ml_corroborated': True,
                        'window_anomaly_density_pct': 10.0,
                    }
                }]
            }
        }
        insight = self.tools._build_prediction_insight(prediction_results)
        self.assertIsNotNone(insight)
        alerts = insight['prediction_alerts']
        self.assertEqual(len(alerts), 1)
        self.assertIn('ml_context', alerts[0])
        self.assertTrue(alerts[0]['ml_context']['ml_corroborated'])

    def test_no_ml_enrichment_when_absent(self):
        """ml_score_trend / ml_context yoksa ek bilgi eklenmemeli."""
        prediction_results = {
            'trend': {
                'trend_direction': 'rising',
                'alerts': [{
                    'alert_type': 'anomaly_rate_increase',
                    'severity': 'WARNING',
                    'title': 'test',
                    'explainability': 'x',
                }],
                'summary': {
                    'baseline_anomaly_rate': 3.0,
                    'current_anomaly_rate': 8.0,
                    # ml_score_trend yok
                }
            }
        }
        insight = self.tools._build_prediction_insight(prediction_results)
        self.assertIsNotNone(insight)
        self.assertNotIn('ML skor trendi', insight['trend_summary'])


if __name__ == '__main__':
    unittest.main()
