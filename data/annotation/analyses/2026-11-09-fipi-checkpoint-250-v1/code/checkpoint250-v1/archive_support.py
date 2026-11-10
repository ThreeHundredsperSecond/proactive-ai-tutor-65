"""Resolve archived snapshot paths without changing historical manifests.

The active checkpoint uses collect_saved() to adapt the legacy collector's
frozen-file check. No global pathlib patching or historical source edits.
"""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'docs/archive-paths.json'


def resolve_path(path):
    path=Path(path).resolve()
    if path.exists():return path
    if not path.is_relative_to(ROOT):return path
    logical=path.relative_to(ROOT).as_posix()
    mapping=json.loads(MAP.read_text(encoding='utf-8'))
    entry=next((e for e in mapping['files'] if e['old']==logical),None)
    if entry is None:return path
    target=(ROOT/entry['new']).resolve()
    if not target.is_relative_to(ROOT/'research/archive'):raise ValueError('Archive target escapes archive')
    actual=hashlib.sha256(target.read_bytes()).hexdigest()
    if actual!=entry['sha256']:raise ValueError(f'Archived bytes changed: {logical}')
    return target


def verify_snapshot(manifest):
    for item in manifest['files']:
        path=resolve_path(ROOT/item['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],item['path']


def collect_saved(report,*args,**kwargs):
    original=report.ext.verify_frozen
    def check():
        for name in ['baseline-manifest.json','freeze-manifest.json']:
            verify_snapshot(json.loads((report.RUN/name).read_text(encoding='utf-8')))
        print('Frozen bytes verified, including archived paths.')
    report.ext.verify_frozen=check
    try:return report.collect(*args,**kwargs)
    finally:report.ext.verify_frozen=original
