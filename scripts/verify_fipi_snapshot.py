"""Independent local integrity audit; optional fresh spot checks of the bank."""
import argparse
import json
from pathlib import Path

from lxml import html

from collect_fipi_bank import Collector, DEFAULT, BASE, PROJECT, QPATH, dump, now, sha


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=DEFAULT)
    p.add_argument('--live',action='store_true')
    p.add_argument('--interface',default='192.168.1.2')
    p.add_argument('--server-ip',default='80.250.169.3')
    args=p.parse_args()
    args.delay=0.5
    c=Collector(args)
    records=[json.loads(line) for line in (c.out/'tasks.jsonl').read_text(encoding='utf-8').splitlines()]
    summary=json.loads((c.out/'summary.json').read_text(encoding='utf-8'))
    total=summary['declared_total']
    assert len(records)==total
    assert len({r['id'].upper() for r in records})==total
    for r in records:
        assert json.loads((c.out/'tasks'/f'{r["id"]}.json').read_text(encoding='utf-8'))==r
        card=html.fromstring((c.out/'tasks'/f'{r["id"]}.html').read_text(encoding='utf-8'))
        assert not card.xpath('//mfenced'),r['id']
        assert len(card.xpath('//math'))==r['mathml_count'],r['id']
        assert len(card.xpath('//img'))==len(r['assets']),r['id']
        for a in card.xpath('//img/@src'):
            assert (c.out/'tasks'/a).resolve().is_file(),(r['id'],a)
    audit=c.audit(records,sorted({r['page'] for r in records}),total)
    audit.update(individual_json_matches=True,
                 cards_have_local_assets=True,cards_have_no_legacy_mfenced=True)
    live=[]
    if args.live:
        stamp=now().replace(':','').replace('-','').replace('.','')
        for page in [1,30,60,90,115]:
            # A live check must not silently reuse an earlier network response.
            path=c.out/'checks'/'live'/stamp/f'page-{page:03}.html'
            data=c.fetch(BASE+f'questions.php?proj={PROJECT}&page={page-1}&pagesize=10',path)
            tree=html.fromstring(data.decode('cp1251'))
            old=html.fromstring((c.out/f'raw/page-{page:03}.html').read_bytes().decode('cp1251'))
            def statements(t):
                return {q.get('id'): '\n'.join(html.tostring(cell,encoding='unicode')
                        for cell in q.xpath('.//td[starts-with(@class,"cell_")]')) for q in t.xpath(QPATH)}
            assert statements(tree)==statements(old),('Live content changed',page)
            live.append(dict(page=page,raw_path=path.relative_to(c.out).as_posix(),
                             ids=[q.get('id')[1:] for q in tree.xpath(QPATH)],statement_match=True))
    checked=0
    for line in (c.out/'downloads.jsonl').read_text(encoding='utf-8').splitlines():
        d=json.loads(line)
        data=(c.out/d['path']).read_bytes()
        assert sha(data)==d['sha256'] and len(data)==d['bytes'],d['path']
        checked+=1
    audit['download_manifest_entries_checked']=checked
    audit['live_spot_checks']=live
    dump(c.out/'checks/final-audit.json',audit)
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':
    main()
