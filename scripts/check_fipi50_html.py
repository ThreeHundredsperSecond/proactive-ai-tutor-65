"""Render three local pilot cards and check actual browser image/MathML loading."""
import json
import os
import subprocess
from pathlib import Path
from lxml import html
from PIL import Image
from fipi_eda50 import RUN,read,write


def main():
    checked=[]
    qa_script='''<script>addEventListener('load',()=>document.body.setAttribute('data-check',JSON.stringify({images:[...document.images].map(i=>i.complete&&i.naturalWidth>0),math:document.querySelectorAll('math').length,mfenced:document.querySelectorAll('mfenced').length,width:document.body.scrollWidth})))</script>'''
    for tid in ['7D21DC','3E3293','eFF32e']:
        card=RUN/'derived/cards'/f'{tid}.html';qa=card.with_name(tid+'.qa.html')
        qa.write_text(card.read_text(encoding='utf-8')+qa_script,encoding='utf-8')
        image=RUN/'checks'/f'card-{tid}.png'
        r=subprocess.run(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless','--disable-gpu','--no-first-run',
                          '--user-data-dir='+str(Path(os.environ['TEMP'])/'fipi50-html-review'),
                          '--window-size=1600,3000','--virtual-time-budget=1000','--dump-dom',
                          '--screenshot='+str(image),qa.as_uri()],capture_output=True,timeout=35)
        assert r.returncode==0 and image.exists()
        tree=html.fromstring(r.stdout.decode('utf-8'))
        result=json.loads(tree.xpath('//body/@data-check')[0]);inp=read(RUN/'inputs/tasks'/f'{tid}.json')
        assert result['math']==inp['mathml_count'] and result['mfenced']==0
        assert len(result['images'])==len(inp['assets']) and all(result['images'])
        assert result['width']<=1600,(tid,result)
        with Image.open(image) as im:im.crop((0,0,1600,1250)).save(RUN/'checks'/f'card-{tid}-top.png')
        checked.append(dict(task_id=tid,browser=result,screenshot=image.relative_to(RUN).as_posix()))
        qa.unlink()
    write(RUN/'checks/html-render.json',dict(status='passed',cards=checked))
    print(checked)


if __name__=='__main__':main()
