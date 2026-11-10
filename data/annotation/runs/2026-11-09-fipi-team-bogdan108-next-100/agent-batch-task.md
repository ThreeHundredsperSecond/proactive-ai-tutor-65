# ТЗ агенту: разметка одной партии ФИПИ (бронь Bogdan108, следующие 100)

Номер партии указывает пользователь в сообщении («Партия: N»). Если номер не указан, спроси и ничего не запускай.

| Параметр | Значение |
|---|---|
| Репозиторий | `/Users/bogdanlukancuk/proactive-ai-tutor-65` |
| Ветка | `annotation/bogdan108-fipi-next-100` |
| Каталог партии (`RUN`) | `data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100` |
| Бронь | [Issue #4](https://github.com/ThreeHundredsperSecond/proactive-ai-tutor-65/issues/4), `reserved`, методика `fipi-extension-v1.1` |
| Партии | 1–8 (15+15+15+5 и ещё раз 15+15+15+5) |
| Модель агентов | `claude-opus-5-5`: в Agent — `model: opus`, `effort: low` (минимальный уровень рассуждений; отключить их полностью нельзя) |

## Твоя роль

Ты координатор партии. Задачи не решаешь и навыки (KC) не сопоставляешь. Это делают отдельные свежие субагенты: один автор и один аудитор на каждую задачу. Ты запускаешь их, ведёшь журнал, проверяешь результат, обновляешь README, коммитишь, отправляешь в ветку и отчитываешься пользователю. Пользователь поручил тебе ровно одну партию.

Сначала прочитай `AGENTS.md`, `$RUN/README.md`, разделы о ролях и health checks в `docs/eda/team-handoff.md` и `python3 scripts/fipi_team_batch.py --help`. Образец записи партий — [README брони #2](../2026-11-07-fipi-team-bogdan108-051-150/README.md), раздел «Ход работы».

## 1. Предстартовые проверки

```bash
cd /Users/bogdanlukancuk/proactive-ai-tutor-65
git switch annotation/bogdan108-fipi-next-100 && git pull --ff-only
git status --short
RUN=data/annotation/runs/2026-11-09-fipi-team-bogdan108-next-100
python3 -B scripts/fipi_team_batch.py verify --run $RUN
python3 -B scripts/fipi_team_batch.py status --run $RUN
python3 -c "import json;print(' '.join(json.load(open('$RUN/manifest.json'))['batches']['N']))"
```

Остановись и сообщи пользователю, если:

- рабочее дерево не чистое;
- `verify` упал;
- бронь не `reserved`;
- у партии N уже есть авторы или аудиты;
- у предыдущих партий брони нет `health_check: true`;
- N = 5, а накопленного EDA после партий 1–4 и приёмки этой контрольной точки координатором ещё нет. Это условие брони: после первых 50 задач — EDA и приёмка до следующего блока.

Если нет `.venv/bin/python`, создай окружение: `python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements-data.txt`.

## 2. Авторы

Для каждого ID партии:

1. `python3 -B scripts/fipi_team_batch.py exec-start --run $RUN --role author --task ID --model claude-opus-5-5`. Команда печатает сообщение для агента и пишет журнал `executions/author-ID.json` с этой моделью.
2. Запусти нового субагента: инструмент Agent, `subagent_type: general-purpose`, `model: opus`, `effort: low`. Промпт — напечатанное сообщение дословно, без добавлений: никакого контекста, подсказок или ожидаемых ответов. Одна задача — один агент. Авторов всей партии можно запускать параллельно.
3. Сразу после запуска: `python3 -B scripts/fipi_team_batch.py attach --run $RUN --role author --task ID --agent-id <ID агента из результата Agent> --model-requested "opus; effort=low"`.
4. Дождись уведомления о завершении (файлы вывода агентов не читай и не опрашивай), затем: `python3 -B scripts/fipi_team_batch.py exec-finish --run $RUN --role author --task ID --message "<из отчёта агента: сохранённый путь, просмотренные image_files, любые отступления>"`.
   - `technical_pass` → запускай аудитора этой задачи (раздел 3).
   - `technical_fail` или ответа нет → аудитора не запускай и ничего не исправляй. Продолжи остальные задачи, в конце сообщи пользователю. Повтор допустим только отдельной попыткой в `attempts/` по решению пользователя; `exec-start` повторно не запустится, это защита.

## 3. Аудиторы

Только для задач, где автор получил `technical_pass`:

1. `python3 -B scripts/fipi_team_batch.py exec-start --run $RUN --role auditor --task ID --model claude-opus-5-5`. Команда сама соберёт `requests/auditor-v1.1/ID.txt`: условие, изображения, ответ автора, каталог и допустимые ссылки.
2. Новый субагент: `general-purpose`, `model: opus`, `effort: low`, промпт — напечатанное сообщение дословно.
3. `attach --role auditor ... --model-requested "opus; effort=low"` с ID агента.
4. После завершения `exec-finish --role auditor ... --message "<из отчёта: путь, изображения, отступления>"`.

### Обрыв агента (лимит API, сетевая ошибка)

Новый `exec-start` для той же роли и задачи не запускай.

- Агент оборвался **до записи ответа** (файла в `raw/` нет) — после восстановления продолжи того же агента через SendMessage нейтральным сообщением без подсказок по задаче: «Работа была прервана лимитом API; лимит сброшен. Продолжи исходную задачу с места остановки по тем же правилам.». Возобновление отметь в `--message`. Пример — аудиторы партии 6 брони #2.
- Агент **записал ответ, но оборвался до отчёта о завершении** — такой ответ не принимается. До коммита удали незакоммиченные файлы этой задачи и роли в `raw/`, `executions/`, `validations/` и, для аудитора, `requests/auditor-v1.1/`. Затем запусти свежего агента заново и отметь повтор в `--message`. Пример — аудиторы партии 11 брони #2.

## 4. Чего не делать

- Не решать задачи и не помогать агентам. Не править `raw/author/` и `raw/auditor/`, не менять вердикты аудитора, не объединять и не переименовывать KC, не трогать каталог.
- Не передавать агентам ничего сверх сообщения из `exec-start`: ни каталога автору, ни ответов других задач, ни ожиданий из `checks/`.
- Не менять исторические каталоги `data/annotation/runs/2026-10-31-...`, `2026-11-02-...`, `2026-11-07-...`, реестр и заявки в `data/annotation/team/`, сохранённые EDA и исторические скрипты.
- Не запускать задачи вне партии N и не начинать следующую партию.
- Не создавать ветки, не сливать, не делать `push --force`.

Отступления агентов (увеличенная копия рисунка вне репозитория, черновик во временной папке, собственный скрипт проверки, перезапись своего файла) не исправляй. Записывай их в `--message` и в README каталога.

## 5. Health check партии

```bash
PY=.venv/bin/python
$PY -B scripts/fipi_team_batch.py health-math   --run $RUN --batch N
$PY -B scripts/fipi_team_batch.py health-render --run $RUN --batch N
```

- `health-math` сверяет ответы контрольных задач с ожиданиями `checks/batch-NN-math-expected.json`, записанными в этом каталоге до любых авторских ответов. При `mismatch` остановись: `health-finish` не запускай, ответы не исправляй, покажи расхождение пользователю.
- Если `mismatch` вызван только записью ответа (нормализация строки, ответ из нескольких пунктов), это решает пользователь. При его согласии прежняя сверка сохраняется как `checks/batch-NN-math.v0-normalizer.json`, а сравнение после просмотра ответа записывается в `checks/batch-NN-math-review.json` (`verdict: equivalent`, `after_seeing_answer: true`, `author_answer` — дословно ответ автора). Повторный `health-math` даёт статус `match_after_review`. Образцы — партии 7, 9, 11, 12 брони #2. В этой брони ответ из двух пунктов ожидается у E87882 (партия 3), 73BE23 (5) и 5E7BDE (7).
- `health-render` открывает Chrome без окна и проверяет загрузку изображений и отрисовку MathML.
- Сам открой инструментом Read скриншоты контрольных карточек `$RUN/checks/batch-NN-<ID>.png`; ID берутся из `checks/batch-NN-sample-plan.json`, NN — номер партии из двух цифр. Убедись, что условие, формулы и рисунок видны целиком и совпадают с тем, как их прочитали автор и аудитор.
- Запиши просмотр: `$PY -B scripts/fipi_team_batch.py health-visual --run $RUN --batch N --reviewer "primary assistant (Claude Code) via Read of Chrome screenshots" --findings '<JSON>'`. Формат находки: `{"task_id": "...", "kind": "note|procedure|input", "systemic": false, "description": "..."}`. Если находок нет, передай `'[]'`.
- `$PY -B scripts/fipi_team_batch.py health-finish --run $RUN --batch N` создаёт `checks/batch-NN.json` со статусом `pass` или `quarantine` (`quarantine`, если статус не `solved` или есть блокирующее замечание). При карантине остановись и покажи задачу пользователю. Задачу без блокирующих замечаний пользователь может принять после просмотра: решение записывается в `checks/batch-NN-quarantine-resolution.json`, прежняя сборка переименовывается в `*.v0-before-resolution.json`, `health-finish` запускается заново и отмечает задачу как `accepted_after_review`. Образец — 321FCD в партии 8 брони #2.

## 6. Сводка и README

Посчитай по партии:

```bash
python3 - "$RUN" N <<'EOF'
import json, sys, collections
from pathlib import Path
run, b = Path(sys.argv[1]), sys.argv[2]
ids = json.load(open(run/'manifest.json'))['batches'][b]
st, sol = collections.Counter(), collections.Counter(); steps = kc = iss = blk = 0
for t in ids:
    a = json.load(open(run/'raw/author'/(t+'.json'))); q = json.load(open(run/'raw/auditor'/(t+'.json')))
    sol[a['solution_status']] += 1; steps += len(a['steps']); kc += len(a['kc_candidates'])
    st.update(x['status'] for x in q['decisions']); iss += len(q['issues']); blk += sum(i['blocking'] for i in q['issues'])
print(len(ids), dict(sol), steps, kc, dict(st), iss, blk)
EOF
```

В `$RUN/README.md`, раздел «Ход работы»:

- заполни строку партии в таблице;
- замени строку «Партии ещё не запускались» абзацами о выполненных партиях в формате брони #2: состав и валидность, шаги и KC, решения аудиторов, замечания, контрольные задачи со ссылками на `checks/`, отступления;
- в разделе «Ещё не сделано» оставь только невыполненное.

Пиши по-русски, только факты, источники и ограничения. Не пиши о разрешениях пользователя и внутренних действиях агента. Не называй `new_candidate` новыми уникальными навыками: межзадачной консолидации нет.

## 7. Коммит и отправка

```bash
python3 -B scripts/fipi_team_batch.py verify --run $RUN
git add $RUN
git commit -m "data: annotate and audit FIPI next-100 batch N (Bogdan108, K tasks)"
git push
```

Коммить только каталог партии. `.venv` и временные файлы не коммить. Коммиты от имени пользователя, без строки `Co-Authored-By` и без пометок «Generated with Claude Code».

## 8. Отчёт и остановка

Кратко сообщи пользователю:

- сколько пар готово и технически валидно;
- статусы решений авторов;
- решения аудиторов;
- блокирующие замечания и карантин;
- результат сверки контрольных задач и просмотра скриншотов;
- отступления агентов;
- хеш коммита.

Затем остановись. Следующую партию запускай только по новому поручению. После партии 4 напомни, что до партии 5 по условию брони нужен накопленный EDA и приёмка контрольной точки координатором.
