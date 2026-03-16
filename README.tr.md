[English](README.md) | [Türkçe](README.tr.md)

# AI / ML Log Anomali Tespit Platformu

MongoDB, MSSQL ve Elasticsearch üzerinde log anomali tespiti, tahminleme ve LLM destekli operasyonel analiz için yapay zeka ve makine öğrenmesi tabanlı platform.

## Genel Bakış

Modern sistemler büyük hacimde log üretir; ancak bu verinin büyük çoğunluğu hiçbir zaman proaktif ve operasyonel açıdan yararlı bir şekilde yorumlanmaz. Pratikte olaylar çoğunlukla çok geç fark edilir, soruşturma yanlış katmandan başlatılır ya da sorunlar gürültülü ve parçalı log akışları arasında gizli kalır.

Bu proje tam olarak bu sorunu çözmek için geliştirildi.

Platform, logları manuel olarak taranması gereken statik metinler olarak değil; yapılandırılmış sinyallere dönüştürülecek, makine öğrenmesiyle analiz edilecek, kısa vadeli risk yönü tahmin edilecek ve sonuçları birleşik bir web arayüzü üzerinden sunulacak operasyonel veri akışları olarak ele alır. Hedef yalnızca bir anomalinin var olduğunu söylemek değil, şu soruların yanıtlanmasına yardımcı olmaktır:

- ne oluyor,
- nerede yoğunlaşıyor,
- ne kadar ciddi,
- kötüleşiyor mu,
- ve operasyonel açıdan ne anlama geliyor.

Bu platform tek kaynaklı bir betik ya da dar kapsamlı bir anomali dedektörü değildir. Aşağıdaki sistemleri desteklemek üzere tasarlanmış modüler, çok kaynaklı bir gözlemlenebilirlik ve anomali analiz platformudur:

- **MongoDB**
- **MSSQL**
- **Elasticsearch**

Tümü tek bir ortak analiz hattında buluşur.

---

## Bu Proje Neden Var

Büyük bir ortamda bir şeyler ters gittiğinde genellikle iki şeyden biri olur:

1. sorun çok geç fark edilir, ya da
2. soruşturma yanlış yerden başlar.

Temel sorun nadiren logların yokluğudur. Çoğu sistemde zaten çok fazla log vardır. Asıl güçlük, daha büyük operasyonel sorunlara dönüşmeden önce hangi sinyallerin önemli olduğunu belirlemektir.

Bu proje, operasyonel veriyi şu niteliklere kavuşturmak için oluşturuldu:

- daha okunabilir,
- daha yorumlanabilir,
- daha tahmin edilebilir,
- ve daha eyleme dönüştürülebilir.

Bu nedenle tasarım yalnızca anomali tespitinin ötesine geçmektedir. Platform şunları bir araya getirir:

- log alımı,
- kaynağa duyarlı ayrıştırma,
- özellik mühendisliği,
- anomali tespiti,
- trend analizi,
- oran tabanlı uyarı,
- tahminleme,
- yapay zeka destekli açıklama,
- depolama ve geçmiş,
- ve zamanlayıcı destekli orkestrasyon.

---

## Proje Hedefleri

Platform aşağıdaki hedefler doğrultusunda inşa edildi:

- ham operasyonel loglardan anomali tespitini otomatikleştirmek
- manuel log tarama bağımlılığını azaltmak
- trend analizi, oran uyarısı ve tahminleme aracılığıyla proaktif uyarı sinyalleri sağlamak
- yapay zeka destekli açıklama ile anomali sonuçlarını daha anlaşılır kılmak
- tüm çıktıları birleşik bir web panosu üzerinden sunmak
- zamanlayıcı odaklı iş akışlarıyla prodüksiyon tarzı periyodik analizi desteklemek

Daha geniş bir perspektiften bakıldığında proje, gürültülü çok kaynaklı operasyonel logları yapılandırılmış, yorumlanabilir ve yeniden kullanılabilir bir karar destek katmanına dönüştürmeyi amaçlamaktadır.

---

## Tasarım İlkeleri

Sistem birkaç temel ilke etrafında geliştirildi:

- **Kod veya veri olmadan varsayım yapılmaz**
- **Yıkıcı yeniden yazmalar yerine modüler değişiklikler**
- **Mümkün olduğunda geriye dönük uyumlu yapılar**
- **Performans bilincine sahip uygulama**
- **Sabit kodlanmış değerler yerine yapılandırma odaklı davranış**
- **Gizli bilgiler ortam değişkenleriyle yönetilir, kaynak kontrolüne alınmaz**
- **MongoDB, MSSQL ve Elasticsearch arasında mümkün olduğunda kaynak eşitliği**

Bu ilkeler projenin genişletilmesini, test edilmesini ve güvenli şekilde işletilmesini kolaylaştırır.

---

## Platform Ne Yapıyor

Üst düzeyde platform beş şey yapar:

1. **Birden fazla teknolojiden logları tek platformda toplar**
2. **Makine öğrenmesiyle alışılmadık davranışları tespit eder**
3. **Sürekli manuel inceleme gerektirmeden riski yüzeye çıkarır**
4. **Tahminleme yoluyla yakın vadeli yönü tahmin eder**
5. **Sonuçları daha hızlı soruşturma için doğal dilde açıklar**

Teknik terimlerle bu bir **çok kaynaklı anomali tespiti ve tahminleme platformudur**.

Günlük kullanımda değeri daha sadedir:

- bir sorun büyümeden önce erken sinyal verir,
- sorunun nerede yoğunlaştığını gösterir,
- zamansal tırmanmayı daha kolay görünür kılar,
- ve gürültülü logları anlaşılır operasyonel bağlama dönüştürmeye yardımcı olur.

---

## Desteklenen Kaynaklar

Platform şu anda şunları desteklemektedir:

- **MongoDB**
- **MSSQL**
- **Elasticsearch**

Mimari kasıtlı olarak modülerdir; bu nedenle aynı deseni izleyerek ek kaynaklar eklenebilir:

- kaynağa özgü okuyucu,
- kaynağa özgü özellik mühendisliği,
- kaynağa özgü dedektör,
- paylaşılan tahmin katmanı,
- paylaşılan depolama ve geçmiş,
- paylaşılan API ve arayüz entegrasyonu.

---

## Temel Özellikler

### 1. Çok kaynaklı log analizi

Farklı sistemlerden gelen loglar kaynağa duyarlı okuyucular aracılığıyla okunur ve ortak bir analiz akışına normalize edilir.

### 2. Makine öğrenmesi tabanlı anomali tespiti

Platform, temel anomali tespit modeli olarak **Isolation Forest** kullanır ve modelleri **sunucu başına** düzeyde yönetir; tüm ana makineleri tek bir evrensel profile zorlamak yerine davranışsal bağlamı korur.

### 3. Tahmin katmanı

Platform yalnızca mevcut anomalilerle sınırlı kalmaz. Aynı zamanda şunları sağlar:

- **trend tespiti**
- **oran tabanlı uyarı**
- **kısa vadeli tahminleme**

Bu, hem mevcut sapmayı hem de olası yönü analiz etmeyi mümkün kılar.

### 4. Yapay zeka destekli yorumlama

Bulgular, LLM entegrasyonu aracılığıyla doğal dile çevrilebilir; bu sayede ham makine öğrenmesi sonuçları daha kolay anlaşılır ve eyleme dönüştürülebilir hale gelir.

### 5. Tarihsel bağlam ve uyarlanabilir davranış

Sistem tarihsel bağlamı korur ve zaman içinde uyarlanabilir davranışı şunlar aracılığıyla destekler:

- tarihsel tamponlar,
- artımlı öğrenme yapıları,
- mini-model ve topluluk tarzı güncellemeler,
- özellik hizalaması ve şema stabilizasyonu.

### 6. Birleşik web arayüzü

FastAPI arka ucu ve Vanilla JavaScript ön ucu tek bir arayüz sunar:

- anomali analizi,
- tahmin panoları,
- risk görünümleri,
- zamanlayıcı kontrolleri,
- geçmiş analizi,
- makine öğrenmesi metrikleri ve görselleştirmeleri,
- uyarı detay görünümü,
- ve operasyonel bağlam panelleri.

---

## Ön Koşullar

Platformu çalıştırmadan önce aşağıdakilerin mevcut olduğundan emin olun:

- Python 3.10 veya üzeri
- Log verilerinizi içeren bir OpenSearch örneğine erişim
- MongoDB (opsiyonel; dosya tabanlı yedek yerine veritabanı destekli depolama istiyorsanız)
- `.env.example` dosyasını temel alan geçerli bir `.env` yapılandırma dosyası

Opsiyonel ama önerilen:

- Docker ve docker-compose
- Yapay zeka destekli açıklamalar istiyorsanız OpenAI uyumlu bir API anahtarı veya özel bir LLM uç noktası

---

## Üst Düzey Mimari

Platform, bir API'ye sarılmış tek bir model yerine katmanlı bir sistem olarak inşa edilmiştir.

### Ana katmanlar

1. **Log alımı**
2. **Kaynağa duyarlı ayrıştırma**
3. **Özellik mühendisliği**
4. **Anomali tespiti**
5. **Tahmin katmanı**
6. **Yapay zeka açıklaması**
7. **Depolama ve geçmiş**
8. **Zamanlayıcı ve orkestrasyon**

### Veri akışı

```text
Kullanıcı
  → Web Arayüzü / API
  → Analiz Orkestratörü
  → Kaynağa Özgü Okuyucu
  → Özellik Mühendisliği
  → Anomali Tespiti
  → Tahmin Katmanı
  → Yapay Zeka Açıklaması
  → Depolama / Geçmiş
```

### Operasyonel yapı

```text
Loglar (MongoDB / MSSQL / Elasticsearch)
  → OpenSearch
  → Okuyucu katmanı
  → Özellik mühendisliği
  → Makine öğrenmesi anomali tespiti
  → Trend / oran / tahmin kontrolleri
  → Yapay zeka açıklaması
  → Depolama + API yanıtı
  → Web arayüzü / panolar
```

---

## Depo Yapısı

```text
.
├── config/                     # Yapılandırma dosyaları
├── docs/                       # Belgeleme ve aktarım notları
├── src/
│   ├── agents/                 # Sorgu ve LLM ile ilgili ajan mantığı
│   ├── anomaly/                # Okuyucular, özellikler, dedektörler, tahminleme
│   ├── connectors/             # LLM ve veritabanı bağlayıcıları
│   ├── monitoring/             # İzleme yardımcıları
│   ├── performance/            # Performans analiz araçları
│   └── storage/                # Depolama yöneticisi, geçmiş, yedek mantığı
├── tests/                      # Test paketi
├── web_ui/
│   ├── api.py                  # FastAPI arka ucu
│   └── static/                 # Ön uç varlıkları
├── Dockerfile
├── docker-compose.yml
├── main.py
└── requirements.txt
```

---

## Başlarken

### 1. Depoyu klonlayın

```bash
git clone https://github.com/muharremaltunbag/ai-ml-log-anomaly-detection-platform.git
cd ai-ml-log-anomaly-detection-platform
```

### 2. Sanal ortam oluşturun

```bash
python -m venv venv
```

#### Windows

```bash
venv\Scripts\activate
```

#### Linux / macOS

```bash
source venv/bin/activate
```

### 3. Bağımlılıkları yükleyin

```bash
pip install -r requirements.txt
```

### 4. Ortam dosyanızı oluşturun

#### Linux / macOS

```bash
cp .env.example .env
```

#### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### 5. Gerekli ortam değişkenlerini doldurun

`.env` dosyasını kendi ortamınıza uygun değerlerle güncelleyin. Referans için [Ortam Değişkenleri](#ortam-değişkenleri) bölümüne bakın.

### 6. Uygulamayı çalıştırın

Kurulumunuza bağlı olarak:

```bash
python main.py
```

veya

```bash
uvicorn web_ui.api:app --reload
```

---

## Docker ile Hızlı Başlangıç

Konteyner tabanlı kurulum tercih ediyorsanız:

```bash
cp .env.example .env
# .env dosyasını kendi değerlerinizle düzenleyin
docker-compose up -d
```

Bu yöntem platformu daha yalıtılmış ve tekrarlanabilir bir ortamda çalıştırmak için kullanışlıdır.

---

## Dağıtım Seçenekleri

Platform birden fazla şekilde çalıştırılabilir.

Desteklenen yaklaşımlar:

- **Yerel Python ortamı** — geliştirme ve hızlı test için uygundur
- **FastAPI geliştirme kurulumu** — yinelemeli çalışma için sıcak yükleme ile `uvicorn` kullanımı
- **Docker / docker-compose** — daha yalıtılmış ve tekrarlanabilir dağıtımlar için

Bu, platformu deneme, yerel geliştirme ve daha yapılandırılmış dağıtım senaryoları için uygun kılar.

---

## Ortam Değişkenleri

Genel sürüm, sabit kodlanmış kimlik bilgileri yerine ortam değişkenleriyle yönetilir.

| Değişken                  | Amaç                                                   |
| ------------------------- | ------------------------------------------------------ |
| `OPENSEARCH_URL`          | OpenSearch uç noktası                                  |
| `OPENSEARCH_USER`         | OpenSearch kullanıcı adı                               |
| `OPENSEARCH_PASS`         | OpenSearch parolası                                    |
| `OPENSEARCH_TENANT`       | Opsiyonel kiracı değeri                                |
| `MONGODB_URI`             | MongoDB bağlantı dizesi                                |
| `MONGODB_ENABLED`         | MongoDB destekli depolamayı etkinleştirir veya devre dışı bırakır |
| `OPENAI_API_KEY`          | OpenAI uyumlu modeller için API anahtarı               |
| `LLM_PROVIDER`            | LLM sağlayıcı seçimi                                   |
| `API_KEY`                 | Etkinleştirilmişse web katmanı tarafından kullanılan API anahtarı |
| `HOSTNAME_STRIP_SUFFIXES` | Ana makine adı normalleştirme sonek listesi             |
| `MONGODB_FQDN_SUFFIX`     | Opsiyonel ana makine adı normalleştirme soneki          |

Tam liste için `.env.example` dosyasına bakın.

---

## Yapılandırma

Proje yapılandırma odaklıdır ve genel sürümde sabit kodlanmış kimlik bilgilerinden kaçınır.

Önemli yapılandırma alanları şunlardır:

- OpenSearch bağlantısı
- MongoDB bağlantısı
- LLM sağlayıcı seçimi
- anomali modeli davranışı
- tahmin yapılandırması
- zamanlayıcı yapılandırması
- küme eşlemeleri
- izleme eşlemeleri

İlgili dosyalar:

- `.env.example`
- `config/anomaly_config.json`
- `config/cluster_mapping.json`
- `config/monitoring_servers.json`

---

## Teknik Detaylar

### Log Okuyucuları

Platform, kaynağa özgü okuyucular kullanarak OpenSearch'ten log okur.

| Kaynak        | Okuyucu Katmanı               | Tipik İndeks Deseni   | Amaç                                                                          |
| ------------- | ----------------------------- | --------------------- | ----------------------------------------------------------------------------- |
| MongoDB       | `log_reader.py`               | `db-mongodb-*`        | MongoDB loglarını okur; yapılandırılmış ve metin tabanlı alım desenlerini destekler |
| MSSQL         | `mssql_log_reader.py`         | `db-mssql-*`          | MSSQL ile ilgili logları kaynağa duyarlı ayrıştırma yoluyla okur              |
| Elasticsearch | `elasticsearch_log_reader.py` | `db-elasticsearch-*`  | Elasticsearch operasyonel loglarını ve kaynağa özgü desenleri okur            |

Platformu kendi OpenSearch dağıtımınıza yönlendirmek için `.env` dosyasındaki bağlantı değerlerini yapılandırın.

---

### Özellik Mühendisliği

Ham bir log satırı makine öğrenmesi modeli tarafından doğrudan kullanılamaz. Bu nedenle sistem logları yapılandırılmış sinyallere dönüştürür.

Özellik kategorileri şunlardır:

- **zaman sinyalleri** — günün saati, hafta içi/sonu, varış arası zamanlama, patlama yoğunluğu
- **operasyonel bayraklar** — kimlik doğrulama hataları, yavaş sorgular, taramalar, işlemler, bellek sorunları, yeniden başlatmalar, replikasyonla ilgili sinyaller, kaynağa özgü operasyonel işaretleyiciler
- **sayısal ağırlık** — süreler, sayımlar, hacim göstergeleri, önem ölçüleri, kaynağa özgü performans metrikleri
- **bileşen bağlamı** — alt sistem veya bileşen kaynağı, nadir bileşen davranışı, mesaj parmak izi tekrarı, yoğunlaşma desenleri
- **şema stabilizasyonu** — özellik hizalaması, eksik sütun işleme, tutarlı sıralama ve tiplendirme

Bu, modelin yalnızca mesaj metnini değil davranışsal desenleri de görmesini sağlar.

---

### Anomali Tespit Motoru

Temel anomali tespit modeli **scikit-learn IsolationForest** üzerine kuruludur.

Tasarım ilkeleri:

- **sunucu başına bağlam** — tek bir model tüm ana makineleri eşit düzeyde temsil etmemelidir
- **özellik ölçeklendirmesi** — sayısal alanlar model kullanılmadan önce standartlaştırılır
- **artımlı davranış** — mini-toplu veya topluluk tarzı mantık daha yeni davranışı absorbe etmeye yardımcı olur
- **kritik geçersiz kılma katmanı** — istatistiksel olarak "normal" olan her zaman operasyonel açıdan güvenli anlamına gelmez
- **önem puanlaması** — anomaliler farklılaştırılmamış bir liste olarak döndürülmek yerine önceliklendirilir

Önem puanlaması makine öğrenmesi anomali skorunu, bileşen kritikliğini, operasyonel özellik bayraklarını, zaman bağlamını ve kural tabanlı geçersiz kılma sonuçlarını birleştirir. Hedef yalnızca tespit değil, önceliklendirmedir.

---

### Tarihsel Tampon ve Uyarlanabilir Modelleme

Platform her döngüye sıfırdan başlamaz.

Geçmiş özellikler, anomali skorları ve önceki sonuçlar yeni analizden önce korunur ve hizalanır. Bu, modele mevcut toplu işlemin ötesinde bağlam sağlar.

Sistem ayrıca tam yeniden eğitim olmaksızın yeni davranışın absorbe edilmesine izin veren artımlı veya mini-model tarzı güncellemeleri destekler. Bu, log dağılımlarının zamanla sürüklendiği operasyonel ortamlarda önem taşır.

---

### Kritik Kural Katmanı

Yalnızca anomali mantığı prodüksiyonda yeterli değildir.

Bazı olaylar istatistiksel olarak nadir olmasa bile operasyonel açıdan önemlidir. Bu nedenle platform, kural tabanlı kritik geçersiz kılma katmanı içerir.

Operasyonel açıdan önemli davranış örnekleri şunları kapsayabilir:

- ciddi bellek sorunları
- büyük taramalar
- kritik sistem arızaları
- replikasyonla ilgili risk
- yüksek etkili güvenlik olayları
- uzun süreli işlemler
- tekrarlayan hata patlamaları

Bu katman modeli tamamlar, onun yerini almaz.

---

### Tahmin Katmanı

Tahmin katmanı, yalnızca mevcut durumu tanımlamak değil kısa vadeli yönü tahmin etmek için trend tespiti, oran tabanlı uyarı ve tahminlemeyi birleştirir.

#### Tahminleme stratejisi

| Veri kullanılabilirliği | Strateji                              |
| ----------------------- | ------------------------------------- |
| 5 noktanın altında      | Yalnızca yön                          |
| 5–9 nokta               | Ağırlıklı hareketli ortalama          |
| 10–19 nokta             | Doğrusal regresyon                    |
| 20 ve üzeri nokta       | EWMA tabanlı trend ayrıştırma         |

Tahmin çıktıları şunları içerebilir:

- güven skoru
- üst/alt sınırlar
- volatilite
- trend açıklaması
- öneri alanı

Tahminleme, durumun istikrar kazanıp kazanmadığını ya da tırmanıp tırmanmadığını ve hangi metriğin daha tehlikeli bir duruma doğru ilerlediğini yanıtlamaya yardımcı olur.

---

### Depolama Modeli

Analiz sonuçları, tahmin çıktıları ve model meta verileri depolama katmanı aracılığıyla saklanır.

Desteklenen depolama modları:

- **MongoDB destekli depolama** — geçmiş ve meta veri ile tam kalıcı depolama
- **Dosya tabanlı yedek depolama** — MongoDB kullanılamadığında veya devre dışı bırakıldığında kullanılır

MongoDB kullanılamıyor veya devre dışıysa platform kalıcılık için dosya tabanlı depolamayı kullanmaya devam eder. Bu, sistemin yerel ortamda test edilmesini ve kısıtlı ortamlarda daha dayanıklı çalışmasını kolaylaştırır.

---

## Yapay Zeka / LLM Katmanı

Platform, anomali ve tahmin çıktılarının üzerine yapay zeka destekli açıklama sunar.

Bu katman ham skorları, özellik desenlerini, kaynağa özgü bulguları ve tahmin bağlamını operasyonel açıdan daha kolay yorumlanabilir doğal dil özetlerine dönüştürür.

LLM katmanının tipik hedefleri:

- temel bulguları özetlemek
- olası operasyonel anlamı açıklamak
- acil kontrolleri veya eylemleri önermek
- soruşturma için daha net bir anlatı sağlamak

Proje şunları destekler:

- OpenAI uyumlu LLM kullanımı
- özel LLM uç noktası entegrasyonu

---

## LLM Entegrasyon Stratejisi

### Desteklenen modlar

- **OpenAI uyumlu sağlayıcı**
- **Özel LLM uç noktası**
- **LLM devre dışı modu**

Bu davranış ortam yapılandırması aracılığıyla kontrol edilir.

### LLM katmanının tipik sorumlulukları

- anomalileri özetlemek
- olası operasyonel anlamı açıklamak
- yapılandırılmış sonuçları okunabilir dile dönüştürmek
- daha hızlı ilk geçiş soruşturma rehberliği üretmek

### Yedek davranış

Platform, analizin tamamen LLM kullanılabilirliğine bağlı olmayacağı şekilde tasarlanmıştır. LLM katmanı kullanılamıyorsa veya yapılandırılmamışsa temel anomali tespit ve tahmin hattı çalışmaya devam edebilir; desteklenen durumlarda yedek açıklayıcı davranış kullanılabilir.

---

## Ortam Odaklı LLM Seçimi

LLM davranışı kod düzenlemeleri yerine yapılandırma aracılığıyla seçilir.

Tipik modlar şunlardır:

- `LLM_PROVIDER=openai`
- `LLM_PROVIDER=custom`
- yapılandırmaya bağlı olarak azaltılmış veya devre dışı LLM kullanımı için boş veya ayarlanmamış sağlayıcı

Bu, uygulama yapısını değiştirmeden sağlayıcı değiştirilmesini kolaylaştırır.

---

## Depolama ve Kalıcılık Stratejisi

Depolama katmanı dayanıklılık ve esneklik için tasarlanmıştır.

Temel yaklaşım; daha zengin kalıcılık için **MongoDB destekli depolama** ve MongoDB'nin kullanılamadığı veya kasıtlı olarak devre dışı bırakıldığı ortamlar için **dosya tabanlı yedek depolama** kullanır.

Bu, platformun yerel test, kısıtlı dağıtım veya azaltılmış bağımlılık ortamlarında kullanılabilir kalmasını sağlar.

Depolanan yapılar şunları içerebilir:

- anomali analizi geçmişi
- tahmin uyarıları ve özetleri
- model meta verileri
- daha sonra karşılaştırma için tarihsel bağlam

---

## Zamanlayıcı ve Orkestrasyon

Platform yalnızca manuel olarak tetiklenen bir betik olarak değil, tekrarlanabilir bir operasyonel süreç olarak çalışabilir.

Orkestrasyon güvenceleri şunlardır:

- aralık kontrolü
- soğuma süresi yönetimi
- çakışma koruması
- eşzamanlılık sınırları
- ana makine düzeyinde izleme

Bu, platformun prodüksiyon benzeri periyodik analiz senaryolarında kullanılabilir olmasını sağlar.

---

## Teknoloji Yığını

### Arka Uç

- Python
- FastAPI
- Uvicorn

### Makine Öğrenmesi

- scikit-learn
- pandas
- numpy
- joblib

### Depolama / Veri

- MongoDB
- OpenSearch

### Ön Uç

- Vanilla JavaScript
- HTML
- CSS
- Chart.js

### Yapay Zeka / LLM

- OpenAI uyumlu modeller
- özel LLM uç noktası desteği

### Dağıtım

- Docker
- docker-compose

---

## Ana Fonksiyonel Alanlar

### Anomali Tespiti

MongoDB, MSSQL ve Elasticsearch log akışlarından anomalileri tespit eder.

### Tahmin Stüdyosu

Trend analizi, oran uyarısı, tahminleme ve risk bağlam görünümleri sağlar.

### Analiz Geçmişi

Önceki analiz sonuçlarını saklar ve erişime sunar.

### Zamanlayıcı Kontrolleri

Periyodik otomatik iş akışlarını destekler.

### Yapay Zeka Açıklaması

Teknik bulgular için okunabilir özetler oluşturur.

### Makine Öğrenmesi Görselleştirme

Web arayüzü üzerinden metrik ve model ile ilgili görünürlüğü destekler.

---

## API Genel Bakışı

FastAPI arka ucu anomali analizi, tahmin iş akışları, zamanlayıcı kontrolü ve geçmiş erişimi için uç noktalar sunar.

Tipik uç nokta grupları şunlardır:

- sistem durumu
- anomali analizi
- tahmin ve öngörü
- zamanlayıcı kontrolleri
- sohbet / yapay zeka açıklaması
- analiz geçmişi
- makine öğrenmesi metrikleri

Sürüme ve dalınızdaki etkin özelliklere bağlı olarak uç nokta adları biraz farklılık gösterebilir. Ana arka uç giriş noktası:

```
web_ui/api.py
```

---

## Demo ve Sunum Desteği

Dal içeriğine bağlı olarak proje, daha güvenli ekran görüntüleri veya demolar için demo odaklı arayüz desteği içerebilir.

Tipik demo ile ilgili hedefler şunlardır:

- hassas ana makine adlarını veya ortama özgü etiketleri maskeleme
- daha güvenli kamuya yönelik ekran görüntüleri alma
- demo sunum mantığını prodüksiyon odaklı arayüz davranışından ayırma

Dalınızda demo varlıkları mevcutsa, bunlar ortama özgü operasyonel detayları açığa çıkarmadan kamuya açık demolar için tasarlanmıştır.

---

## Geliştirici Notları

Bu depo modüler geliştirme ve genişletme için tasarlanmıştır.

Platformu genişletirken önerilen stil:

- değişiklikleri modüler tutun
- gereksiz soyutlamadan kaçının
- basit, test edilebilir mantığı tercih edin
- mümkün olduğunda kaynak eşitliğini koruyun
- arayüz davranışını arka uç çıktılarıyla yönlendirin
- mevcut yapılandırma formatlarını açıkça belgelenmedikçe bozmayın

Bu, desteklenen kaynaklar ve dağıtım stilleri genelinde kullanılabilirliği korumaya yardımcı olur.

---

## Mevcut Durum

Platformda uygulanmış ve kullanılabilir durumda olan özellikler:

- çok kaynaklı log alımı
- kaynağa duyarlı özellik mühendisliği
- makine öğrenmesi tabanlı anomali tespiti
- kural destekli önem mantığı
- trend analizi
- oran tabanlı uyarı
- tahminleme
- yapay zeka destekli açıklama
- depolama ve geçmiş
- web arayüzü
- zamanlayıcı desteği

---

## Test Durumu

Genel sürüm hazırlanmış ve arındırılmıştır; ancak kullanıcılar ortama özgü entegrasyonu kendi kurulumlarında doğrulanması gereken bir şey olarak değerlendirmelidir.

Genel olarak doğrulanmış alanlar şunlardır:

- temel modül içe aktarma ve duman testi hazırlığı
- genel kullanıma güvenlik temizliği ve gizli bilgi kaldırma
- yapılandırma odaklı yapı
- temel alanlarda uyumluluk odaklı içe aktarma düzenlemeleri

Genellikle ortama özgü doğrulama gerektiren alanlar:

- OpenSearch ile tam uçtan uca bağlantı
- gerçek LLM sağlayıcı entegrasyonu
- canlı zamanlayıcı yürütme
- hedef ortamda MongoDB kalıcılığı
- hedef sistemde Docker dağıtımı
- kullanıcıya özgü kurulumda tam arayüz etkileşim testi

Bu, harici hizmetlere ve altyapıya bağımlı sistemler için normaldir.

---

## Bilinen Sınırlamalar

Ortamınıza bağlı olarak ek doğrulama veya genişletme gerektirebilecek birkaç alan:

- kendi OpenSearch veri kümenize karşı uçtan uca test
- altyapınızda özel LLM davranışının doğrulanması
- iş yükü boyutunuza göre zamanlayıcı ayarı
- dağıtıma özgü depolama doğrulaması
- çok kiracılı veya yüksek hacimli ortamlarda tam performans ve yük testi

Bu depo platform temelini sağlar; ancak prodüksiyon kalitesinde dağıtım yine de kendi altyapınıza, ölçeklendirmenize ve operasyonel doğrulamanıza bağlıdır.

---

## Yol Haritası

Potansiyel sonraki adımlar şunlardır:

- daha güçlü uçtan uca çok kaynaklı test
- daha otomatik yeniden eğitim akışları
- sürüklenme tetiklemeli yeniden eğitim iş akışları
- CI/CD entegrasyonu
- daha zengin geri bildirim odaklı öğrenme
- ek kaynak adaptörleri
- genişletilmiş görselleştirme ve raporlama seçenekleri

---

## Sorun Giderme

### OpenSearch bağlantı sorunları

`.env` dosyanızda aşağıdakileri kontrol edin:

- `OPENSEARCH_URL`
- `OPENSEARCH_USER`
- `OPENSEARCH_PASS`

Ayrıca OpenSearch örneğinizin çalışma ortamınızdan erişilebilir olduğunu doğrulayın.

### MongoDB bağlantı sorunları

MongoDB destekli depolama etkin ancak kullanılamıyorsa şunları inceleyin:

- `MONGODB_URI`
- `MONGODB_ENABLED`

Mevcut yapılandırmanız destekliyorsa platform dosya tabanlı depolamaya geri dönebilir.

### Yapay zeka açıklaması çalışmıyor

Şunları kontrol edin:

- `LLM_PROVIDER`
- `OPENAI_API_KEY`
- `.env` dosyasındaki özel LLM uç noktası yapılandırması

Yapay zeka destekli açıklama opsiyoneldir ve hiçbir sağlayıcı yapılandırılmamışsa atlanabilir.

### Bağımlılık veya içe aktarma sorunları

Şunu çalıştırın:

```bash
pip install -r requirements.txt
```

Ortamınızda kısmen yüklenmiş paketler varsa sanal ortamı yeniden oluşturmak genellikle en temiz çözümdür.

---

## Genel Kullanıma Açık Kaynak Hazırlığı

Bu depo yalnızca bir kod dışa aktarması değildir. Arındırılmış bir genel sürüm olarak hazırlanmıştır.

Genel sürüm süreci şunları kapsadı:

- ortama özgü gizli bilgileri kaldırma veya değiştirme
- dahili ana makine ve küme desenlerini genelleştirme
- kuruma özgü LLM referanslarını genel özel LLM isimlendirmesiyle değiştirme
- sabit kodlanmış değerleri `.env` veya yapılandırma odaklı yer tutuculara taşıma
- yalnızca dahili kullanım için olan test artifaktlarını kaldırma
- genel kurulum ortamları için bağımlılık uyumluluğunu iyileştirme
- dış kullanıcılar için belgeleri yeniden yazma

Sonuç, platformun özgün ortamı dışında daha kolay anlaşılabilen, yapılandırılabilen ve yeniden kullanılabilen bir sürümüdür.

---

## Son Genel Sürüm İyileştirmeleri

Açık kaynak hazırlık çalışması şunları kapsadı:

- gizli bilgi arındırma
- dahili adlandırma temizliği
- genel özel LLM entegrasyon isimlendirmesi
- ortam değişkeni tamamlama
- genel bağımlılık ortamları için uyumluluk iyileştirmeleri
- dış kullanıcılar için belge yeniden yazımı
- yalnızca dahili kullanım için olan artifaktların kaldırılması

Bu değişiklikler genel bağlamlarda güvenliği, netliği ve yeniden kullanımı iyileştirmek amacıyla yapıldı.

---

## Genel Sürüm Notları

Bu, platformun arındırılmış bir genel sürümüdür.

Genel depo şunları içermez:

- gerçek kimlik bilgileri
- özel uç noktalar
- dahili ana makine eşlemeleri
- kuruma özgü tanımlayıcılar
- prodüksiyon gizli bilgileri
- ortama özgü özel altyapı detayları

`.env.example` ve yapılandırma dosyalarını şablon olarak kullanın, ardından kendi ortamınıza özgü değerleri sağlayın.

---

## Güvenlik Uygulamaları

Bu proje, genel kullanıma güvenli bir yapılandırma modeliyle tasarlanmıştır.

Önerilen uygulamalar:

- `.env` dosyasını asla commit etmeyin
- kimlik bilgilerini kod veya ekran görüntülerinde asla saklamayın
- prodüksiyon gizli bilgilerini deponun dışında tutun
- açığa çıkan kimlik bilgilerini hemen döndürün
- geliştirme, test ve prodüksiyon için ayrı kimlik bilgileri kullanın
- paylaşmadan önce genel demoları ve ekran görüntülerini doğrulayın

---

## Önerilen GitHub Konuları

GitHub'da daha güçlü keşfedilebilirlik için şu konuları kullanın:

- `ai`
- `machine-learning`
- `llm`
- `anomaly-detection`
- `log-analysis`
- `forecasting`
- `opensearch`
- `mongodb`
- `mssql`
- `elasticsearch`
- `fastapi`
- `observability`
- `aiops`

---

## Lisans

Tercih ettiğiniz lisansı buraya ekleyin, örneğin MIT.




