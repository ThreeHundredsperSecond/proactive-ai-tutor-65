"""Prepare one full A-FIPI request, including all 13 literal requirements. No API."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / 'docs/eda/01-exam/requirements-map.md'
OLD = ROOT / 'data/annotation/runs/2026-10-25-A-19x3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, text):
    path = HERE / name
    data = text.encode('utf-8')
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f'Refusing to overwrite frozen {name}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


catalog = []
for line in SOURCE.read_text(encoding='utf-8').splitlines():
    cells = [c.strip() for c in line.strip().strip('|').split('|')]
    if len(cells) == 5 and cells[0].isdigit():
        catalog.append({'code': cells[0], 'requirement': cells[1], 'level': cells[2], 'pdf_printed_pages': cells[4]})
assert [r['code'] for r in catalog] == [str(n) for n in range(1, 14)]
save('catalog.json', json.dumps({'source': 'ФИПИ, таблица 2, кодификатор ЕГЭ 2027, сохранённый проект', 'requirements': catalog}, ensure_ascii=False, indent=2) + '\n')
a_path = ROOT / 'docs/eda/04-annotation/02.1-prompting-pilot/prompts/A.txt'
a = a_path.read_text(encoding='utf-8')
save('original-A.txt', a)
intro = a[:a.index('Итоговая структура')]
delta = '''Рамка A-FIPI-v1:
Полный перечень предметных требований дан ниже в FIPI_REQUIREMENTS. Это фиксированные верхние классы, не готовый каталог атомарных KC. Коды и формулировки не изменяй и новые официальные коды не придумывай.
Сначала определи предположительно применимые требования. Самостоятельно реши задачу, не ограничивая способ решения первоначальным выбором, затем уточни выбранные требования по реально выполненным шагам.
Внутри выбранных требований сформулируй конкретные переиспользуемые KC по выполненным действиям. Не подменяй конкретное действие целой формулировкой широкого требования. Не перечисляй остальные понятия выбранного требования, если они не использованы в решении.
Для каждого KC запиши связь с подходящим требованием в fipi_links: requirement_code, kc_ids, anchor (точный непрерывный фрагмент requirement из перечня) и reason (почему выполненное действие соответствует этому фрагменту). Свидетельства применения KC находятся в steps.kc_ids. Один KC может иметь несколько обоснованных связей.
Если уверенной связи нет, сохрани её с requirement_code=null, anchor="" и конкретной причиной. Не удаляй нужное математическое действие, чтобы подогнать его под каталог.
В selected_requirements перечисли только коды фактически обоснованных требований. Само наличие общей арифметики не требует добавления всех широких классов: обосновывай выбор существенным действием. Это классификация проекта по официальной рамке, а не официальная разметка ФИПИ.
'''
save('delta-FIPI.txt', delta)
schema = {'task_id': '...', 'selected_requirements': ['код из перечня'], 'solution_status': 'solved|partial|unsolved',
          'steps': [{'id': 's1', 'action': '...', 'result': '...', 'kc_ids': ['k1']}],
          'kc_candidates': [{'id': 'k1', 'name': '...', 'description': '...'}],
          'methods': [{'id': 'm1', 'name': '...', 'step_ids': ['s1']}],
          'fipi_links': [{'requirement_code': 'код из перечня или null', 'kc_ids': ['k1'], 'anchor': 'точный фрагмент требования', 'reason': '...'}], 'warnings': []}
template = intro + delta + '\nВерни только JSON строго с этими полями:\n' + json.dumps(schema, ensure_ascii=False) + '\nВсе id уникальны внутри типа; ссылки должны существовать. Все KC применены в шагах и отражены в fipi_links. Неиспользованных KC и пустых методов нет. Допустимые solution_status: solved, partial, unsolved. Необоснованные места отмечай в warnings.\n\nFIPI_REQUIREMENTS:\n' + (HERE / 'catalog.json').read_text(encoding='utf-8') + '\nЗАДАЧА:\n{task_json}\n'
save('prompt-A-FIPI-v1.txt', template)
inp = OLD / 'inputs/699086.json'
payload = json.loads(inp.read_text(encoding='utf-8'))
save('input.json', json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
for im in payload['images']:
    path = HERE / im['path']
    path.parent.mkdir(exist_ok=True)
    data = (OLD / im['path']).read_bytes()
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Frozen image differs')
    path.write_bytes(data)
request = template.replace('{task_json}', json.dumps(payload, ensure_ascii=False, indent=2))
assert '{task_json}' not in request
assert all(row['requirement'] in request for row in catalog)
save('request.txt', request)
job = 'Прочитай только запрос ' + (HERE / 'request.txt').as_posix() + '. '
job += ''.join('Просмотри через view_image ' + (HERE / im['path']).as_posix() + '. ' for im in payload['images'])
job += 'Не читай другие файлы проекта, каталогов или старых ответов. Каталог ФИПИ уже целиком включён в запрос. Загрузка запроса/изображений и запись ответа — разрешённые технические действия. После загрузки решай без инструментов, поиска и проверки. Полностью готовый JSON сохрани без Markdown в ' + (HERE / 'raw.txt').as_posix() + ', не перезаписывая существующий файл. Верни только путь raw.txt.\n'
save('job.txt', job)
files = ['original-A.txt', 'catalog.json', 'delta-FIPI.txt', 'prompt-A-FIPI-v1.txt', 'input.json', 'request.txt', 'job.txt'] + [im['path'] for im in payload['images']]
manifest = {'trial': HERE.name, 'expected_responses': 1, 'mode': 'independent_solution_from_statement_and_images',
            'source_catalog': SOURCE.relative_to(ROOT).as_posix(), 'source_catalog_sha256': sha(SOURCE),
            'original_A_sha256': sha(a_path), 'catalog_codes': [row['code'] for row in catalog],
            'prepare_script_sha256': sha(Path(__file__)), 'runtime': 'one isolated agent, fork_turns=none, no override; model parameters unknown',
            'files': {name: sha(HERE / name) for name in files},
            'precheck_criteria': ['all 13 exact requirements physically present in request', 'real codes and exact anchors', 'KC evidence in steps', 'no unused listed concepts', 'independent vector solution; examine classification and granularity separately'],
            'limits': 'One known example; primary-agent nonblind review; no expert standard or stability estimate.'}
save('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('Prepared full request:', HERE / 'request.txt', '| requirements:', len(catalog), '| images:', len(payload['images']))
