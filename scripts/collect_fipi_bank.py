"""Collect public FIPI pages in bounded batches; stop on incomplete content.

Network calls use curl bound to a specified local interface. Offline audit never
uses the network. Raw cp1251 pages are authoritative; native MathML HTML is derived.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html as esc
import io
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

from lxml import html
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'AC437B34557F88EA4115D2F374B0A07B'
BASE = 'https://ege.fipi.ru/bank/'
DEFAULT = ROOT / 'data/fipi/2026-10-31-profile'
QPATH = '//div[contains(concat(" ",normalize-space(@class)," ")," qblock ")]'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def native_math(s):
    s = re.sub(r'<(/?)m:', r'<\1', s)
    return re.sub(r'<math(?=[\s>])', '<math xmlns="http://www.w3.org/1998/Math/MathML"', s)


def browser_math(s):
    """Expand legacy mfenced for MathML Core browsers; source MathML stays intact."""
    tree = html.fromstring(s)
    for fenced in reversed(tree.xpath('.//mfenced')):
        opening, closing = fenced.get('open', '('), fenced.get('close', ')')
        separators = ''.join(fenced.get('separators', ',').split())
        children = list(fenced)
        fenced.tag = 'mrow'
        for key in ['open', 'close', 'separators']:
            fenced.attrib.pop(key, None)
        if opening:
            op = html.Element('mo', fence='true')
            op.text = opening
            fenced.insert(0, op)
        for i, child in enumerate(children[:-1]):
            if separators:
                sep = html.Element('mo', separator='true')
                sep.text = separators[min(i, len(separators)-1)]
                child.addnext(sep)
        if closing:
            cl = html.Element('mo', fence='true')
            cl.text = closing
            fenced.append(cl)
    return html.tostring(tree, encoding='unicode')


class Collector:
    def __init__(self, args):
        self.args, self.out = args, args.out.resolve()
        for d in ['raw', 'tasks', 'assets', 'checks']:
            (self.out / d).mkdir(parents=True, exist_ok=True)
        self.requests = []

    def fetch(self, url, path):
        if path.exists():
            return path.read_bytes()
        if urlsplit(url).hostname != 'ege.fipi.ru':
            raise ValueError('Unexpected asset host: ' + url)
        safe = quote(url, safe=':/?=&%')
        for attempt in range(3):
            time.sleep(self.args.delay)
            proc = subprocess.run([
                'curl.exe', '--silent', '--show-error', '--fail', '--noproxy', '*',
                '--interface', self.args.interface,
                '--resolve', f'ege.fipi.ru:443:{self.args.server_ip}',
                '--connect-timeout', '10', '--max-time', '40', safe,
            ], capture_output=True)
            if proc.returncode == 0 and proc.stdout:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(proc.stdout)
                item = dict(url=url, path=path.relative_to(self.out).as_posix(),
                            sha256=sha(proc.stdout), bytes=len(proc.stdout), retrieved_at=now())
                with (self.out / 'downloads.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
                return proc.stdout
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f'Failed GET {url}: {proc.stderr.decode(errors="replace")}')

    def asset(self, url):
        ext = Path(urlsplit(url).path).suffix.lower()
        if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp'}:
            raise ValueError('Unsupported media, inspect before continuing: ' + url)
        name = sha(url.encode())[:24] + ext
        path = self.out / 'assets' / name
        data = self.fetch(url, path)
        if ext == '.svg':
            from lxml import etree
            etree.fromstring(data)
            size = None
        else:
            with Image.open(io.BytesIO(data)) as img:
                size = list(img.size)
                img.verify()
            assert min(size) > 0
        return dict(url=url, path='assets/' + name, sha256=sha(data), bytes=len(data), size=size)

    def parse_page(self, data, page):
        text = data.decode('cp1251')
        tree = html.fromstring(text)
        count_match = re.findall(r'setQCount\((\d+),\s*(\d+),\s*(\d+)\)', text)
        if not count_match:
            raise ValueError('No pagination declaration')
        total, current, size = map(int, count_match[-1])
        assert current == page + 1 and size == 10, (page, count_match)
        blocks = tree.xpath(QPATH)
        assert len(blocks) == min(10, total - page * 10), (page, len(blocks), total)
        records = []
        for q in blocks:
            qid = q.get('id')[1:]
            assert re.fullmatch('[A-Fa-f0-9]{6}', qid), qid
            guid = q.xpath('.//input[@name="guid"]/@value')[0]
            assert re.fullmatch('[A-Fa-f0-9]{32}', guid), guid
            cells = q.xpath('.//td[starts-with(@class,"cell_")]')
            assert cells, qid
            # Keep every content cell, including multipart/choice content.
            source = '\n'.join(html.tostring(c, encoding='unicode') for c in cells)
            wrapper = html.Element('div')
            for c in cells:
                section = html.Element('section')
                section.text = c.text
                for child in c:
                    section.append(copy.deepcopy(child))
                wrapper.append(section)
            assets = []
            for script in list(wrapper.xpath('.//script')):
                code = script.text or ''
                # Paths can contain parentheses; use complete quoted strings instead.
                if 'ShowPicture' in code:
                    strings = re.findall(r"(['\"])((?:\\.|(?!\1).)*?)\1", code)
                    paths = [v.replace('\\/', '/') for _, v in strings
                             if re.search(r'\.(?:png|jpe?g|gif|svg|webp|bmp)$', v, re.I)]
                    if not paths:
                        raise ValueError(f'Unparsed image script in {qid}: {code}')
                    # Preserve original + preview when supplied, avoiding lost high resolution.
                    for value in dict.fromkeys(paths):
                        url = urljoin('https://ege.fipi.ru/', value.replace('. ', '.'))
                        a = self.asset(url)
                        assets.append(a)
                        img = html.Element('img', src='../' + a['path'], alt='Рисунок ФИПИ')
                        script.addprevious(img)
                else:
                    raise ValueError(f'Unknown statement script in {qid}: {code}')
                script.drop_tree()
            for img in wrapper.xpath('.//img'):
                src = img.get('src') or ''
                if src.startswith('../assets/'):
                    continue
                a = self.asset(urljoin(BASE + 'questions.php', src))
                assets.append(a)
                img.set('src', '../' + a['path'])
            # Fail closed on media types not covered by the image collector.
            if wrapper.xpath('.//object|.//embed|.//iframe|.//video|.//audio|.//*[@background]|.//*[@srcset]'):
                raise ValueError('Unsupported embedded content: ' + qid)
            if any('url(' in e.get('style', '') for e in wrapper.iter()):
                raise ValueError('CSS media requires inspection: ' + qid)
            for e in wrapper.iter():
                for key in list(e.attrib):
                    if key.lower().startswith('on') or key in {'id', 'width', 'height'}:
                        del e.attrib[key]
                if e.tag == 'a' and e.get('href', '').startswith('javascript:'):
                    del e.attrib['href']
            for inp in list(wrapper.xpath('.//input|.//button')):
                inp.drop_tree()
            derived = native_math(html.tostring(wrapper, encoding='unicode'))
            before_math = len(re.findall(r'<m:math\b', source))
            assert before_math == len(re.findall(r'<math\b', derived)), qid
            source_tree = html.fromstring(source)
            source_math = [html.tostring(e, encoding='unicode', with_tail=False)
                           for e in source_tree.iter() if e.tag == 'm:math']
            derived_tree = html.fromstring(derived)
            derived_math = [html.tostring(e, encoding='unicode', with_tail=False)
                            for e in derived_tree.iter() if e.tag == 'math']
            assert [native_math(m) for m in source_math] == derived_math, ('MathML changed', qid)
            # Script text is implementation, all other statement text must survive.
            for e in list(source_tree.xpath('.//script')):
                e.drop_tree()
            assert ''.join(source_tree.itertext()).split() == ''.join(derived_tree.itertext()).split(), ('Text changed', qid)
            assert derived.count('\ufffd') == source.count('\ufffd') and '<script' not in derived, qid
            source_issues = (['replacement_character_in_source'] if '\ufffd' in source else [])
            info = tree.get_element_by_id('i' + qid)
            metadata = []
            for tr in info.xpath('.//div[@class="task-info-content"]//tr'):
                tds = tr.xpath('./td')
                if len(tds) == 2:
                    vals = tds[1].xpath('./div')
                    metadata.append(dict(label=tds[0].text_content().strip(),
                                         values=[v.text_content().strip() for v in vals] if vals
                                         else [tds[1].text_content().strip()]))
            instruction = ' '.join(q.xpath('.//div[@id="hint"]/text()')).strip()
            record = dict(id=qid, guid=guid, project=PROJECT, page=page + 1,
                          source_url=BASE + f'index.php?proj={PROJECT}&qid={qid}',
                          raw_page=f'raw/page-{page+1:03}.html',
                          raw_page_sha256=sha(data), bank_snapshot_date='2026-10-31',
                          exam_year=None,
                          raw_statement_html=source, statement_html=derived,
                          instruction=instruction, metadata=metadata, assets=assets,
                          source_issues=source_issues,
                          mathml_count=before_math,
                          answer=None, solution=None,
                          validation='technical; not mathematical review')
            dump(self.out / 'tasks' / (qid + '.json'), record)
            self.card(record)
            records.append(record)
        return total, records

    def card(self, r):
        content = ('<!doctype html><html lang="ru"><meta charset="utf-8">'
                   '<style>body{max-width:1000px;margin:32px auto;padding:0 24px;font:22px/1.6 Georgia}'
                   'img{max-width:100%;height:auto}math{font-size:1.1em}section{margin:20px 0}'
                   '.meta{font:14px/1.5 system-ui;color:#555}table{border-collapse:collapse}</style>'
                   f'<title>ФИПИ {r["id"]}</title><h2>ФИПИ · {r["id"]}</h2>' +
                   ('<p style="background:#ffe4b5;padding:12px">В исходнике ФИПИ есть повреждённый символ. '
                    'Условие сохранено без исправления; требуется проверка перед использованием.</p>'
                    if r.get('source_issues') else '') +
                   f'<p>{esc.escape(r["instruction"])}</p>' + browser_math(r['statement_html']) +
                   '<hr><div class="meta">' + ''.join('<p><b>' + esc.escape(m['label']) +
                   '</b> ' + esc.escape('; '.join(m['values'])) + '</p>' for m in r['metadata']) +
                   f'<p><a href="{esc.escape(r["source_url"])}">Источник ФИПИ</a></p></div></html>')
        (self.out / 'tasks' / (r['id'] + '.html')).write_text(content, encoding='utf-8')

    def audit(self, records, pages, total):
        ids = [r['id'] for r in records]
        guids = [r['guid'] for r in records]
        assert len(ids) == len({x.upper() for x in ids}) and len(guids) == len({x.upper() for x in guids}), 'Duplicate IDs/pages'
        for r in records:
            assert sha((self.out / r['raw_page']).read_bytes()) == r['raw_page_sha256'], r['id']
            parsed = html.fromstring(r['statement_html'])
            assert len(parsed.xpath('.//math')) == r['mathml_count'], r['id']
            assert len(parsed.xpath('.//img')) == len(r['assets']), r['id']
            assert not parsed.xpath('.//script|.//object|.//embed'), r['id']
            for a in r['assets']:
                data = (self.out / a['path']).read_bytes()
                assert sha(data) == a['sha256']
                if not a['path'].endswith('.svg'):
                    with Image.open(io.BytesIO(data)) as im:
                        im.verify()
        for page in pages:
            raw = (self.out / f'raw/page-{page:03}.html').read_bytes().decode('cp1251')
            tree = html.fromstring(raw)
            blocks = tree.xpath(QPATH)
            assert {q.get('id')[1:] for q in blocks} == {r['id'] for r in records if r['page'] == page}, ('Missing raw task', page)
            for r in (r for r in records if r['page'] == page):
                block = tree.get_element_by_id('q'+r['id'])
                raw_source = '\n'.join(html.tostring(c, encoding='unicode') for c in block.xpath('.//td[starts-with(@class,"cell_")]'))
                assert raw_source == r['raw_statement_html'], ('Raw statement mismatch', r['id'])
                assert block.xpath('.//input[@name="guid"]/@value')[0] == r['guid']
        samples = []
        for predicate in [lambda r: bool(r['assets']), lambda r: r['mathml_count'] > 0,
                          lambda r: 'развернутый' in r['instruction'] or 'развёрнутый' in r['instruction']]:
            match = next((r for r in records if predicate(r) and r['id'] not in samples), None)
            if match:
                samples.append(match['id'])
        if records[-1]['id'] not in samples:
            samples.append(records[-1]['id'])
        result = dict(checked_at=now(), pages=pages, declared_total=total, tasks=len(records),
                      mathml=sum(r['mathml_count'] for r in records),
                      tasks_with_images=sum(bool(r['assets']) for r in records),
                      unique_assets=len({a['path'] for r in records for a in r['assets']}),
                      source_warnings=[dict(id=r['id'],issues=r['source_issues']) for r in records if r.get('source_issues')],
                      samples=samples, status='passed', mathematical_review=False)
        if result['source_warnings']:
            result['status'] = 'passed_with_source_warnings'
        return result

    def run(self):
        self.fetch(BASE + 'index.php?proj=' + PROJECT, self.out / 'raw/index.html')
        all_records, batch_records, summaries = [], [], []
        total = None
        for page in range(self.args.stop_page):
            if total is not None and page >= math.ceil(total / 10):
                break
            url = BASE + f'questions.php?proj={PROJECT}&page={page}&pagesize=10'
            data = self.fetch(url, self.out / 'raw' / f'page-{page+1:03}.html')
            declared, records = self.parse_page(data, page)
            if total is not None:
                assert declared == total, 'Bank count changed during snapshot'
            total = declared
            all_records.extend(records)
            batch_records.extend(records)
            print(f'PAGE {page+1}: {len(records)} tasks; images={sum(bool(r["assets"]) for r in records)}', flush=True)
            # Validate each page immediately; then validate the whole batch and all IDs.
            self.audit(records, [page+1], total)
            if (page+1) % self.args.batch_pages == 0 or page+1 == self.args.stop_page or len(all_records) == total:
                pages = sorted({r['page'] for r in batch_records})
                check = self.audit(batch_records, pages, total)
                self.audit(all_records, list(range(1, page+2)), total)
                dump(self.out / 'checks' / f'batch-{pages[0]:03}-{pages[-1]:03}.json', check)
                summaries.append(check)
                self.export(all_records, total, summaries)
                print('BATCH HEALTH ' + json.dumps(check, ensure_ascii=False), flush=True)
                if self.args.render_check:
                    render_file = self.out / 'checks' / f'render-{pages[0]:03}-{pages[-1]:03}.json'
                    if not render_file.exists() or json.loads(render_file.read_text(encoding='utf-8')).get('renderer_version') != 2:
                        subprocess.run([sys.executable, '-B', '-X', 'utf8',
                                        str(ROOT / 'scripts/check_fipi_render.py'), '--out', str(self.out),
                                        '--start', str(pages[0]), '--end', str(pages[-1])], check=True)
                batch_records = []
        return self.export(all_records, total, summaries)

    def export(self, records, total, checks):
        (self.out / 'tasks.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        summary = self.audit(records, sorted({r['page'] for r in records}), total)
        summary['complete_by_count'] = len(records) == total
        summary['batches'] = len(checks)
        dump(self.out / 'summary.json', summary)
        items = ''.join(f'<li><a href="tasks/{r["id"]}.html">{r["id"]}</a> · стр. {r["page"]}'
                        f' · формул {r["mathml_count"]} · изображений {len(r["assets"])}'
                        + (' · ⚠ дефект исходника' if r.get('source_issues') else '') + '</li>' for r in records)
        (self.out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Банк ФИПИ</title>'
                                           f'<h1>ФИПИ · профильная математика · {len(records)}/{total}</h1>'
                                           '<p>Технический сбор; решения и ответы не получены.</p><ul>' + items + '</ul>', encoding='utf-8')
        return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=DEFAULT)
    p.add_argument('--interface', default='192.168.1.2')
    p.add_argument('--server-ip', default='80.250.169.3')
    p.add_argument('--stop-page', type=int, default=1)
    p.add_argument('--batch-pages', type=int, default=5)
    p.add_argument('--delay', type=float, default=1.0)
    p.add_argument('--audit', action='store_true')
    p.add_argument('--render-check', action='store_true', help='Browser health gate before the next batch')
    args = p.parse_args()
    c = Collector(args)
    if args.audit:
        records = [json.loads(line) for line in (c.out / 'tasks.jsonl').read_text(encoding='utf-8').splitlines()]
        total = json.loads((c.out / 'summary.json').read_text(encoding='utf-8'))['declared_total']
        print(json.dumps(c.audit(records, sorted({r['page'] for r in records}), total), ensure_ascii=False))
    else:
        print(json.dumps(c.run(), ensure_ascii=False))


if __name__ == '__main__':
    main()
