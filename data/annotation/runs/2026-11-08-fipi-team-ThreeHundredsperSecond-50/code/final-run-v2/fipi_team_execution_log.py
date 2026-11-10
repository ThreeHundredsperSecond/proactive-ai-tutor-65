"""Record actual root-dispatched isolated agent calls; never invokes a model."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/annotation/runs/2026-11-08-fipi-team-ThreeHundredsperSecond-50'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('event', choices=['launch', 'complete'])
    p.add_argument('role', choices=['author', 'auditor'])
    p.add_argument('task_id')
    p.add_argument('--agent', required=True)
    args = p.parse_args()
    now = datetime.now(timezone.utc).isoformat()
    dest = RUN / 'executions' / f'{args.role}-{args.task_id}.json'
    request = RUN / 'requests' / args.role / f'{args.task_id}.txt'
    if args.event == 'launch':
        assert not dest.exists(), 'Launch already recorded'
        obj = dict(task_id=args.task_id, role=args.role, agent_task_name=args.agent,
                   mechanism='collaboration.spawn_agent', fork_turns='none',
                   requested_model='gpt-6.1-sol', actual_model='not exposed by tool result',
                   launched_at_utc=now, launch_timestamp_precision='recorded immediately after spawn',
                   request_path=request.relative_to(ROOT).as_posix(), request_sha256=digest(request),
                   input_policy='Only request and its listed images; no other tasks, catalog for author, previous mappings or network',
                   status='running')
    else:
        obj = json.loads(dest.read_text(encoding='utf-8'))
        assert obj['agent_task_name'] == args.agent
        assert digest(request) == obj['request_sha256']
        raw = RUN / 'raw' / args.role / f'{args.task_id}.json'
        obj.update(completed_at_utc=now, raw_path=raw.relative_to(ROOT).as_posix(),
                   raw_sha256=digest(raw), status='completed')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
