from pathlib import Path

import pytest
import yaml

from app.playbook import PLAYBOOK_PATH, PlaybookError, load_playbook, playbook_hash
from evals.cuad import TARGET_LABELS

CLAUSE_IDS = [
    "governing_law",
    "termination_for_convenience",
    "cap_on_liability",
    "non_compete",
    "anti_assignment",
]


def write_playbook(tmp_path: Path, mutate) -> Path:
    data = yaml.safe_load(PLAYBOOK_PATH.read_text())
    mutate(data)
    path = tmp_path / "playbook.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_real_playbook_loads():
    playbook = load_playbook()
    assert [c.id for c in playbook.clauses] == CLAUSE_IDS
    assert playbook.clause("non_compete").absence_is == "ok"


def test_unknown_clause_id_raises_key_error():
    with pytest.raises(KeyError):
        load_playbook().clause("nope")


def test_unknown_key_rejected(tmp_path):
    path = write_playbook(tmp_path, lambda d: d["clauses"][0].update(notes="x"))
    with pytest.raises(PlaybookError, match="playbook.yaml"):
        load_playbook(path)


def test_missing_key_rejected(tmp_path):
    path = write_playbook(tmp_path, lambda d: d["clauses"][0].pop("absence_is"))
    with pytest.raises(PlaybookError):
        load_playbook(path)


def test_bad_severity_rejected(tmp_path):
    path = write_playbook(
        tmp_path, lambda d: d["clauses"][0].update(severity_if_missing="critical")
    )
    with pytest.raises(PlaybookError):
        load_playbook(path)


def test_duplicate_ids_rejected(tmp_path):
    path = write_playbook(
        tmp_path, lambda d: d["clauses"][1].update(id=d["clauses"][0]["id"])
    )
    with pytest.raises(PlaybookError):
        load_playbook(path)


def test_more_than_five_clauses_rejected(tmp_path):
    def add_sixth(d):
        extra = dict(d["clauses"][0], id="sixth")
        d["clauses"].append(extra)

    with pytest.raises(PlaybookError):
        load_playbook(write_playbook(tmp_path, add_sixth))


def test_empty_query_terms_rejected(tmp_path):
    path = write_playbook(tmp_path, lambda d: d["clauses"][0].update(query_terms=[]))
    with pytest.raises(PlaybookError):
        load_playbook(path)


def test_hash_changes_with_content(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("version: 1\n")
    b.write_text("version: 2\n")
    assert len(playbook_hash(a)) == 12
    assert playbook_hash(a) != playbook_hash(b)
    assert playbook_hash(a) == playbook_hash(a)


def test_playbook_labels_exist_in_cuad():
    assert {c.cuad_label for c in load_playbook().clauses} == set(TARGET_LABELS)
