---
description: MongoDB LangChain Assistant - Advanced Windsurf Workflows
---

# MongoDB LangChain Assistant - Windsurf Workflows

## 🛠️ Core Development Workflows

### 1. Yeni LangChain Tool Ekleme
```
WORKFLOW: add_new_tool
TRIGGER: "Yeni tool eklemek istiyorum"
PRIORITY: Medium

STEPS:
1. Tool kategorisini belirle:
   - MongoDB (3): Core database operations
   - Monitoring (5): System metrics  
   - Performance (2): Query optimization
   - Anomaly (3): Log analysis

2. Uygun modül dizinini seç:
   - MongoDB: src/agents/tools.py
   - Monitoring: src/monitoring/monitoring_tools.py
   - Performance: src/performance/performance_tools.py
   - Anomaly: src/anomaly/anomaly_tools.py

3. Tool implementation:
   - StructuredTool pattern kullan
   - Standart JSON response format:
     ```json
     {
       "durum": "başarılı|uyarı|hata",
       "işlem": "tool_name",
       "açıklama": "Türkçe açıklama",
       "sonuç": {},
       "öneriler": []
     }
     ```

4. Security & Integration:
   - QueryValidator entegrasyonu (MongoDB için)
   - Input validation (Pydantic)
   - get_all_tools() fonksiyonunu güncelle
   - Agent integration test

5. Documentation:
   - .windsurf/context.md tool sayısını güncelle
   - Usage examples ekle

VALIDATION:
- Tool sayısı 13'ten fazla
- Response format standarda uygun
- Agent integration çalışıyor
- Security checks pass
```

### 2. SSH Configuration Test & Troubleshooting
```
WORKFLOW: ssh_config_test
TRIGGER: "SSH ayarlarını test etmek istiyorum" | "SSH bağlantı problemi"
PRIORITY: High

STEPS:
1. Environment kontrol:
   - Test: Vagrant VMs (2200, 2201, 2222)
   - Production: lcwmongodb01n1/n2/n3 + Jump servers

2. Jump server connectivity:
   - RAGNAROK (10.29.1.229:22)
   - LCWECOMMERCE (10.62.0.70:22)

3. Authentication test:
   - LDAP (same user): Jump → Target
   - DBA (different user): Jump → Target with credentials

4. SSH connection sequence:
   - Jump server connection
   - TCP tunnel (direct-tcpip)
   - Target server connection
   - Log path access: /mongodata/log/

5. Dynamic SSH Reader test:
   - DynamicSSHLogReader.set_connection_params()
   - connect() method
   - read_logs() functionality

6. Security validation:
   - Memory-only password storage
   - Connection cleanup
   - Error handling

VALIDATION:
- SSH bağlantı kuruldu
- Log okuma çalışıyor
- Authentication methods tested
- Error handling validated
- Security checks passed

ERROR_RECOVERY:
- Connection timeout: Check network/firewall
- Auth failure: Verify credentials/permissions
- Log access denied: Check file permissions
```

### 3. Anomaly Model Update
```
WORKFLOW: anomaly_model_update
TRIGGER: "Anomaly modelini güncellemek istiyorum"
PRIORITY: High

STEPS:
1. Current model assessment:
   - Performance metrics (accuracy, false positives)
   - Model age ve training data freshness
   - models/ dizininde saved model kontrolü

2. Data collection:
   - SSH ile production logs (minimum 1000 entries)
   - Data quality check
   - Format validation (JSON/Text)

3. Feature engineering:
   - 15 aktif feature validation:
     * Temporal (4): hour_of_day, is_weekend, burst_density
     * Message (3): is_auth_failure, is_drop_operation
     * Component (3): component_encoded, is_rare_component
     * Severity (1): severity_W
     * Attribute (4): has_error_key, attr_key_count

4. Model training:
   - Isolation Forest parameters:
     * contamination: 0.03 (3%)
     * n_estimators: 300
     * random_state: 42
   - Model validation
   - Performance comparison

5. Deployment:
   - Old model backup
   - New model save (joblib)
   - Production test

VALIDATION:
- Model training successful
- Validation metrics >85% accuracy
- False positive rate <5%
- Production deployment successful

ROLLBACK:
- Restore previous model
- Validate rollback success
```

## 🚀 Operations Workflows

### 4. Production Deployment
```
WORKFLOW: production_deployment
TRIGGER: "Production'a deploy etmek istiyorum"
PRIORITY: Critical

STEPS:
1. Pre-deployment security:
   - SSH Key Policy: AutoAddPolicy → StrictHostKeyChecking
   - API keys production değerleri
   - Credential security audit

2. LC Waikiki compliance:
   - Corporate colors: #0047BA, #0033A0, #5C5B5B
   - Security standards
   - Performance SLA

3. Environment setup:
   - Production MongoDB cluster:
     * lcwmongodb01n1: 10.29.20.163
     * lcwmongodb01n2: 10.29.20.172  
     * lcwmongodb01n3: 10.29.20.171
   - Jump servers: RAGNAROK, LCWECOMMERCE
   - Virtual environment + dependencies

4. Configuration deployment:
   - .env production values
   - monitoring_servers.json production config
   - anomaly_config.json SSH settings

5. Tool validation:
   - 13 Tool functionality test
   - Integration test suite
   - End-to-end validation

6. Monitoring setup:
   - Health checks
   - Performance monitoring
   - Security alerts
   - Dashboard configuration

VALIDATION:
- All 13 tools operational
- SSH connections working
- MongoDB cluster accessible
- Performance within SLA
- Security controls active

ROLLBACK_PLAN:
1. Traffic diversion
2. Configuration restoration
3. Service restart
4. Validation
```

### 5. Error Investigation
```
WORKFLOW: error_investigation
TRIGGER: "Hata araştırması yapmak istiyorum"
PRIORITY: High

STEPS:
1. Error classification:
   - SSH connection errors
   - MongoDB query failures
   - LangChain tool malfunctions
   - API/UI errors
   - Performance issues

2. Log analysis:
   - Application logs (/logs/)
   - MongoDB logs (/mongodata/log/)
   - SSH connection logs
   - System logs

3. System state check:
   - 13 Tool health matrix
   - Resource utilization
   - Connection pool status
   - Memory usage patterns

4. Root cause analysis:
   - Timeline reconstruction
   - Pattern identification
   - Contributing factors
   - Code path tracing

5. Solution implementation:
   - Fix development
   - Testing strategy
   - Deployment plan
   - Monitoring enhancement

VALIDATION:
- Root cause identified
- Solution tested
- Prevention implemented
- Documentation updated
```

### 6. Performance Optimization
```
WORKFLOW: performance_optimization
TRIGGER: "Performance problemi var"
PRIORITY: High

STEPS:
1. Performance assessment:
   - Query response times
   - System resource usage
   - Connection utilization
   - Bottleneck identification

2. MongoDB optimization:
   - Slow query analysis
   - Execution plan review:
     * Performance score: time(30) + efficiency(30) + index(25) + result_size(15)
   - Index usage analysis
   - COLLSCAN vs IXSCAN detection

3. SSH optimization:
   - Connection pooling
   - Keep-alive settings
   - Compression evaluation

4. Anomaly detection optimization:
   - Model inference time
   - Feature extraction efficiency
   - Memory usage
   - Parallel processing

5. Implementation:
   - Priority-based fixes
   - A/B testing
   - Performance monitoring

VALIDATION:
- Response time improvement >20%
- Resource usage reduction >15%
- Error rate unchanged
- Functionality preserved

TARGETS:
- MongoDB queries: <100ms average
- SSH connections: <2s establishment
- Anomaly detection: <5s analysis
```

## 🔧 Maintenance Workflows

### 7. Weekly System Maintenance
```
WORKFLOW: weekly_maintenance
TRIGGER: "Haftalık bakım yapmak istiyorum"
SCHEDULE: Weekly (Sunday 02:00 AM)
PRIORITY: Medium

STEPS:
1. Health check:
   - 13 tools availability
   - MongoDB cluster health
   - SSH connectivity
   - Anomaly model performance

2. Database maintenance:
   - Index optimization
   - Connection pool cleanup
   - Slow query review
   - Replication status

3. SSH maintenance:
   - Connection cleanup
   - Key rotation check
   - Jump server health
   - Auth log review

4. Anomaly maintenance:
   - Model performance check
   - False positive analysis
   - Training data freshness
   - Retraining assessment

5. System cleanup:
   - Log rotation
   - Temp file cleanup
   - Cache cleanup
   - Old model cleanup (keep last 5)

6. Security review:
   - Access log analysis
   - Failed auth review
   - Unusual activity detection

VALIDATION:
- All systems healthy
- Performance within baseline
- Security posture maintained
- Cleanup completed

REPORTING:
- Maintenance summary
- Performance trends
- Security review
- Capacity recommendations
```

## 🎯 Usage Instructions

### Workflow Activation:
```
# Development:
"MongoDB için backup tool eklemek istiyorum"
→ add_new_tool workflow

"SSH production bağlantısı çalışmıyor"  
→ ssh_config_test workflow

"Anomaly model accuracy düştü"
→ anomaly_model_update workflow

# Operations:
"Production'a deploy etmek istiyorum"
→ production_deployment workflow

"Sistemde performans problemi var"
→ performance_optimization workflow

"Haftalık bakım zamanı"
→ weekly_maintenance workflow
```

### Priority Levels:
- **Critical**: Production deployment, security issues
- **High**: SSH problems, performance issues, errors
- **Medium**: Development tasks, maintenance

### Success Patterns:
- Prerequisites validated
- Step-by-step execution
- Validation at each stage
- Rollback plans ready
- Documentation updated

Bu kompakt workflow sistemi MongoDB LangChain Assistant projenizde **operational excellence** sağlar! 