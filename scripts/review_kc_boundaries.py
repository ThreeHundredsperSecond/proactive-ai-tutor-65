"""Rebuild review cards from frozen responses and explicit editorial decisions.

No model calls, semantic inference, catalogue edits or metric recalculation.
Run from repository root: python scripts/review_kc_boundaries.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/annotation/reviews/2026-10-26-kc-boundaries"
OUTPUT = ROOT / "docs/eda/04-annotation/05-kc-boundary-review.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def link(path: Path) -> str:
    return Path(os.path.relpath(path, OUTPUT.parent)).as_posix()


def main() -> None:
    decisions_path = REVIEW / "decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    run = ROOT / decisions["run"]
    ledger_path = run / "responses.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen_tasks = {t["task_id"]: t for t in manifest["tasks"]}
    tasks = decisions["tasks"]
    if [t["position"] for t in tasks] != list(range(1, 20)):
        raise ValueError("Expected exactly positions 1..19, in order")
    with (run / "derived/stability_summary.csv").open(encoding="utf-8", newline="") as f:
        stability = {int(row["position"]): row for row in csv.DictReader(f)}
    sources = {decisions_path, ledger_path, manifest_path,
               run / "derived/stability_summary.csv", Path(__file__)}
    lines = [
        "# Просмотр границ KC: 19 задач и пять карточек",
        "",
        "26 октября 2026. **Предложения для обсуждения, не согласованные правила.**",
        "",
        "Сопоставлены все 57 сохранённых решений. Ни исходные ответы, ни каталог из 155 кандидатов, ни прежние метрики не изменены. Новых генераций не было. Это интерпретация основного агента, не независимая предметная экспертиза.",
        "",
        "Цель — различить переименование, границы составных KC и содержательные варианты решения. Отсутствие отдельного KC не доказывает отсутствия действия: нужно читать шаги. Средний Жаккар ниже взят из прежнего каталога; это не оценка правильности решения.",
        "",
        "## Пять показательных карточек",
        "",
    ]
    inventory = []
    card_count = 0
    for task in tasks:
        position = task["position"]
        tid = str(699084 + position)
        if stability[position]["task_id"] != tid:
            raise ValueError("Position/task ID mismatch")
        input_path = run / "inputs" / f"{tid}.json"
        condition = json.loads(input_path.read_text(encoding="utf-8"))
        if digest(input_path) != frozen_tasks[tid]["input_sha256"]:
            raise ValueError(f"Frozen input changed: {tid}")
        sources.add(input_path)
        responses = []
        for repeat in (1, 2, 3):
            raw = run / "raw" / f"{tid}_r{repeat}.txt"
            if digest(raw) != ledger[f"{tid}_r{repeat}"]["raw_sha256"]:
                raise ValueError(f"Captured response changed: {raw.name}")
            response = json.loads(raw.read_text(encoding="utf-8"))
            if response["task_id"] != tid:
                raise ValueError("Raw task ID mismatch")
            responses.append((raw, response))
            sources.add(raw)
        counts = "/".join(str(len(d["kc_candidates"])) for _, d in responses)
        mean = float(stability[position]["mean_jaccard"])
        inventory += [
            f"### №{position} · {tid}", "",
            f"Типы различий: {', '.join(task['types'])}. KC r1/r2/r3: **{counts}**. Средний Жаккар: **{mean:.3f}**.", "",
            task["observation"], "",
            f"**Предложение:** {task['proposal']}", "",
            "<details><summary>Точные названия KC и методов трёх повторов</summary>", "",
        ]
        for repeat, (raw, d) in enumerate(responses, 1):
            inventory += [f"**[r{repeat}]({link(raw)})**", ""]
            inventory += [f"- `{k['id']}`: {k['name']}" for k in d["kc_candidates"]]
            inventory += ["", "Методы: " + "; ".join(m["name"] for m in d["methods"]) + ".", ""]
        inventory += ["</details>", ""]
        card = task.get("card")
        if card is None:
            continue
        card_count += 1
        lines += [f"### Карточка {card_count}. №{position}: {card['title']}", "",
                  f"Задача `{tid}` · [сохранённый вход]({link(input_path)}) · KC r1/r2/r3: **{counts}** · прежний средний Жаккар: **{mean:.3f}**.", "",
                  "Условие: доступный текст ниже может содержать машинные названия символов; точные формулы и рисунки сохранены в изображениях.", "",
                  "```text", condition["statement"], "```", ""]
        for img in condition["images"]:
            path = run / img["path"]
            if not path.is_file():
                raise FileNotFoundError(path)
            frozen_img = next(i for i in frozen_tasks[tid]["images"] if i["path"] == img["path"])
            if digest(path) != frozen_img["png_sha256"]:
                raise ValueError(f"Frozen image changed: {path.name}")
            sources.add(path)
            lines += [f"![Условие №{position}: {path.name}]({link(path)})", ""]
        lines += ["**Точные фрагменты KC** (локальные ID действуют только внутри своего ответа):", ""]
        for repeat, ((raw, d), focus) in enumerate(zip(responses, card["focus"], strict=True), 1):
            by_id = {k["id"]: k for k in d["kc_candidates"]}
            lines += [f"**[r{repeat}: полный ответ и шаги]({link(raw)})**", ""]
            for kid in focus:
                k = by_id[kid]
                lines += [f"- `{kid}` **{k['name']}**. {k['description']}"]
            lines += [""]
        lines += [f"**Сопоставление действий:** {task['observation']}", "",
                  card["explanation"], "", f"**Предложение:** {task['proposal']}", "",
                  f"**Для обсуждения:** {card['question']}", ""]
    lines += ["## Предлагаемые правила", ""]
    lines += [f"{i}. {rule}" for i, rule in enumerate(decisions["rules"], 1)]
    lines += ["", "Правила ещё не применены к каталогу. После их согласования нужна отдельная версия соответствий с возможностью связать исходный составной KC с несколькими операциями. Текущее сопоставление один-к-одному для этого недостаточно. Новые метрики можно считать только после явной фиксации этих решений; рост сходства сам по себе не подтверждает улучшение предметной модели.", "",
              "## Обзор всех 19 задач", ""]
    lines += inventory
    lines += ["## Воспроизведение и границы результата", "",
              f"Редакторские интерпретации находятся в [decisions.json]({link(decisions_path)}). Код лишь извлекает точные формулировки, входы и прежние показатели: он не принимает смысловые решения.", "",
              "Из корня репозитория:", "", "```powershell",
              ".\\.venv\\Scripts\\python.exe -X utf8 scripts/review_kc_boundaries.py", "```", "",
              f"[Манифест происхождения]({link(REVIEW / 'provenance.json')}) фиксирует SHA-256 входов, кода и этого документа. Повторный запуск воспроизводит документ из сохранённых данных без сети и модели.", "",
              "Пять карточек выбраны основным агентом для иллюстрации разных случаев, а не как случайная выборка. Обзор охватывает 19 задач, но не задаёт исчерпывающую экспертную классификацию всех различий. Полезность детализации для диагностики ученика пока не проверена.", "",
              "**Место остановки:** карточки и предложения подготовлены. Следующее действие — обсудить границы KC на этих примерах, затем подготовить версию каталога и сравнение метрик до/после. Новые генерации для этого шага не нужны.", ""]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    provenance = {
        "status": decisions["status"],
        "source_run": decisions["run"],
        "reviewer": decisions["reviewer"],
        "responses_read": len(tasks) * 3,
        "cards": card_count,
        "inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(sources)},
        "output": {OUTPUT.relative_to(ROOT).as_posix(): digest(OUTPUT)},
    }
    (REVIEW / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Built {OUTPUT.relative_to(ROOT)}: {len(tasks)} tasks, {card_count} cards")


if __name__ == "__main__":
    main()
