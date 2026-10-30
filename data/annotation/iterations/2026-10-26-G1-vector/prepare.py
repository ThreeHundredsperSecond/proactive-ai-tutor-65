"""Freeze the single G1 annotation trial. No model calls.

Run from the repository root; existing frozen inputs must match exactly.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "data/annotation/runs/2026-10-25-A-19x3/raw/699086_r1.txt"
A = ROOT / "docs/eda/04-annotation/02.1-prompting-pilot/prompts/A.txt"


def save(name, value):
    path = HERE / name
    data = value.encode("utf-8")
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"Refusing to change frozen file: {path}")
    path.write_bytes(data)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


original = json.loads(SOURCE.read_text(encoding="utf-8"))
payload = {"task_id": original["task_id"], "solution_status": original["solution_status"],
           "steps": [{key: step[key] for key in ("id", "action", "result")}
                     for step in original["steps"]]}
save("input.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
text = A.read_text(encoding="utf-8")
body = text[text.index("Общие определения и детализация:"):text.index("Итоговая структура")]
schema = text[text.index("Итоговая структура"):text.index("В одном ответе")]
base = (
    "Ты размечаешь сохранённое математическое решение для предметной модели тьютора. "
    "Не решай задачу заново. Во входе дано готовое решение без прежних KC и методов. "
    "Не обращайся к источникам, другим ответам и инструментам. Верни только JSON.\n\n"
    + body + "\n" + schema
    + "\nРежим фиксированного решения: сохрани task_id, solution_status и все steps.id/action/result "
    "буквально, в исходном порядке. Не добавляй и не удаляй шаги. Добавь к ним kc_ids, "
    "выдели kc_candidates и methods. Инструкции Step выше относятся к интерпретации уже данных шагов; "
    "изменять или дополнять математическое решение здесь нельзя. Сомнения вынеси в warnings.\n"
)
delta = (
    "\nПравка G1 — границы операций:\n"
    "Один данный Step может содержать несколько KC. Если в нём явно выполнены операции "
    "с разными входами и результатами, назови эти операции отдельными KC и свяжи их "
    "с этим же Step; не сворачивай цепочку операций в один KC. В description каждого KC "
    "обозначь вход, выполняемое действие, результат и существенные условия применения. "
    "Повторное применение одной операции к нескольким объектам не создаёт новые KC. "
    "Элементарные арифметические вычисления внутри одной операции отдельно не выделяй. "
    "Не добавляй действий, которые лишь могли бы понадобиться, но отсутствуют в решении.\n"
)
save("baseline-adapted-A.txt", base)
save("delta-G1.txt", delta)
save("candidate-v1.txt", base + delta)
save("request.txt", base + delta + "\nСОХРАНЁННОЕ РЕШЕНИЕ:\n" + (HERE / "input.json").read_text(encoding="utf-8"))
save("job.txt", "Прочитай только request.txt в этой папке. Техническое чтение и сохранение разрешены. "
     "После чтения не используй инструменты для математического рассуждения, поиска или проверки. "
     "Выполни запрос и сохрани полный итоговый JSON без Markdown в raw.txt в этой папке. "
     "Не читай другие материалы, исходный эксперимент, ожидаемые критерии или README. "
     "После сохранения верни только путь raw.txt.\n")
files = ["input.json", "baseline-adapted-A.txt", "delta-G1.txt", "candidate-v1.txt", "request.txt", "job.txt"]
manifest = {
    "trial": "2026-10-26-G1-vector", "expected_responses": 1,
    "mode": "annotation_of_fixed_solution", "source_response": SOURCE.relative_to(ROOT).as_posix(),
    "source_sha256": sha(SOURCE), "original_prompt": A.relative_to(ROOT).as_posix(),
    "original_prompt_sha256": sha(A), "prepare_script_sha256": sha(Path(__file__)),
    "protocol": "docs/eda/04-annotation/07-prompt-local-iteration.md",
    "protocol_sha256": sha(ROOT / "docs/eda/04-annotation/07-prompt-local-iteration.md"),
    "model_parameters": None, "runtime": "one isolated agent, fork_turns=none, no model override",
    "files": {name: sha(HERE / name) for name in files},
    "baseline_generated": False, "review": "primary agent, nonblind, not expert validation",
}
save("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print("Frozen single-response trial:", HERE)
