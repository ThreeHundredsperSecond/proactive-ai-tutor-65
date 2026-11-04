# Проверка офлайн-отчёта

2 ноября 2026. Скрипт `scripts/report_fipi_extension.py` не вызывает моделей и сети.

- `progress --count 50 --no-notebook` завершился: 0 завершённых новых пар, исторические 49 задач в основных частотах. Снимок `progress-2a016b379cd44770` сохранён до последующих правок версии скрипта; это не checkpoint.
- `report --count 50` ожидаемо отказал: нужны 50 технически валидных пар, сохранено 0. Артефакт checkpoint не создан.
- `offline-fixture-tests/test_report.py`: пять тестов прошли. Проверены Cartesian-переходы между соседними multiKC-шагами с присутствием один раз на задачу, отсутствие переходов между методами; отсутствие объединения одноимённых несопоставленных кандидатов; исключение задачи с блокировкой; исключение старого partial; запрет пути активной попытки за пределы RUN.
- Первый запуск исполнения notebook завис в sandbox до получения результата ядра. Остановлен только его exec session 68449 через Ctrl+C. Частичный каталог `progress-75e188c3010271d5.building` сохранён для просмотра, завершённым отчётом не является.
- Исполнение notebook: **pending**, не выдаётся за пройденное. В коде теперь startup_timeout=30, timeout=120 и `.venv/Scripts` в PATH; для реального checkpoint root при необходимости выполнит разрешённый escalated запуск. Дополнительных notebook на пустых данных не запускали.

CLI из корня репозитория:

```powershell
.venv/Scripts/python.exe scripts/report_fipi_extension.py progress --count 50 --no-notebook
.venv/Scripts/python.exe scripts/report_fipi_extension.py report --count 50
.venv/Scripts/python.exe scripts/report_fipi_extension.py report --count 100
.venv/Scripts/python.exe scripts/report_fipi_extension.py report --count 150
.venv/Scripts/python.exe data/annotation/runs/2026-11-02-fipi-extension-150/derived/offline-fixture-tests/test_report.py
```

`--count` — число **новых** задач; totals соответственно 100/150/200. Checkpoint требует все соответствующие health checks. Изменившиеся входные хеши не перезаписывают checkpoint; осознанная новая версия сохраняется через `--version v2`. Progress допускает неполноту; вариант без исполнения notebook получает суффикс `-without-notebook`.
