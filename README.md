# 🧠 MongoDB LangChain Assistant

**Doğal Dil ile MongoDB Sorgulama Asistanı (LLM Destekli)**  
Bu proje, GPT-4o + LangChain altyapısı kullanarak MongoDB üzerinde doğal dil ile güvenli sorgular yapabilen CLI tabanlı bir asistandır. Özellikle DBA'lar ve sistem yöneticileri için tasarlanmıştır.

---

## 🚀 Özellikler

- 🔎 Doğal dil → MongoDB sorgu dönüşümü (LLM destekli)
- 🔐 Güvenlik kontrollü sorgu validator
- 📊 Schema analizi ve index önerileri
- 🧹 Veri tutarsızlığı (null, mixed type) tespiti
- 🛠 CLI tabanlı yönetim arayüzü
- ⚙️ Tam yapılandırılabilir `.env` dosyası
- 🌐 Windsurf gibi platformlara entegre edilebilir yapı

---

## 📂 Proje Yapısı

```
mongodb-langchain-assistant/
├── src/
│   ├── connectors/        # MongoDB & OpenAI bağlantı modülleri
│   ├── agents/            # LangChain agent yapısı ve araçları
│   ├── utils/             # Yardımcı fonksiyonlar
├── config/                # Konfigürasyon dosyaları
├── logs/                  # Log klasörü
├── tests/                 # Test dosyaları
├── main.py                # Ana çalıştırılabilir CLI arayüzü
├── .env                   # Gizli ayarlar (gitignore altında)
└── requirements.txt       # Python bağımlılıkları
```

---

## ⚙️ Kurulum

1. **Depoyu klonlayın**
   ```bash
   git clone https://github.com/muharremaltunbag/MongoDB-LLM-assistant.git
   cd MongoDB-LLM-assistant
   ```

2. **Virtual environment oluşturun**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows için: venv\Scripts\activate
   ```

3. **Gerekli paketleri yükleyin**
   ```bash
   pip install -r requirements.txt
   ```

4. **`.env` dosyasını doldurun**  
   Örnek:
   ```
   MONGODB_URI=mongodb://user:pass@localhost:27017/chatbot_test?authSource=admin
   MONGODB_DATABASE=chatbot_test
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o
   MAX_QUERY_LIMIT=100
   QUERY_TIMEOUT=30
   LOG_LEVEL=INFO
   ENVIRONMENT=development
   ```

---

## 🧪 Kullanım

CLI üzerinden çalıştırmak için:
```bash
python main.py
```

Örnek komutlar:
- `schema products` → `products` koleksiyonunun şemasını gösterir
- `stock bilgisi olmayan ürünleri listele`
- `price alanı string olan kaç ürün var?`
- `createdAt alanı olmayan ürünleri tespit et`

---

## 👮 Güvenlik

- Tüm sorgular otomatik olarak validator'dan geçer
- Tehlikeli operatörler ($where, $function, JS injection) engellenir
- Her sorgu maksimum 100 sonuçla sınırlıdır
- Hassas koleksiyonlara erişim kısıtlanabilir

---

## 📌 Katkı ve Geliştirme

Pull request’ler ve öneriler memnuniyetle karşılanır. Geliştirme adımları için `issues` ve `projects` sayfaları aktif kullanılacaktır.

---

## 🧑‍💻 Geliştirici

**Muharrem Altunbag**  
[LinkedIn](https://www.linkedin.com/in/muharrem-altunbag/)  
📧 altunbgmuharrem@gmail.com

---

## 📄 Ek Bilgi

### 🔒 .env Dosyası Yapısı

`.env` dosyası `.gitignore` ile dışlanmıştır. Aşağıdaki formatta manuel oluşturulmalıdır:

```dotenv
# MongoDB Bağlantı Bilgileri
MONGODB_URI=mongodb://<username>:<password>@localhost:27017/chatbot_test?authSource=admin
MONGODB_DATABASE=chatbot_test

# OpenAI API Bilgileri
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Uygulama Ayarları
MAX_QUERY_LIMIT=100
QUERY_TIMEOUT=30
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

### 🗃️ MongoDB Test Veritabanı Yapısı

#### Koleksiyon: `products`

- **Temel Alanlar:**
  - `name`: String veya null
  - `category`: "Erkek", "Kadın", "Çocuk", "Gizli"
  - `price`: Number veya string (test amaçlı)
  - `stock`: Beden-bazlı adet objesi veya undefined
  - `createdAt`: Date veya null
  - `manufacturer`: Object (örneğin `{ name: "LCW" }`) veya null
  - `description`: Uzun string (bazıları >1000 karakter)
  - `tags`, `variants`, `ratings`, `reviews`, `seo`, `campaign`: nested veya array alanlar

- **Test Senaryosu Amaçlı Sapmalar:**
  - `name: null` veya `""`
  - `price: "999.99"` (string olarak)
  - `stock`: eksik ya da undefined
  - `createdAt`: geçmiş tarih (örn. 2020) veya null
  - `category: "Gizli"` (policy testi)
  - `manufacturer: {}` veya `null`
  - `description`: aşırı uzun açıklama (1000+ karakter)
  - `veryLargeDocument: true` (boyut anomali testi)

Bu yapı sayesinde hem **DBA** hem de **sistem yöneticisi** rollerine uygun sorgular test edilebilir.
