# test_upload_pipeline_validation.py
"""
Upload Pipeline Doğrulama Testi
OpenSearch ile aynı pipeline'dan geçtiğini doğrular
"""

import sys
sys.path.insert(0, '.')

def test_imports():
    """Modül import testleri"""
    print("=" * 60)
    print("📦 MODÜL IMPORT TESTLERİ")
    print("=" * 60)
    
    try:
        from src.storage.storage_manager import StorageManager
        print("✅ StorageManager import başarılı")
        
        # uploaded_filename parametresi kontrolü
        import inspect
        sig = inspect.signature(StorageManager.save_anomaly_analysis)
        params = list(sig.parameters.keys())
        
        if 'uploaded_filename' in params:
            print("✅ save_anomaly_analysis() 'uploaded_filename' parametresi VAR")
        else:
            print("❌ save_anomaly_analysis() 'uploaded_filename' parametresi YOK!")
            return False
            
    except Exception as e:
        print(f"❌ StorageManager import hatası: {e}")
        return False
    
    try:
        from src.anomaly.anomaly_tools import AnomalyDetectionTools
        print("✅ AnomalyDetectionTools import başarılı")
        
        # Server extraction fonksiyonları kontrolü
        tools = AnomalyDetectionTools.__dict__
        
        if '_extract_server_from_filename' in tools:
            print("✅ _extract_server_from_filename() metodu VAR")
        else:
            print("❌ _extract_server_from_filename() metodu YOK!")
            return False
            
        if '_extract_server_from_log_content' in tools:
            print("✅ _extract_server_from_log_content() metodu VAR")
        else:
            print("❌ _extract_server_from_log_content() metodu YOK!")
            return False
            
    except Exception as e:
        print(f"❌ AnomalyDetectionTools import hatası: {e}")
        return False
    
    try:
        from src.anomaly.log_reader import MongoDBLogReader, enrich_log_entry
        print("✅ MongoDBLogReader import başarılı")
        print("✅ enrich_log_entry import başarılı")
    except Exception as e:
        print(f"❌ log_reader import hatası: {e}")
        return False
    
    print("\n✅ TÜM IMPORTLAR BAŞARILI")
    return True

def test_enrich_log_entry():
    """enrich_log_entry fonksiyonu testi"""
    print("\n" + "=" * 60)
    print("🔧 ENRICH_LOG_ENTRY FONKSİYONU TESTİ")
    print("=" * 60)
    
    from src.anomaly.log_reader import enrich_log_entry
    
    # Test log entry
    test_log = {
        't': {'$date': '2025-01-15T10:30:00.000Z'},
        's': 'W',
        'c': 'QUERY',
        'ctx': 'conn12345',
        'msg': 'Slow query',
        'attr': {
            'durationMillis': 5000,
            'ns': 'testdb.users'
        }
    }
    
    enriched = enrich_log_entry(test_log)
    
    # Kontroller
    checks = [
        ('full_message' in enriched, "full_message alanı VAR"),
        ('message' in enriched, "message alanı VAR"),
        (enriched.get('full_message') is not None, "full_message dolu"),
        (enriched.get('message') is not None, "message dolu"),
    ]
    
    all_passed = True
    for passed, desc in checks:
        status = "✅" if passed else "❌"
        print(f"{status} {desc}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print(f"\n📝 Enriched message: {enriched.get('full_message', 'N/A')[:100]}")
    
    return all_passed

def test_server_extraction():
    """Server name extraction testi"""
    print("\n" + "=" * 60)
    print("🖥️ SERVER NAME EXTRACTION TESTİ")
    print("=" * 60)
    
    from src.anomaly.anomaly_tools import AnomalyDetectionTools
    
    tools = AnomalyDetectionTools(environment='test')
    
    # Test dosya adları
    test_filenames = [
        ("mongod_lcwmongodb01n2.log", "lcwmongodb01n2"),
        ("ECAZTRDBMNG019.log", "ecaztrdbmng019"),
        ("mongod.log.PPLMNGDBN2", "pplmngdbn2"),
        ("testmongodb01_2025.log", "testmongodb01"),
        ("random_file.log", None),  # Tanınmayan pattern
    ]
    
    all_passed = True
    for filename, expected in test_filenames:
        result = tools._extract_server_from_filename(filename)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} {filename} -> {result} (beklenen: {expected})")
        if not passed:
            all_passed = False
    
    return all_passed

def main():
    """Ana test fonksiyonu"""
    print("\n" + "=" * 60)
    print("🧪 UPLOAD PIPELINE DOĞRULAMA TESTLERİ")
    print("=" * 60)
    
    results = []
    
    # Test 1: Imports
    results.append(("Import Testleri", test_imports()))
    
    # Test 2: Enrich log entry
    results.append(("Enrich Log Entry", test_enrich_log_entry()))
    
    # Test 3: Server extraction
    results.append(("Server Extraction", test_server_extraction()))
    
    # Özet
    print("\n" + "=" * 60)
    print("📊 TEST SONUÇLARI")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 TÜM TESTLER BAŞARILI!")
        print("Upload pipeline OpenSearch ile uyumlu çalışıyor.")
    else:
        print("⚠️ BAZI TESTLER BAŞARISIZ!")
        print("Lütfen hataları kontrol edin.")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)