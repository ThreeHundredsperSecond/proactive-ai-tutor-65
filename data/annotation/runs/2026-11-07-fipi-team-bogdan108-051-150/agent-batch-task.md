# ТЗ агенту: разметка одной партии ФИПИ (бронь Bogdan108, очередь 51–150)

Номер партии указывает пользователь в сообщении («Партия: N»). Если номер не указан, спроси и ничего не запускай.

| Параметр | Значение |
|---|---|
| Репозиторий | `/Users/bogdanlukancuk/proactive-ai-tutor-65` |
| Ветка | `annotation/bogdan108-fipi-51-150` |
| Каталог партии (`RUN`) | `data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150` |
| Бронь | [Issue #2](https://github.com/ThreeHundredsperSecond/proactive-ai-tutor-65/issues/2), `reserved`, методика `fipi-extension-v1.1` |
| Партии | 5–12 (15+15+15+5 и ещё раз 15+15+15+5); партия 5 выполнена |

## Твоя роль

Ты координатор партии. Задачи не решаешь и навыки (KC) не сопоставляешь. Это делают отдельные свежие субагенты: один автор и один аудитор на каждую задачу. Ты запускаешь их, ведёшь журнал, проверяешь результат, обновляешь README, коммитишь, отправляешь в ветку и отчитываешься пользователю. Пользователь поручил тебе ровно одну партию.

Сначала прочитай `AGENTS.md`, `$RUN/README.md` (там образец записи партии 5), разделы о ролях и health checks в `docs/eda/team-handoff.md` и `python3 scripts/fipi_team_batch.py --help`.

## 1. Предстартовые проверки

```bash
cd /Users/bogdanlukancuk/proactive-ai-tutor-65
git switch annotation/bogdan108-fipi-51-150 && git pull --ff-only
git status --short
RUN=data/annotation/runs/2026-11-07-fipi-team-bogdan108-051-150
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
- N = 9, а промежуточного EDA на накопленных 150 задачах ещё нет. Это условие брони: после первых 50 новых задач (партии 5–8) нужен EDA-150 и сверка с EDA-100.

Если нет `.venv/bin/python`, создай окружение: `python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements-data.txt`.

## 2. Авторы

Для каждого ID партии:

1. `python3 -B scripts/fipi_team_batch.py exec-start --run $RUN --role author --task ID`. Команда печатает сообщение для агента и пишет журнал `executions/author-ID.json`.
2. Запусти нового субагента: инструмент Agent, `subagent_type: general-purpose`, `model: opus`. Промпт — напечатанное сообщение дословно, без добавлений: никакого контекста, подсказок или ожидаемых ответов. Одна задача — один агент. Авторов всей партии можно запускать параллельно.
3. Сразу после запуска: `python3 -B scripts/fipi_team_batch.py attach --run $RUN --role author --task ID --agent-id <ID агента из результата Agent>`.
4. Дождись уведомления о завершении (файлы вывода агентов не читай и не опрашивай), затем: `python3 -B scripts/fipi_team_batch.py exec-finish --run $RUN --role author --task ID --message "<из отчёта агента: сохранённый путь, просмотренные image_files, любые отступления>"`.
   - `technical_pass` → запускай аудитора этой задачи (раздел 3).
   - `technical_fail` или ответа нет → аудитора не запускай и ничего не исправляй. Продолжи остальные задачи, в конце сообщи пользователю. Повтор допустим только отдельной попыткой в `attempts/` по решению пользователя; `exec-start` повторно не запустится, это защита.

## 3. Аудиторы

Только для задач, где автор получил `technical_pass`:

1. `python3 -B scripts/fipi_team_batch.py exec-start --run $RUN --role auditor --task ID`. Команда сама соберёт `requests/auditor-v1.1/ID.txt`: условие, изображения, ответ автора, каталог и допустимые ссылки.
2. Новый субагент: `general-purpose`, `model: opus`, промпт — напечатанное сообщение дословно.
3. `attach --role auditor ...` с ID агента.
4. После завершения `exec-finish --role auditor ... --message "<из отчёта: путь, изображения, отступления>"`.

## 4. Чего не делать

- Не решать задачи и не помогать агентам. Не править `raw/author/` и `raw/auditor/`, не менять вердикты аудитора, не объединять и не переименовывать KC, не трогать каталог.
- Не передавать агентам ничего сверх сообщения из `exec-start`: ни каталога автору, ни ответов других задач, ни ожиданий из `checks/`.
- Не менять исторический каталог `data/annotation/runs/2026-11-02-fipi-extension-150/`, реестр `data/annotation/team/` и исторические скрипты.
- Не запускать задачи вне партии N и не начинать следующую партию.
- Не создавать ветки, не сливать, не делать `push --force`.

Отступления агентов (увеличенная копия рисунка вне репозитория, черновик во временной папке, собственный скрипт проверки цитат) не исправляй. Записывай их в `--message` и в README партии.

## 5. Health check партии

```bash
PY=.venv/bin/python
$PY -B scripts/fipi_team_batch.py health-math   --run $RUN --batch N
$PY -B scripts/fipi_team_batch.py health-render --run $RUN --batch N
```

- `health-math` сверяет ответы контрольных задач с ожиданиями, записанными до любых авторских ответов. При `mismatch` остановись: `health-finish` не запускай, ответы не исправляй, сообщи пользователю. Это повод разобрать задачу или отправить её в карантин. `not_checked` допустимо, укажи это в отчёте.
- `health-render` открывает Chrome без окна и проверяет загрузку изображений и отрисовку MathML.
- Сам открой инструментом Read скриншоты контрольных карточек `$RUN/checks/batch-NN-<ID>.png`; ID берутся из `checks/batch-NN-sample-plan.json`, NN — номер партии из двух цифр. Убедись, что условие, формулы и рисунок видны целиком и совпадают с тем, как их прочитали автор и аудитор.
- Запиши просмотр: `$PY -B scripts/fipi_team_batch.py health-visual --run $RUN --batch N --reviewer "primary assistant (Claude Code) via Read of Chrome screenshots" --findings '<JSON>'`. Формат находки: `{"task_id": "...", "kind": "note|procedure|input", "systemic": false, "description": "..."}`. Если находок нет, передай `'[]'`.
- `$PY -B scripts/fipi_team_batch.py health-finish --run $RUN --batch N` создаёт `checks/batch-NN.json` со статусом `pass` или `quarantine` (`quarantine`, если статус не `solved` или есть блокирующее замечание).

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
- добавь абзац о партии в том же формате, что у партии 5: состав и валидность, шаги и KC, решения аудиторов, замечания, контрольные задачи со ссылками на `checks/`, отступления.

Пиши по-русски, только факты, источники и ограничения. Не пиши о разрешениях пользователя и внутренних действиях агента. Не называй `new_candidate` новыми уникальными навыками: межзадачной консолидации нет.

## 7. Коммит и отправка

```bash
python3 -B scripts/fipi_team_batch.py verify --run $RUN
git add $RUN
git commit -m "data: annotate and audit FIPI queue batch N (Bogdan108, K tasks)"
git push
```

Коммить только каталог партии. `.venv` и временные файлы не коммить.

## 8. Отчёт и остановка

Кратко сообщи пользователю:
- сколько пар готово и технически валидно;
- статусы решений авторов;
- решения аудиторов;
- блокирующие замечания и карантин;
- результат сверки контрольных задач и просмотра скриншотов;
- отступления агентов;
- хеш коммита.

Затем остановись. Следующую партию запускай только по новому поручению. После партии 8 напомни, что до партии 9 по условию брони нужен промежуточный EDA на 150 задачах.
