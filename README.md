# 🧠 MongoDB LangChain Assistant

**Natural Language Query Assistant for MongoDB (LLM-Powered)**  
This project is a CLI-based assistant that enables secure natural language querying on MongoDB using GPT-4o + LangChain. It is tailored for DBAs and system administrators.

---

## 🚀 Features

- 🔎 Natural language → MongoDB query transformation (LLM-based)
- 🔐 Secure query validator
- 📊 Schema analysis and index suggestions
- 🧹 Detection of data inconsistency (nulls, mixed types)
- 🛠 CLI-based management interface
- ⚙️ Fully configurable via `.env` file
- 🌐 Pluggable for platforms like Windsurf

---

## 📂 Project Structure

```
mongodb-langchain-assistant/
├── src/
│   ├── connectors/       # MongoDB & OpenAI connector modules
│   ├── agents/           # LangChain agent and tool logic
│   ├── utils/            # Utility functions
├── config/               # Configuration files
├── logs/                 # Log directory
├── tests/                # Test scripts
├── main.py               # Main executable CLI interface
├── .env                  # Secret configs (gitignored)
└── requirements.txt      # Python dependencies
```

---

## ⚙️ Installation

1. **Clone the repository**
```bash
git clone https://github.com/muharremaltunbag/MongoDB-LLM-assistant.git
cd MongoDB-LLM-assistant
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Create and configure `.env` file**

```ini
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

## 🧪 Usage

Run from CLI:

```bash
python main.py
```

Sample commands:

- `schema products` → show schema for the products collection
- `find products where stock is missing`
- `how many products have price as string?`
- `find products with no createdAt field`

---

## 👮 Security

- All queries pass through a secure validator
- Dangerous operators (`$where`, `$function`, JS injection) are blocked
- Each query is limited to 100 results
- Sensitive collections can be restricted

---

## 📌 Contribution & Development

Pull requests and suggestions are welcome. The **issues** and **projects** tabs are actively used for development tracking.

---

## 🧑‍💻 Developer

**Muharrem Altunbag**  
📧 altunbgmuharrem@gmail.com  
🔗 [LinkedIn](https://www.linkedin.com/in/muharrem-altunbag/)

---

## 📄 Additional Information

### 🔒 .env File Structure

This file is excluded via `.gitignore`. Create it manually with the following format:

```ini
# MongoDB Connection
MONGODB_URI=mongodb://<username>:<password>@localhost:27017/chatbot_test?authSource=admin
MONGODB_DATABASE=chatbot_test

# OpenAI API
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# App Settings
MAX_QUERY_LIMIT=100
QUERY_TIMEOUT=30
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

### 🗃️ MongoDB Test Database Structure

**Collection: `products`**

Sample fields:

- `name`: String or null
- `category`: "Male", "Female", "Child", or "Sensitive"
- `price`: Number or string
- `stock`: Object by size or undefined
- `createdAt`: Date or null
- `manufacturer`: Object (e.g. `{ name: "besttextile" }`) or null
- `description`: Some over 1000 characters
- `tags`, `variants`, `ratings`, `reviews`, `seo`, `campaign`: nested or array fields

**Test scenarios include:**

- `name`: null or empty
- `price`: string type (e.g., "999.99")
- `stock`: missing or undefined
- `createdAt`: old date (e.g., 2020) or null
- `category`: "Sensitive" (policy test)
- `manufacturer`: empty object or null
- `description`: excessively long
- `veryLargeDocument`: true (anomaly test)
