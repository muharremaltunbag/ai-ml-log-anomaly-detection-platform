#!/usr/bin/env python3
# MongoDB-LLM-assistant\src\anomaly\retrain_all_models.py

"""
MongoDB Log Anomaly Detection - Model Retraining Script
========================================================
Bu script, feature optimizasyonu sonrası tüm modelleri yeniden eğitir.

Kullanım:
    python retrain_all_models.py --server lcwmongodb01n2
    python retrain_all_models.py --all
    python retrain_all_models.py --validate-only

Değişiklikler (Feature Optimization):
- Kaldırılan: is_admin_operation, is_ftdc_event, is_scram_failure, 
              is_tenant_operation, txn_keys_inserted, is_create_operation
- Değiştirilen: is_transaction_operation → is_aborted_transaction
"""

import os
import sys
import json
import shutil
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Proje root'unu path'e ekle (src/anomaly/ içinden çalıştırılıyorsa)
PROJECT_ROOT = Path(__file__).parent.parent.parent  # src/anomaly/ -> src/ -> root/
sys.path.insert(0, str(PROJECT_ROOT))

from src.anomaly.log_reader import MongoDBLogReader, OpenSearchProxyReader
from src.anomaly.feature_engineer import MongoDBFeatureEngineer
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/retraining_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Beklenen güncel feature listesi (optimizasyon sonrası)
EXPECTED_FEATURES = [
    # Severity
    "severity_W",
    
    # Component
    "component_encoded",
    "is_rare_component",
    "component_changed",
    
    # Component Categories (MongoDB 8.0)
    "is_wiredtiger_recovery",
    "is_wiredtiger_checkpoint",
    "is_wiredtiger_event",
    "is_storage_event",
    "is_async_io_event",
    "is_index_event",
    "is_recovery_event",
    "is_unknown_component",
    "is_network_component",
    "is_security_component",
    "is_replication_component",
    "is_storage_component",
    "is_control_component",
    "component_criticality_score",
    
    # Message Features
    "is_auth_failure",
    "is_drop_operation",
    "is_aggregate_operation",
    "is_bulk_operation",
    "is_aborted_transaction",  # YENİ (is_transaction_operation yerine)
    "is_rare_message",
    "is_collscan",
    "is_index_build",
    "is_slow_query",
    "is_high_doc_scan",
    "is_shutdown",
    "is_assertion",
    "is_fatal",
    "is_error",
    "is_replication_issue",
    "is_out_of_memory",
    "is_restart",
    "is_memory_limit",
    
    # Temporal
    "hour_of_day",
    "is_weekend",
    "extreme_burst_flag",
    "burst_density",
    
    # Attr Features
    "has_error_key",
    "attr_key_count",
    "has_many_attrs",
    "is_rare_combo",
    
    # Numeric Features
    "query_duration_ms",
    "docs_examined_count",
    "keys_examined_count",
    "performance_score",
    
    # Transaction Features (Optimized)
    "txn_time_active_micros",
    "txn_time_inactive_micros",
    "txn_wait_ratio",
]

# Kaldırılan feature'lar (doğrulama için)
REMOVED_FEATURES = [
    "is_admin_operation",
    "is_ftdc_event", 
    "is_scram_failure",
    "is_tenant_operation",
    "txn_keys_inserted",
    "is_create_operation",
    "is_transaction_operation",  # is_aborted_transaction ile değiştirildi
    "is_long_transaction",
]


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_config(config_path: str = "config/anomaly_config.json") -> Dict[str, Any]:
    """Config dosyasını doğrula"""
    logger.info(f"Validating config: {config_path}")
    
    result = {
        "status": "OK",
        "errors": [],
        "warnings": [],
        "info": []
    }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        result["status"] = "ERROR"
        result["errors"].append(f"Failed to load config: {e}")
        return result
    
    # enabled_features kontrolü
    enabled_features = config.get("anomaly_detection", {}).get("features", {}).get("enabled_features", [])
    
    if not enabled_features:
        result["status"] = "ERROR"
        result["errors"].append("enabled_features list is empty!")
        return result
    
    result["info"].append(f"Found {len(enabled_features)} enabled features")
    
    # Kaldırılması gereken feature'lar hala var mı?
    for removed_feature in REMOVED_FEATURES:
        if removed_feature in enabled_features:
            result["status"] = "ERROR"
            result["errors"].append(f"Removed feature still in config: {removed_feature}")
    
    # Yeni feature'lar eklenmiş mi?
    if "is_aborted_transaction" not in enabled_features:
        result["warnings"].append("is_aborted_transaction not found in enabled_features")
    
    # Eksik beklenen feature'lar
    missing_expected = set(EXPECTED_FEATURES) - set(enabled_features)
    if missing_expected:
        result["warnings"].append(f"Missing expected features: {missing_expected}")
    
    # Fazla feature'lar (beklenmeyen)
    extra_features = set(enabled_features) - set(EXPECTED_FEATURES) - set(REMOVED_FEATURES)
    if extra_features:
        result["info"].append(f"Additional features in config: {extra_features}")
    
    return result


def validate_feature_engineer(config_path: str = "config/anomaly_config.json") -> Dict[str, Any]:
    """Feature engineer'ın doğru çalıştığını test et"""
    logger.info("Validating feature engineer...")
    
    result = {
        "status": "OK",
        "errors": [],
        "warnings": [],
        "extracted_features": []
    }
    
    try:
        from src.anomaly.feature_engineer import MongoDBFeatureEngineer
        import pandas as pd
        
        # Feature engineer oluştur
        fe = MongoDBFeatureEngineer(config_path)
        
        # Test verisi oluştur
        test_data = pd.DataFrame([{
            't': {'$date': '2025-05-14T10:30:00.000Z'},
            's': 'W',
            'c': 'COMMAND',
            'msg': 'Slow query',
            'attr': {'durationMillis': 5000, 'docsExamined': 100000}
        }])
        
        # Feature extraction
        X, df = fe.create_features(test_data)
        
        result["extracted_features"] = list(X.columns)
        result["info"] = [f"Extracted {len(X.columns)} features"]
        
        # Kaldırılan feature'lar çıkarılmış mı?
        for removed in REMOVED_FEATURES:
            if removed in X.columns:
                result["status"] = "ERROR"
                result["errors"].append(f"Removed feature still being extracted: {removed}")
        
        # Yeni feature'lar eklendi mi?
        if "is_aborted_transaction" not in X.columns:
            result["warnings"].append("is_aborted_transaction not in extracted features")
        
        logger.info(f"Feature engineer validation: {result['status']}")
        
    except Exception as e:
        result["status"] = "ERROR"
        result["errors"].append(f"Feature engineer test failed: {e}")
        import traceback
        result["errors"].append(traceback.format_exc())
    
    return result


# ============================================================================
# BACKUP FUNCTIONS
# ============================================================================

def backup_existing_models(models_dir: str = "models", backup_dir: str = None) -> str:
    """Mevcut modelleri yedekle"""
    if backup_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"models_backup_{timestamp}"
    
    models_path = Path(models_dir)
    backup_path = Path(backup_dir)
    
    if not models_path.exists():
        logger.warning(f"Models directory not found: {models_dir}")
        return None
    
    # Model dosyalarını bul
    model_files = list(models_path.glob("*.pkl"))
    
    if not model_files:
        logger.warning("No model files found to backup")
        return None
    
    # Backup klasörü oluştur
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # Dosyaları kopyala
    for model_file in model_files:
        dest = backup_path / model_file.name
        shutil.copy2(model_file, dest)
        logger.info(f"Backed up: {model_file.name}")
    
    logger.info(f"Backup completed: {len(model_files)} files to {backup_dir}")
    return str(backup_path)


def clear_historical_buffers(models_dir: str = "models") -> Dict[str, Any]:
    """Mevcut modellerdeki historical buffer'ları temizle"""
    import joblib
    
    result = {
        "cleared": [],
        "errors": [],
        "skipped": []
    }
    
    models_path = Path(models_dir)
    model_files = list(models_path.glob("*.pkl"))
    
    for model_file in model_files:
        try:
            # Model yükle
            model_data = joblib.load(model_file)
            
            # Historical data'yı kontrol et
            if 'historical_data' in model_data and model_data['historical_data'] is not None:
                if model_data['historical_data'].get('features') is not None:
                    old_size = len(model_data['historical_data']['features'])
                    
                    # Buffer'ı temizle
                    model_data['historical_data'] = {
                        'features': None,
                        'predictions': None,
                        'scores': None,
                        'metadata': {
                            'total_samples': 0,
                            'anomaly_samples': 0,
                            'last_update': None,
                            'buffer_version': 2.0,
                            'cleared_reason': 'Feature optimization retraining'
                        }
                    }
                    
                    # Kaydet
                    joblib.dump(model_data, model_file)
                    
                    result["cleared"].append({
                        "file": model_file.name,
                        "old_buffer_size": old_size
                    })
                    logger.info(f"Cleared buffer: {model_file.name} (was {old_size} samples)")
                else:
                    result["skipped"].append(model_file.name)
            else:
                result["skipped"].append(model_file.name)
                
        except Exception as e:
            result["errors"].append({
                "file": model_file.name,
                "error": str(e)
            })
            logger.error(f"Error clearing buffer for {model_file.name}: {e}")
    
    return result


# ============================================================================
# RETRAINING FUNCTIONS
# ============================================================================

def get_available_servers(config_path: str = "config/monitoring_servers.json") -> List[str]:
    """Mevcut sunucu listesini al"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        servers = []
        for server in config.get("servers", []):
            if server.get("enabled", True):
                servers.append(server.get("name") or server.get("hostname"))
        
        return servers
    except Exception as e:
        logger.warning(f"Could not load server config: {e}")
        return []


def retrain_single_server(
    server_name: str,
    config_path: str = "config/anomaly_config.json",
    hours: int = 24,
    clear_buffer: bool = True
) -> Dict[str, Any]:
    """Tek bir sunucu için model retraining"""
    logger.info(f"="*60)
    logger.info(f"Retraining model for server: {server_name}")
    logger.info(f"="*60)
    
    result = {
        "server": server_name,
        "status": "PENDING",
        "errors": [],
        "stats": {}
    }
    
    try:
        from src.anomaly.feature_engineer import MongoDBFeatureEngineer
        from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
        
        # =====================================================================
        # DÜZELTME: OpenSearchProxyReader kullan (MongoDBLogReader değil)
        # =====================================================================
        
        # Step 1: OpenSearch reader oluştur
        logger.info("Step 1: Initializing OpenSearch reader...")
        opensearch_reader = OpenSearchProxyReader()
        
        # Step 2: OpenSearch'e bağlan
        logger.info("Step 2: Connecting to OpenSearch...")
        if not opensearch_reader.connect():
            raise Exception("Failed to connect to OpenSearch. Check credentials and network.")
        logger.info("Successfully connected to OpenSearch")
        
        # Step 3: OpenSearch'ten log çek
        logger.info(f"Step 3: Fetching logs from OpenSearch (last {hours} hours)...")
        logs_df = opensearch_reader.read_logs(
            last_hours=hours,
            host_filter=server_name
        )
        
        if logs_df is None or len(logs_df) == 0:
            result["status"] = "SKIPPED"
            result["errors"].append(f"No logs found for {server_name}")
            logger.warning(f"No logs found for {server_name}, skipping...")
            return result
        
        logger.info(f"Fetched {len(logs_df)} logs")
        result["stats"]["log_count"] = len(logs_df)
        
        # Step 4: Feature engineering
        logger.info("Step 4: Extracting features...")
        feature_engineer = MongoDBFeatureEngineer(config_path)
        X, enriched_df = feature_engineer.create_features(logs_df)
        
        logger.info(f"Extracted {len(X.columns)} features")
        result["stats"]["feature_count"] = len(X.columns)
        result["stats"]["features"] = list(X.columns)
        
        # Step 5: Filtreleme
        logger.info("Step 5: Applying filters...")
        enriched_filtered, X_filtered = feature_engineer.apply_filters(enriched_df, X)
        logger.info(f"After filtering: {len(X_filtered)} samples")
        result["stats"]["filtered_count"] = len(X_filtered)
        
        if len(X_filtered) == 0:
            result["status"] = "SKIPPED"
            result["errors"].append(f"No logs remaining after filtering for {server_name}")
            logger.warning(f"No logs remaining after filtering for {server_name}, skipping...")
            return result
        
        # Step 6: Model oluştur ve eğit
        logger.info("Step 6: Training model...")
        detector = MongoDBAnomalyDetector(config_path)
        
        # Historical buffer'ı temizle (yeni feature set için)
        if clear_buffer:
            detector.clear_historical_buffer()
            logger.info("Historical buffer cleared for fresh training")
        
        # Training
        training_stats = detector.train(
            X_filtered,
            save_model=True,
            incremental=False,  # İlk eğitim, incremental değil
            server_name=server_name
        )
        
        result["stats"]["training"] = training_stats
        result["status"] = "SUCCESS"
        
        # Sanitize server name for filename
        safe_server_name = server_name.replace('.', '_').replace(':', '_')
        logger.info(f"Training completed successfully for {server_name}")
        logger.info(f"Model saved to: models/isolation_forest_{safe_server_name}.pkl")
        
    except Exception as e:
        result["status"] = "ERROR"
        result["errors"].append(str(e))
        import traceback
        result["errors"].append(traceback.format_exc())
        logger.error(f"Retraining failed for {server_name}: {e}")
    
    return result


def retrain_all_servers(
    config_path: str = "config/anomaly_config.json",
    hours: int = 24,
    servers: List[str] = None
) -> Dict[str, Any]:
    """Tüm sunucular için model retraining"""
    logger.info("="*60)
    logger.info("STARTING FULL MODEL RETRAINING")
    logger.info("="*60)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "config_path": config_path,
        "servers": {},
        "summary": {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
    }
    
    # Sunucu listesi
    if servers is None:
        servers = get_available_servers()
    
    if not servers:
        # Sunucu config'i yoksa OpenSearch'ten al
        logger.info("No server config found, fetching from OpenSearch...")
        try:
            opensearch_reader = OpenSearchProxyReader()
            if opensearch_reader.connect():
                servers = opensearch_reader.get_available_hosts(last_hours=hours)
                logger.info(f"Found {len(servers)} servers from OpenSearch")
            else:
                logger.error("Could not connect to OpenSearch to get server list")
        except Exception as e:
            logger.error(f"Error getting servers from OpenSearch: {e}")
    
    if not servers:
        logger.error("No servers found!")
        results["summary"]["error"] = "No servers configured or found"
        return results
    
    logger.info(f"Servers to retrain: {servers}")
    results["summary"]["total"] = len(servers)
    
    # Her sunucu için retraining
    for server in servers:
        result = retrain_single_server(server, config_path, hours)
        results["servers"][server] = result
        
        if result["status"] == "SUCCESS":
            results["summary"]["success"] += 1
        elif result["status"] == "ERROR":
            results["summary"]["failed"] += 1
        else:
            results["summary"]["skipped"] += 1
    
    # Özet
    logger.info("="*60)
    logger.info("RETRAINING SUMMARY")
    logger.info("="*60)
    logger.info(f"Total servers: {results['summary']['total']}")
    logger.info(f"Successful: {results['summary']['success']}")
    logger.info(f"Failed: {results['summary']['failed']}")
    logger.info(f"Skipped: {results['summary']['skipped']}")
    
    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="MongoDB Log Anomaly Detection - Model Retraining Tool"
    )
    
    parser.add_argument(
        "--server", "-s",
        type=str,
        help="Single server name to retrain"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Retrain all configured servers"
    )
    
    parser.add_argument(
        "--validate-only", "-v",
        action="store_true",
        help="Only validate config and feature engineer, don't retrain"
    )
    
    parser.add_argument(
        "--hours", "-H",
        type=int,
        default=24,
        help="Hours of log data to use for training (default: 24)"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/anomaly_config.json",
        help="Path to config file"
    )
    
    parser.add_argument(
        "--backup", "-b",
        action="store_true",
        help="Backup existing models before retraining"
    )
    
    parser.add_argument(
        "--clear-buffers",
        action="store_true",
        help="Clear historical buffers in existing models"
    )
    
    parser.add_argument(
        "--no-clear-buffer",
        action="store_true",
        help="Don't clear historical buffer during training"
    )
    
    parser.add_argument(
        "--list-servers",
        action="store_true",
        help="List available servers from OpenSearch and exit"
    )
    
    args = parser.parse_args()
    
    # Logs klasörü oluştur
    Path("logs").mkdir(exist_ok=True)
    
    print("\n" + "="*60)
    print("MongoDB Log Anomaly Detection - Model Retraining Tool")
    print("="*60 + "\n")
    
    # List servers mode
    if args.list_servers:
        print("Fetching available servers from OpenSearch...")
        try:
            opensearch_reader = OpenSearchProxyReader()
            if opensearch_reader.connect():
                servers = opensearch_reader.get_available_hosts(last_hours=args.hours)
                print(f"\nFound {len(servers)} servers:\n")
                for i, server in enumerate(servers, 1):
                    print(f"  {i}. {server}")
                return 0
            else:
                print("ERROR: Could not connect to OpenSearch")
                return 1
        except Exception as e:
            print(f"ERROR: {e}")
            return 1
    
    # Step 1: Config validation
    print("Step 1: Validating configuration...")
    config_result = validate_config(args.config)
    
    if config_result["errors"]:
        print(f"[X] Config validation FAILED:")
        for error in config_result["errors"]:
            print(f"   - {error}")
        if not args.validate_only:
            print("\nFix config errors before retraining!")
            return 1
    else:
        print(f"[OK] Config validation passed")
    
    if config_result["warnings"]:
        print(f"[!] Warnings:")
        for warning in config_result["warnings"]:
            print(f"   - {warning}")
    
    # Step 2: Feature engineer validation
    print("\nStep 2: Validating feature engineer...")
    fe_result = validate_feature_engineer(args.config)
    
    if fe_result["errors"]:
        print(f"[X] Feature engineer validation FAILED:")
        for error in fe_result["errors"]:
            print(f"   - {error}")
        if not args.validate_only:
            print("\nFix feature engineer errors before retraining!")
            return 1
    else:
        print(f"[OK] Feature engineer validation passed")
        print(f"   Extracted features: {len(fe_result['extracted_features'])}")
    
    if args.validate_only:
        print("\n[OK] Validation completed (--validate-only mode)")
        return 0
    
    # Step 3: Backup (optional)
    if args.backup:
        print("\nStep 3: Backing up existing models...")
        backup_path = backup_existing_models()
        if backup_path:
            print(f"[OK] Backup created: {backup_path}")
        else:
            print("[!] No models to backup")
    
    # Step 4: Clear buffers (optional)
    if args.clear_buffers:
        print("\nStep 4: Clearing historical buffers...")
        clear_result = clear_historical_buffers()
        print(f"[OK] Cleared: {len(clear_result['cleared'])} buffers")
        if clear_result["errors"]:
            print(f"[!] Errors: {len(clear_result['errors'])}")
    
    # Step 5: Retraining
    print("\nStep 5: Retraining models...")
    
    clear_buffer = not args.no_clear_buffer
    
    if args.server:
        # Single server
        result = retrain_single_server(
            args.server, 
            args.config, 
            args.hours,
            clear_buffer=clear_buffer
        )
        
        if result["status"] == "SUCCESS":
            print(f"\n[OK] Retraining completed successfully for {args.server}")
            print(f"   Logs processed: {result['stats'].get('log_count', 'N/A')}")
            print(f"   Features extracted: {result['stats'].get('feature_count', 'N/A')}")
            print(f"   Samples after filtering: {result['stats'].get('filtered_count', 'N/A')}")
        elif result["status"] == "SKIPPED":
            print(f"\n[!] Retraining skipped for {args.server}")
            for error in result["errors"]:
                print(f"   - {error}")
            return 0
        else:
            print(f"\n[X] Retraining failed for {args.server}")
            for error in result["errors"]:
                print(f"   - {error}")
            return 1
            
    elif args.all:
        # All servers
        results = retrain_all_servers(args.config, args.hours)
        
        print(f"\n{'='*60}")
        print("FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"Total: {results['summary']['total']}")
        print(f"Success: {results['summary']['success']}")
        print(f"Failed: {results['summary']['failed']}")
        print(f"Skipped: {results['summary']['skipped']}")
        
        if results["summary"]["failed"] > 0:
            return 1
    else:
        print("Please specify --server <name> or --all")
        print("Use --list-servers to see available servers")
        parser.print_help()
        return 1
    
    print("\n[OK] Retraining process completed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())