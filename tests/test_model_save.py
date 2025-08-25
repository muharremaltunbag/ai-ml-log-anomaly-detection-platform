import asyncio
from src.storage.storage_manager import StorageManager

async def test_model_save():
    """Model kaydetme testi"""
    
    storage = StorageManager()
    await storage.initialize()
    
    # Model bilgileri
    model_info = {
        "model_type": "IsolationForest",
        "parameters": {
            "n_estimators": 100,
            "contamination": 0.1
        },
        "training_stats": {
            "total_samples": 10000,
            "training_date": "2025-08-18"
        },
        "feature_names": ["severity", "component", "hour"],
        "n_features": 3
    }
    
    # Model kaydet
    version_id = await storage.save_model(
        model_path="models/isolation_forest.pkl",
        model_info=model_info,
        performance_metrics={
            "accuracy": 0.95,
            "precision": 0.92,
            "recall": 0.88
        }
    )
    
    print(f"Model kaydedildi: {version_id}")
    
    # Model registry'yi kontrol et
    models = await storage.mongodb.get_model_registry()
    print(f"\nModel Registry ({len(models)} model):")
    for model in models:
        print(f"- {model['version']}: {model['model_type']} (Active: {model.get('is_active', False)})")
    
    await storage.shutdown()

asyncio.run(test_model_save())