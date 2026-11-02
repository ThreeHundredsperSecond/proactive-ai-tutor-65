"""Render a stratified sample for one collection batch, checking local images/MathML."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from lxml import html
from PIL import Image, ImageDraw

from collect_fipi_bank import DEFAULT, dump, now, browser_math

QA = '''<script>addEventListener('load',()=>{
const images=[...document.images].map(i=>({src:i.getAttribute('src'),ok:i.complete&&i.naturalWidth>0,width:i.naturalWidth,height:i.naturalHeight}));
const maths=[...document.querySelectorAll('math')];
document.body.setAttribute('data-health',JSON.stringify({images,maths:maths.length,legacy_mfenced:document.querySelectorAll('mfenced').length,maths_ok:maths.every(m=>m.namespaceURI==='http://www.w3.org/1998/Math/MathML'&&m.getBoundingClientRect().height>0),height:document.body.scrollHeight,width:document.body.scrollWidth}));
});</script>'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=DEFAULT)
    p.add_argument('--start', type=int, required=True)
    p.add_argument('--end', type=int, required=True)
    p.add_argument('--ids', nargs='+', help='Explicit additional regression cases')
    args = p.parse_args()
    out = args.out.resolve()
    rs = [json.loads(f.read_text(encoding='utf-8')) for f in (out/'tasks').glob('*.json')]
    rs = sorted([r for r in rs if args.start <= r['page'] <= args.end or r['id'] in (args.ids or [])], key=lambda r:(r['page'],r['id']))
    chosen = []
    for predicate in [lambda r: r['id'] in (args.ids or []), lambda r: bool(r.get('source_issues')), lambda r: bool(r['assets']),
                      lambda r: len(r['assets']) > 1, lambda r:r['mathml_count']>0,
                      lambda r:'<mfenced' in r['statement_html'],
                      lambda r:'развернутый' in r['instruction'] or 'развёрнутый' in r['instruction']]:
        r = next((r for r in rs if predicate(r) and r not in chosen), None)
        if r:
            chosen.append(r)
    if rs[-1] not in chosen:
        chosen.append(rs[-1])
    checks = []
    for r in chosen:
        card = out/'tasks'/f'{r["id"]}.html'
        qa = out/'tasks'/f'{r["id"]}.qa.html'
        normalized = '<!doctype html>' + browser_math(card.read_text(encoding='utf-8'))
        card.write_text(normalized, encoding='utf-8')
        qa.write_text(normalized+QA, encoding='utf-8')
        image = out/'checks'/f'{r["id"]}.png'
        proc = subprocess.run(['C:/Program Files/Google/Chrome/Application/chrome.exe',
                               '--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
                               '--user-data-dir='+str(Path(os.environ['TEMP'])/f'fipi-render-{args.start}-{args.end}'),
                               '--window-size=1200,2000','--virtual-time-budget=1000','--dump-dom',
                               '--screenshot='+str(image),qa.as_uri()],capture_output=True,timeout=40)
        assert proc.returncode == 0 and image.exists(), proc.stderr.decode(errors='replace')
        tree = html.fromstring(proc.stdout.decode('utf-8'))
        health = json.loads(tree.xpath('//body/@data-health')[0])
        assert health['maths'] == r['mathml_count'] and health['maths_ok'] and health['legacy_mfenced'] == 0, (r['id'],health)
        assert len(health['images']) == len(r['assets']) and all(i['ok'] for i in health['images']), (r['id'],health)
        assert health['width'] <= 1200, (r['id'],'horizontal overflow',health)
        checks.append(dict(id=r['id'],page=r['page'],screenshot=image.relative_to(out).as_posix(),browser_health=health))
        qa.unlink()  # Only our temporary QA wrapper, never a source/card/image.
    montage = Image.new('RGB',(1200,800*((len(checks)+1)//2)),'#ddd')
    draw = ImageDraw.Draw(montage)
    for n, c in enumerate(checks):
        with Image.open(out/c['screenshot']) as im:
            # All screenshots remain full-size on disk; contact sheet crops only whitespace.
            height=min(2000,max(350,c['browser_health']['height']+80))
            preview=im.crop((0,0,1200,height))
            preview.thumbnail((580,750))
            left, top = (n%2)*600+10, (n//2)*800
            montage.paste(preview,(left,top+35))
            draw.text((left,top+10),f'{c["id"]} / page {c["page"]}',fill='black')
    dest=out/'checks'/f'visual-{args.start:03}-{args.end:03}.jpg'
    montage.save(dest,quality=85)
    result=dict(checked_at=now(),renderer_version=2,pages=[args.start,args.end],status='passed',samples=checks,
                contact_sheet=dest.relative_to(out).as_posix(),review='browser checks; visual inspection recorded separately')
    dump(out/'checks'/f'render-{args.start:03}-{args.end:03}.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
