"""Add explicit reference dictionary to audit packets before main execution.

Pure format wrapper, no suggested KC assignments; original prompt is preserved.
"""
import argparse
import json
from pathlib import Path

from fipi_extension import RUN, ROOT, read, freeze, audit_request

WRAPPER = '''
Обвязка ссылок v1.1 (уточнение формата, критерии сопоставления не меняются).
Пути image_files предназначены для открытия изображений, НЕ для evidence.ref.
В evidence.ref, context_refs и issues.refs используй только значения из allowed_refs.
Для image:assets/... вместо quote укажи region_description.
Текстовая quote — непрерывная буквальная подстрока исходного поля, с теми же
знаками и пробелами. condition здесь HTML, его нельзя цитировать как пересказ
или очищенный текст. При необходимости ссылайся на буквальные action/result.
Не создавай условные s0/i1 из шаблона: каждый ID должен существовать.
Если image evidence содержит лишь слова «на рисунке», опиши конкретную область
и наблюдаемые объекты, а не только факт наличия рисунка.
'''


def main():
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--author-path')
    a=p.parse_args();audit_request(a.task,author_path=a.author_path)
    inp=read(RUN/'inputs/tasks'/(a.task+'.json'))
    d=read(ROOT/a.author_path if a.author_path else RUN/'raw/author'/(a.task+'.json'))
    refs=['condition']+[f'step:{s["id"]}:{k}' for s in d['steps'] for k in ['action','result']]
    refs+=['image:'+x['path'] for x in inp['assets']]
    freeze(RUN/'audit-format-wrapper-v1.1.txt',WRAPPER)
    packet=(RUN/'requests/auditor'/(a.task+'.txt')).read_text(encoding='utf-8')
    packet+='\n'+WRAPPER+'\n'+json.dumps({'allowed_refs':refs},ensure_ascii=False,indent=2)+'\n'
    dest=RUN/'requests/auditor-v1.1'/(a.task+'.txt');freeze(dest,packet);print(dest.relative_to(ROOT).as_posix())


if __name__=='__main__':main()
