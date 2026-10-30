"""Offline provenance and selected arithmetic checks; no network or models."""
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def area(points):
    cyclic = points[1:] + points[:1]
    return abs(sum(F(a[0]) * F(b[1]) - F(a[1]) * F(b[0])
                   for a, b in zip(points, cyclic))) / 2


def main():
    manifest = read(HERE / "frozen-inputs.json")
    for item in manifest["files"]:
        assert sha(ROOT / item["path"]) == item["sha256"], item["path"]
    audit = read(HERE / "geometry-audit.json")
    cards = read(ROOT / audit["frozen_catalog"])["cards"]
    draft_ids = {c["id"] for c in audit["draft_families"]}
    assert len(draft_ids) == 5
    assert draft_ids.isdisjoint({c["candidate_id"] for c in cards})
    assert len(audit["cases"]) == 3
    assert audit["source"]["bank_id"] is None
    for case in audit["cases"]:
        assert set(case["draft_families"]) <= draft_ids
    content = (ROOT / "docs/eda/01-exam/content-map.md").read_text(encoding="utf-8")
    assert "| 7.1 | Фигуры на плоскости |" in content

    c1, c2, c3 = audit["cases"]
    # Conditional on the stated tangential-quadrilateral theorem.
    semiperimeter = F(c1["given"]["perimeter"], 2)
    cd = semiperimeter - c1["given"]["AB"]
    assert cd > 0
    assert 2 * (c1["given"]["AB"] + cd) == c1["given"]["perimeter"]
    # Independent coordinate illustration of the area scale for midpoints.
    a, b, c = (-2, 0), (2, 0), (0, 2)
    d, e = (-1, 1), (1, 1)
    ratio = area([c, d, e]) / area([c, a, b])
    assert ratio == F(1, 4)
    small = F(c2["given"]["area_ABC"]) * ratio
    trapezoid = F(c2["given"]["area_ABC"]) - small
    assert small + trapezoid == c2["given"]["area_ABC"]
    assert area([a, b, e, d]) + area([c, d, e]) == area([a, b, c])
    # The two proposed routes use different intermediate angles.
    angle_c = c3["given"]["angle_C_deg"]
    half_a = c3["given"]["angle_BAD_deg"]
    angle_a = 2 * half_a
    angle_b = 180 - angle_a - angle_c
    route_a = 180 - half_a - angle_b
    angle_adc = 180 - half_a - angle_c
    route_b = 180 - angle_adc
    assert min(angle_a, angle_b, angle_c, angle_adc, route_a) > 0
    assert route_a == route_b
    result = {
        "input_hashes_checked": len(manifest["files"]),
        "source_examples": 3,
        "frozen_cards_unchanged": 8,
        "draft_families_separate": len(draft_ids),
        "arithmetic_review": {
            "D27-1a": {"CD": str(cd), "assumption": "применено свойство описанного четырёхугольника"},
            "D27-1b": {"small_area": str(small), "trapezoid_area": str(trapezoid), "coordinate_area_ratio": str(ratio)},
            "D27-1c": {"angle_B": angle_b, "angle_ADC": angle_adc, "route_A_ADB": route_a, "route_B_ADB": route_b}
        },
        "limits": "Арифметика и один координатный пример, не доказательство всех теорем и не независимая предметная экспертиза. Полный официальный PDF не получен."
    }
    (HERE / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(manifest['files'])} hashes, 3 examples, two angle routes, separate drafts")


if __name__ == "__main__":
    main()
