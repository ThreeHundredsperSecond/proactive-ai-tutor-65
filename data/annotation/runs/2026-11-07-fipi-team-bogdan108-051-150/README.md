# ФИПИ: командная партия Bogdan108, очередь 51–150

Заявка: [Issue #2](https://github.com/ThreeHundredsperSecond/proactive-ai-tutor-65/issues/2). Методика `fipi-extension-v1.1`, базовый коммит `8119f21383ec6f83554da7a6d8f97f5d02bdb07d` ветки `docs/full-ege-math-scope`. Подготовлено 7 ноября 2026 года.

**Статус: бронь подтверждена координатором** ([комментарий 7 ноября](https://github.com/ThreeHundredsperSecond/proactive-ai-tutor-65/issues/2#issuecomment-6707050340)): 100 ID, партии 15+15+15+5, EDA на накопленных 150 и 200, остановка после 100. Состояние брони — [reservation.json](reservation.json).

## Состав

100 задач замороженной очереди [selection.json](../2026-11-02-fipi-extension-150/selection.json), номера 51–150. Номера партий сохранены из очереди.

| Партия | Номера | Задач |
|---|---|---:|
| 5 | 51–65 | 15 |
| 6 | 66–80 | 15 |
| 7 | 81–95 | 15 |
| 8 | 96–100 | 5 |
| 9 | 101–115 | 15 |
| 10 | 116–130 | 15 |
| 11 | 131–145 | 15 |
| 12 | 146–150 | 5 |

По первой метке КЭС: уравнения и неравенства 35, геометрия 29, начала анализа 15, числа и вычисления 10, вероятность 8, функции 3. Точные ID и хеши — [manifest.json](manifest.json).

## Что подготовлено

- **Методика побитово** из [запуска 2026-11-02](../2026-11-02-fipi-extension-150/README.md): `PROTOCOL.md`, промпты автора и аудитора, обвязки, `catalog-for-auditor.json` (144 определения), `execution-protocol-v1.1.json`. SHA-256 совпадают с `methodology_sha256` [реестра](../../team/registry.json).
- **Условия и изображения** скопированы из [снимка банка](../../../fipi/2026-10-31-profile/README.md) и сверены с замороженными входами очереди.
- **Запросы автора** (`requests/author/`) совпадают с подготовленными в очереди, кроме абсолютных путей `image_files`. Прежние пути указывали на другую машину.
- **Заранее зафиксированные проверки** (`checks/batch-NN-sample-plan.json`, `-math-expected.json`, `-math-supplement.json`; 23 файла) скопированы без изменений. Их подготовили до любых авторских ответов на эти задачи, поэтому их можно использовать как предварительные ожидания при health check. Это не полная предметная экспертиза.
- `active-attempts.json` пуст, `environment.json` фиксирует среду подготовки.

## Отличие от задач 1–50 очереди

Задачи 1–50 решали и проверяли агенты Codex (`collaboration.spawn_agent`, модель не раскрыта). Здесь планируются отдельные свежие субагенты Claude Code на каждую роль и задачу, модель `claude-opus-5-5`. Инструкции, каталог и формат те же. Модель и среда другие, поэтому в EDA эти результаты показываются отдельным слоем происхождения и не смешиваются молча с прежними частотами.

## Команды

Из корня репозитория:

```bash
python3 scripts/fipi_team_batch.py verify  --run data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150
python3 scripts/fipi_team_batch.py status  --run data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150
# после `reserved` в Issue #2:
python3 scripts/fipi_team_batch.py reserve --run ... --confirmed-by <координатор> --comment-url <ссылка на комментарий>
python3 scripts/fipi_team_batch.py exec-start  --run ... --role author --task <ID>
python3 scripts/fipi_team_batch.py exec-finish --run ... --role author --task <ID> --agent-id <ID агента>
```

Для аудитора `exec-start --role auditor` собирает запрос `requests/auditor-v1.1/<ID>.txt` из сохранённого ответа автора: условие, изображения, ответ, каталог, обвязка v1.1 и список допустимых ссылок. `exec-finish` проверяет ответ историческими валидаторами (`fipi_eda50.validate_one`, `fipi_extension.validate_audit`) и пишет результат в `validations/`.

Скрипт проверен на сохранённых задачах 1–50 очереди без записи в исторический каталог. Валидаторы приняли 50/50 разборов и 50/50 аудитов. Запросы аудитору, собранные новым кодом, совпали с историческими: 39 байт в байт, 10 с точностью до путей изображений, одна задача с исправленной попыткой не сравнивалась.

## Ещё не подготовлено

- Отрисовка карточек для health check (`health_fipi_extension.py render` рассчитан на Chrome под Windows).
- Запись партии и её health check, отчёт партии, накопленный EDA на 150 и 200.
