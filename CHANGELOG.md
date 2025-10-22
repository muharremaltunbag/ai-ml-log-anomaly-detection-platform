# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [15.0.0] - 2025-10-10
### Added
- Modüler Frontend Mimari (script-*.js ayrıştırmaları)
- DBA Analiz Modalı (zaman aralığı + çoklu host)
- ML Görselleştirmeleri (feature importance, component dağılımı, heatmap, metrikler)
- LCWGPT genişletilmiş açıklamalar (20 anomali, 5’li chunk)
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

### Migration Notes
- index.html script sırası güncel tutulmalı
- Modeller repo’ya **eklenmemeli**
- History MongoDB’de, localStorage sadece metadata
