# Локальная Qwen3 для генерации ФОС

Актуальный путь проекта на ПК:

```text
C:\projects\control-work-generator
```

Файл модели:

```text
Qwen3-14B-Q4_K_M.gguf
```

Модель не хранится в GitHub. Она должна лежать только локально на компьютере.

## Быстрый вариант через готовые скрипты

После `git pull` в проекте будут Windows-скрипты:

```text
scripts\windows\setup_c_project_env.ps1
scripts\windows\start_qwen.ps1
scripts\windows\start_backend.ps1
scripts\windows\start_frontend.ps1
scripts\windows\check_local_llm.ps1
```

### 1. Положить модель

Положи файл сюда:

```text
C:\projects\control-work-generator\backend\storage\models\Qwen3-14B-Q4_K_M.gguf
```

### 2. Настроить `.env`

Из корня проекта:

```powershell
cd C:\projects\control-work-generator
powershell -ExecutionPolicy Bypass -File scripts\windows\setup_c_project_env.ps1
```

Скрипт создаст или обновит:

```text
backend\.env
```

и пропишет настройки локальной LLM.

### 3. Запустить Qwen

В отдельном PowerShell:

```powershell
cd C:\projects\control-work-generator
powershell -ExecutionPolicy Bypass -File scripts\windows\start_qwen.ps1
```

Окно не закрывать. Это процесс модели.

Если `start_qwen.ps1` ругнется на `--jinja`, запусти вручную без него:

```powershell
cd C:\projects\control-work-generator
llama-server -m backend\storage\models\Qwen3-14B-Q4_K_M.gguf --host 127.0.0.1 --port 8081 -c 8192
```

### 4. Запустить backend

Во втором PowerShell:

```powershell
cd C:\projects\control-work-generator
powershell -ExecutionPolicy Bypass -File scripts\windows\start_backend.ps1
```

### 5. Запустить frontend

В третьем PowerShell:

```powershell
cd C:\projects\control-work-generator
powershell -ExecutionPolicy Bypass -File scripts\windows\start_frontend.ps1
```

### 6. Проверить LLM

В четвертом PowerShell:

```powershell
cd C:\projects\control-work-generator
powershell -ExecutionPolicy Bypass -File scripts\windows\check_local_llm.ps1
```

Нормальный результат:

```json
{
  "enabled": true,
  "available": true,
  "json_ok": true,
  "model": "qwen3-14b-instruct-q4_k_m"
}
```

## Ручной вариант

## 1. Куда положить модель

Открой корень проекта:

```powershell
cd C:\projects\control-work-generator
```

Создай папку для моделей, если ее нет:

```powershell
mkdir backend\storage\models
```

Положи файл модели сюда:

```text
C:\projects\control-work-generator\backend\storage\models\Qwen3-14B-Q4_K_M.gguf
```

Проверить, что файл на месте:

```powershell
dir backend\storage\models
```

В списке должен быть файл:

```text
Qwen3-14B-Q4_K_M.gguf
```

## 2. Установить llama.cpp

Попробуй через winget:

```powershell
winget install llama.cpp
```

После установки закрой PowerShell и открой новый терминал, затем проверь:

```powershell
llama-server --version
```

Если команда не находится, значит `llama-server` не добавился в PATH. Тогда нужно либо перезагрузить терминал/Windows, либо запускать `llama-server.exe` из папки установки.

## 3. Запустить локальный сервер модели

Из корня проекта:

```powershell
cd C:\projects\control-work-generator
```

Запусти модель:

```powershell
llama-server -m backend\storage\models\Qwen3-14B-Q4_K_M.gguf --host 127.0.0.1 --port 8081 -c 8192 --jinja
```

Если появилась ошибка про неизвестный параметр `--jinja`, запусти без него:

```powershell
llama-server -m backend\storage\models\Qwen3-14B-Q4_K_M.gguf --host 127.0.0.1 --port 8081 -c 8192
```

Если ноутбук начинает сильно тормозить, можно уменьшить контекст:

```powershell
llama-server -m backend\storage\models\Qwen3-14B-Q4_K_M.gguf --host 127.0.0.1 --port 8081 -c 4096
```

Окно с `llama-server` не закрывать. Это отдельный процесс модели.

## 4. Проверить, что сервер отвечает

Открой второй PowerShell и выполни:

```powershell
Invoke-RestMethod http://127.0.0.1:8081/v1/models
```

Если сервер работает, будет JSON-ответ со списком моделей.

## 5. Включить локальную LLM в backend

Открой файл:

```text
backend\.env
```

Добавь или измени строки:

```env
LOCAL_LLM_ENABLED=true
LOCAL_LLM_BASE_URL=http://127.0.0.1:8081/v1
LOCAL_LLM_MODEL=qwen3-14b-instruct-q4_k_m
LOCAL_LLM_TIMEOUT_SECONDS=120
LOCAL_LLM_TEMPERATURE=0.2
LOCAL_LLM_MAX_TOKENS=900
LOCAL_LLM_MAX_ITEMS=24
```

Важно: `LOCAL_LLM_MODEL` — это внутреннее имя для запроса. Сам файл модели может называться `Qwen3-14B-Q4_K_M.gguf`.

Если файла `backend\.env` нет, скопируй пример:

```powershell
copy backend\.env.example backend\.env
```

И потом добавь строки выше.

## 6. Перезапустить backend

В отдельном PowerShell:

```powershell
cd C:\projects\control-work-generator\backend
.\.venv\Scripts\activate
python run.py
```

Backend должен стартовать без ошибок.

## 7. Проверить интеграцию из backend

В еще одном PowerShell:

```powershell
cd C:\projects\control-work-generator\backend
.\.venv\Scripts\activate
python -m app.tools.test_local_llm
```

Нормальный результат должен быть примерно такой:

```json
{
  "enabled": true,
  "available": true,
  "json_ok": true,
  "model": "qwen3-14b-instruct-q4_k_m"
}
```

Если `available=false`, проверь:

1. запущен ли `llama-server`;
2. совпадает ли порт `8081`;
3. стоит ли `LOCAL_LLM_ENABLED=true`;
4. не закрыто ли окно с моделью;
5. не заблокировал ли Windows Firewall локальный сервер.

## 8. Проверить из интерфейса

Запусти frontend:

```powershell
cd C:\projects\control-work-generator\frontend
npm run dev
```

В интерфейсе открой ФОС и банк заданий. Визуально основной блок теперь называется `Context-module`, потому что для ВКР мы показываем объяснимый контекст генерации. Qwen работает внутри как дополнительный LLM-refiner, если включен в `.env`.

## 9. Как понять, что Qwen реально сработала

После генерации в предупреждениях может появиться сообщение:

```text
Локальная LLM улучшила формулировки заданий: ...; модель: qwen3-14b-instruct-q4_k_m.
```

Также у части заданий источник может быть:

```text
LLM-refiner
```

Если такого нет, но генерация прошла, значит система работала через context-module, базу знаний и антидубли без LLM-редактора.

## 10. Рекомендуемый порядок запуска каждый раз

1. Запустить `llama-server` или `scripts\windows\start_qwen.ps1`.
2. Запустить backend или `scripts\windows\start_backend.ps1`.
3. Запустить frontend или `scripts\windows\start_frontend.ps1`.
4. Открыть интерфейс и генерировать задания.

## 11. Важное по GitHub

Файлы моделей нельзя коммитить. В `.gitignore` уже добавлены:

```text
*.gguf
*.safetensors
*.bin
*.pt
*.pth
backend/storage/models/*
```

Если GitHub Desktop вдруг покажет модель в изменениях, не коммить ее.
