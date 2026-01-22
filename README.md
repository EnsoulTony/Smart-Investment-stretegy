# Smart-Investment-stretegy
Radar V1.4 三指標策略戰情室

## 環境需求 (Environment Requirements)

此專案使用以下工具和技術：
- **Python 3.11+**: 主要開發語言
- **Claude AI**: AI 助手支援
- **Aider**: AI 配對編程工具

## 安裝設定 (Installation & Setup)

### 1. Python 環境設定

```bash
# 建議使用 pyenv 管理 Python 版本
pyenv install 3.11
pyenv local 3.11

# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 2. 環境變數設定

```bash
# 複製環境變數範例檔案
cp .env.example .env

# 編輯 .env 檔案，填入你的 API keys
# - ANTHROPIC_API_KEY: Claude API 金鑰 (從 https://console.anthropic.com/ 取得)
# - OPENAI_API_KEY: OpenAI API 金鑰 (選用，用於 Aider)
```

### 3. Aider 使用

Aider 是一個 AI 配對編程工具，可以協助你編寫和修改程式碼。

```bash
# 確保已安裝 aider-chat
pip install aider-chat

# 啟動 Aider
aider

# 或指定特定檔案
aider file1.py file2.py
```

Aider 配置檔案位於 `.aider.conf.yml`，可以根據需求調整設定。

## 專案說明 (Project Description)

智慧投資策略系統 - Radar V1.4 三指標策略戰情室

### 主要功能
- 三指標技術分析策略
- 即時市場數據監控
- 投資決策輔助系統

## 開發指南 (Development Guide)

### 使用 AI 工具開發

1. **使用 Claude**: 透過 API 或介面與 Claude 互動，獲取程式碼建議和問題解決方案
2. **使用 Aider**: 在終端機中執行 `aider` 命令，直接與 AI 協作編寫程式碼
3. **版本控制**: 所有變更都應該透過 Git 進行版本控制

### 程式碼規範

- 遵循 PEP 8 Python 程式碼風格指南
- 使用有意義的變數和函數命名
- 為複雜邏輯添加註解說明

## 授權 (License)

請參閱 LICENSE 檔案
