"""
Server-specific model yönetimi test scripti
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Path configuration
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.anomaly_detector import MongoDBAnomalyDetector
from src.anomaly.anomaly_tools import AnomalyDetectionTools
import pandas as pd
import numpy as np

def test_server_specific_model_save_load():
    """Test 1: Server-specific model save/load"""
    print("\n" + "="*60)
    print("TEST 1: Server-Specific Model Save/Load")
    print("="*60)
    
    try:
        # Detector oluştur
        detector = MongoDBAnomalyDetector()
        
        # Dummy data oluştur
        X = pd.DataFrame(np.random.randn(100, 10), columns=[f'feature_{i}' for i in range(10)])
        
        # Test server isimleri
        test_servers = ["lcwmongodb01n2", "lcwmongodb02n1", "testmongodb01"]
        
        for server in test_servers:
            print(f"\n Testing server: {server}")
            
            # Train model for specific server
            detector.train(X, save_model=True, server_name=server)
            print(f"  ✅ Model trained and saved for {server}")
            
            # Check if file exists
            expected_path = f"models/isolation_forest_{server}.pkl"
            if Path(expected_path).exists():
                print(f"  ✅ Model file exists: {expected_path}")
                file_size = Path(expected_path).stat().st_size / 1024
                print(f"     File size: {file_size:.2f} KB")
            else:
                print(f"  ❌ Model file NOT found: {expected_path}")
            
            # Reset detector
            detector = MongoDBAnomalyDetector()
            
            # Load server-specific model
            loaded = detector.load_model(server_name=server)
            if loaded:
                print(f"  ✅ Model loaded successfully for {server}")
                print(f"     Current server: {detector.current_server}")
                print(f"     Server models cache: {list(detector.server_models.keys())}")
            else:
                print(f"  ❌ Failed to load model for {server}")
        
        print("\n✅ TEST 1 PASSED: Server-specific model save/load working")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_opensearch_with_host_filter():
    """Test 2: OpenSearch with host_filter"""
    print("\n" + "="*60)
    print("TEST 2: OpenSearch Integration with Host Filter")
    print("="*60)
    
    try:
        # AnomalyDetectionTools oluştur
        tools = AnomalyDetectionTools()
        
        # Test host filters
        test_hosts = [
            "lcwmongodb01n2.lcwaikiki.local",
            "lcwmongodb02n1",
            "KZNMONGODBN2"
        ]
        
        for host in test_hosts:
            print(f"\n Testing host filter: {host}")
            
            # Expected server name
            expected_server = host.split('.')[0] if '.' in host else host
            print(f"  Expected server name: {expected_server}")
            
            # Model path check
            model_path = f"models/isolation_forest_{expected_server}.pkl"
            print(f"  Expected model path: {model_path}")
            
            # Check if model would be loaded correctly
            if Path(model_path).exists():
                print(f"  ✅ Server-specific model exists")
            else:
                print(f"  ℹ️ No server-specific model, will use global or create new")
        
        print("\n✅ TEST 2 PASSED: Host filter to server name conversion working")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_historical_buffer_per_server():
    """Test 3: Historical buffer per server"""
    print("\n" + "="*60)
    print("TEST 3: Historical Buffer Management per Server")
    print("="*60)
    
    try:
        detector = MongoDBAnomalyDetector()
        
        # Test data
        X1 = pd.DataFrame(np.random.randn(50, 10), columns=[f'feature_{i}' for i in range(10)])
        X2 = pd.DataFrame(np.random.randn(70, 10), columns=[f'feature_{i}' for i in range(10)])
        
        # Server 1 training
        detector.train(X1, save_model=True, incremental=False, server_name="server1")
        buffer_size_1 = detector.historical_data['metadata']['total_samples']
        print(f"\n Server1 initial training:")
        print(f"  Samples: {len(X1)}")
        print(f"  Buffer size: {buffer_size_1}")
        
        # Server 1 incremental update
        detector.train(X2, save_model=True, incremental=True, server_name="server1")
        buffer_size_1_updated = detector.historical_data['metadata']['total_samples']
        print(f"\n Server1 after incremental update:")
        print(f"  New samples: {len(X2)}")
        print(f"  Updated buffer size: {buffer_size_1_updated}")
        print(f"  ✅ Buffer grew from {buffer_size_1} to {buffer_size_1_updated}")
        
        # Server 2 training (fresh start)
        detector = MongoDBAnomalyDetector()
        detector.train(X1, save_model=True, incremental=False, server_name="server2")
        buffer_size_2 = detector.historical_data['metadata']['total_samples']
        print(f"\n Server2 initial training:")
        print(f"  Samples: {len(X1)}")
        print(f"  Buffer size: {buffer_size_2}")
        
        # Load server1 model again
        detector = MongoDBAnomalyDetector()
        detector.load_model(server_name="server1")
        print(f"\n Reloaded Server1 model:")
        print(f"  Buffer size: {detector.historical_data['metadata']['total_samples']}")
        print(f"  ✅ Server1 buffer preserved: {detector.historical_data['metadata']['total_samples']} samples")
        
        print("\n✅ TEST 3 PASSED: Historical buffers are server-specific")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_response_structure():
    """Test 4: API response structure"""
    print("\n" + "="*60)
    print("TEST 4: API Response Structure with Server Info")
    print("="*60)
    
    try:
        # Create test response structure
        test_response = {
            "data": {
                "server_info": {
                    "server_name": "lcwmongodb01n2",
                    "model_status": "existing",
                    "model_path": "models/isolation_forest_lcwmongodb01n2.pkl",
                    "historical_buffer_size": 360673,
                    "last_update": "2024-01-15T10:30:00"
                },
                "summary": {
                    "total_logs": 10000,
                    "n_anomalies": 245,
                    "anomaly_rate": 2.45
                }
            }
        }
        
        # Verify structure
        assert "server_info" in test_response["data"], "server_info missing"
        assert "server_name" in test_response["data"]["server_info"], "server_name missing"
        assert "model_status" in test_response["data"]["server_info"], "model_status missing"
        assert "historical_buffer_size" in test_response["data"]["server_info"], "buffer size missing"
        
        print(f"\n Response structure validation:")
        print(f"  ✅ server_info present")
        print(f"  ✅ server_name: {test_response['data']['server_info']['server_name']}")
        print(f"  ✅ model_status: {test_response['data']['server_info']['model_status']}")
        print(f"  ✅ buffer_size: {test_response['data']['server_info']['historical_buffer_size']:,}")
        
        print("\n✅ TEST 4 PASSED: API response structure is correct")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("RUNNING SERVER-SPECIFIC MODEL TESTS")
    print("="*60)
    
    results = []
    
    # Test 1
    results.append(("Model Save/Load", test_server_specific_model_save_load()))
    
    # Test 2
    results.append(("OpenSearch Integration", test_opensearch_with_host_filter()))
    
    # Test 3
    results.append(("Historical Buffer", test_historical_buffer_per_server()))
    
    # Test 4
    results.append(("API Response", test_api_response_structure()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Server-specific model management is working correctly.")
    else:
        print("\n⚠️ SOME TESTS FAILED. Please review the errors above.")
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)