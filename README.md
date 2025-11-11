# Работа с нейроинтерфейсами - Лабораторная работа № 5 & 6

Приложение для снятия биометрических сигналов (ЭЭГ, ЭКГ, ЭМГ, ФПГ, КГР)
с помощью нейроинтерфейсов.

## Быстрый старт
Для использования приложения требуется как минимум Python 3.12.

### Установка

> Проект использует `pyproject.toml` (setuptools) и `requirements.txt`.
> Зависимости читаются из `requirements.txt` автоматически при установке пакета.

1. Создайте и активируйте виртуальное окружение:

**Windows (PowerShell):**
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
py -m venv .venv
.venv\Scripts\activate.bat
```

**Linux, macOS**:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Обновите инструменты сборки:
```bash
python -m pip install --upgrade pip setuptools wheel
```

3. Установите пакет в режиме разработки (рекомендуется):
```bash
pip install -e .
```

Это установит сам пакет и зависимости из requirements.txt.

Альтернатива (необязательно): можно сначала поставить зависимости вручную,
а затем пакет:

```bash
pip install -r requirements.txt
pip install -e .
```

4. Запуск:
```bash
python main.py

```

