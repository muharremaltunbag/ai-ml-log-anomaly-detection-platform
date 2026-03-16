# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [15.0.0] - 2025-10-10
### Added
- Modüler Frontend Mimari (script-*.js ayrıştırmaları)
- DBA Analiz Modalı (zaman aralığı + çoklu host)
- ML Görselleştirmeleri (feature importance, component dağılımı, heatmap, metrikler)
- AI genişletilmiş açıklamalar (20 anomali, 5’li chunk)
- MongoDB history saklama + verify & retry
- Session ID üretimi ve 3 denemeli kaydetme
- Cluster paralel analizi (asyncio.gather)

### Changed
- OpenSearch entegrasyonu (proxy/cookie, scroll, slice)
- Incremental learning (server-specific model + historical buffer)
- UI/UX iyileştirmeleri (geniş görünüm, scroll, vurgu)
- Token optimizasyonu (yapılandırılmış çıktı, parça parça analiz)
- Storage yönetimi (10GB limit, FIFO cleanup, usage izleme)

### Fixed
- IndexError (index reset)
- Agresif duplicate removal
- JSON/type guard sorunları
- History merge alanları

### Removed
- Büyük model dosyası repo’dan kaldırıldı
- LocalStorage bağımlılığı minimuma indirildi

### Performance
- Render ve okuma iyileştirmeleri
- Dinamik max_samples

### Security
- .gitignore genişletildi (models/*.pkl*, temp_logs/, *.log)

# Changelog

## v17 – 01.12.2025  
### Full OpenSearch Modernization + ML Scaling + Hybrid Rule Engine + AI Visibility Fixes

Bu sürüm, MongoDB Anomaly Detection platformunun tam kapsamlı modernizasyonudur.  
Sistem artık sadece “Slow Query Dedektörü” değil; OpenSearch tabanlı gerçek zamanlı risk tarayıcısı ve bütüncül bir sağlık monitörü olarak çalışmaktadır.

---

### 1) Machine Learning Modernizasyonu
- StandardScaler entegre edildi → Sayısal değer farkları giderildi.
- Küçük olayların büyük sayılar tarafından ezilmesi problemi çözüldü.
- Auth Failure, Replication Error, Long Transaction gibi olaylar artık eşit önemde.

---

### 2) OpenSearch Micro-Slicing & Stabil Pipeline
- 24 saatlik veri tek seferde alınmıyor → 15 dakikalık mikro paketlere bölündü.
- Batch size 5000 → timeout (502) hataları tamamen ortadan kalktı.
- 300.000+ satır kesintisiz işlenebilir hale geldi.

---

### 3) Hybrid Rule Engine (ML + DBA Knowledge)
- Massive Scan (>1M docs) → +40 CRITICAL skor
- Long Transaction (>3s) → +30 skor
- Memory / Replication hataları → Her zaman kritik
- ML model skoru + DBA kural puanları birleşerek priority sorting geliştirildi.

---

### 4) UI & AI İyileştirmeleri
- UI limit 500 → 2000
- Hardcoded tenant → Dinamik tenant yapısına geçildi
- AI float parsing hatası düzeltildi → AI sonuçları eksiksiz okuyabiliyor

---

### 5) Model Cleanup ve Yönetim
- Eski tüm .pkl modeller temizlendi.
- Çoklu cluster eğitim desteği için `retrain_all_models.py` eklendi.
- Model store yeniden yapılandırıldı.

---

### ⚡ Sonuç
Bu sürüm ile sistem:
- Daha akıllı  
- Daha hızlı  
- Daha stabil  
- Daha görünür  
- Daha üretim odaklı  

bir **MongoDB Health Monitoring Platformu** hâline gelmiştir.

### Migration Notes
- index.html script sırası güncel tutulmalı
- Modeller repo’ya **eklenmemeli**
- History MongoDB’de, localStorage sadece metadata
