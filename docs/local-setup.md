# Локальная среда

## Текущий результат и пересчёт

6 ноября 2026: для чтения и сдачи используйте [единый EDA.ipynb](../notebooks/checkpoint-2/EDA.ipynb) с уже сохранёнными результатами. Веб-сервис и повторный сбор данных не нужны.

Из корня репозитория:

```powershell
.venv/Scripts/python.exe -B -X utf8 scripts/build_checkpoint2.py
.venv/Scripts/python.exe -B -X utf8 scripts/verify_checkpoint2.py
```

Зависимости — [requirements-local.txt](../scripts/requirements-local.txt); версии проверенного исполнения — в [журнале EDA](../notebooks/checkpoint-2/derived/verification.json). Ядро Jupyter при исполнении использует локальное соединение. Архивные пути разрешаются по карте переносов, данные и старые манифесты не переписываются. Старые команды подготовки экспериментов ниже относятся к истории, а не к текущей точке запуска.

## История настройки 25 октября

Подготовлена 25 октября 2026 года на Windows, PowerShell 7.6.5. Ветка: `docs/full-ege-math-scope`. Слияние и push не выполнялись.

## Что установлено

- Git 2.55.0.windows.5.
- Python 3.12.13 из существующего Conda-окружения `jupyter`.
- Отдельная `.venv` в корне проекта: JupyterLab 4.6.4, ipykernel 7.4.0, lxml 6.1.3. Исходное Conda-окружение не менялось.
- Прямые зависимости: [scripts/requirements-local.txt](../scripts/requirements-local.txt). Диапазоны версий не являются lock-файлом; снимок установленных версий сохранён локально в `.venv/installed-packages.txt`.

Корень локальной копии: `C:\Users\U_M35CB\Documents\ВШЭ\proactive-ai-tutor-65`.

## Работа в PowerShell

Открыть терминал в корне проекта. Активация окружения не обязательна:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m jupyterlab
```

Остановить JupyterLab: `Ctrl+C` в том же терминале. Это необязательный интерактивный способ работы; для чтения сохранённого результата запускать его не требуется.

В Jupyter выбрать ядро `Python (proactive-ai-tutor-65)`, зарегистрированное внутри `.venv`. Проверены запуск этого ядра, выполнение Python-кода с импортом lxml и завершение; проверка прошла вне ограниченного терминала. `pip check` ошибок не нашёл.

Запуск Python-скрипта:

```powershell
.\.venv\Scripts\python.exe -X utf8 путь\к\скрипту.py
```

`-X utf8` нужен для существующих скриптов, в которых чтение/запись текста не везде задаёт кодировку явно. Сборщик без `--offline` обращается к источнику и перезаписывает снимок; для текущей работы он не нужен.

## Восстановление окружения на этом компьютере

Если `.venv` ещё не существует:

```powershell
& "$env:USERPROFILE\miniconda3\envs\jupyter\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-local.txt
.\.venv\Scripts\python.exe -m pip check
```

В ограниченном терминале создание pip столкнулось с запретом записи в системную временную папку. Рабочий обход в том же сеансе PowerShell:

```powershell
New-Item -ItemType Directory -Force .venv\tmp | Out-Null
$env:TEMP = Join-Path (Get-Location) '.venv\tmp'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip
```

После этого повторить установку зависимостей. Изменение TEMP/TMP действует только в текущем процессе терминала.

`conda.exe` при первом запуске сообщил об ошибке Windows DLL. Команда `& "$env:USERPROFILE\miniconda3\python.exe" -m conda env list` работает; для обычной работы с `.venv` Conda вызывать не требуется.

## Переводы строк и сохранность данных

Глобальный Git использовал `core.autocrlf=true`: при клонировании у 125 SVG изменились байты переводов строк. Для этого репозитория установлено `git config --local core.autocrlf input`, SVG восстановлены до совпадения с манифестом. Глобальная настройка не менялась; содержательных изменений данных нет.

Проверены 19 JSONL-записей, уникальность ID, позиции 1–19, наличие, размеры и SHA-256 всех 134 изображений. Это техническая проверка сохранности, не математическая валидация.

## Точка продолжения

Реализованы сборщик одного варианта и скрипты проверки прежнего пилота; общего механизма вызова LLM, подготовки мультимодальных запросов и ноутбука пайплайна пока нет. Новые задачи не собирались, разметка и LLM-запросы не запускались.

Следующий шаг — обсудить состав артефактов и размещение по [Source review 2](eda/04-annotation/03-what-to-analyze.md#source-review-2--рабочая-схема-пайплайна), затем реализовывать. Кандидаты для отладки: позиции 1 (рисунок) и 6 (формула). Модель и механизм её вызова ещё не выбраны.

Позднее в тот же день выполнен [агентный пилот на этих двух заданиях](../data/annotation/runs/2026-10-25-agent-pilot-01/README.md), без API-клиента. Это состояние раннего пилота; дальнейшие этапы описаны в [истории исследования](research-history.md).

Следующее обновление: создан [ноутбук анализа](../research/archive/notebooks/annotation-review.ipynb) и получены [57 ответов на 19 задач](../data/annotation/runs/2026-10-25-A-19x3/README.md). В `.venv` добавлен matplotlib; зависимости перечислены в `scripts/requirements-local.txt`, точный снимок пакетов — в `requirements-frozen.txt` нового запуска. Порядок Run All и восстановление артефактов описаны в README запуска.
