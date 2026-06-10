import json

from storage import load_data, save_data


def test_load_data_creates_file_from_seed_when_missing(tmp_path):
    seed_file = tmp_path / "seed.json"
    data_file = tmp_path / "data.json"
    seed_content = [{"id": "1", "name": "Pizza Margherita"}]
    seed_file.write_text(json.dumps(seed_content), encoding="utf-8")

    result = load_data(str(data_file), str(seed_file))

    assert result == seed_content
    assert data_file.exists()
    assert json.loads(data_file.read_text(encoding="utf-8")) == seed_content


def test_load_data_returns_empty_list_without_seed(tmp_path):
    data_file = tmp_path / "data.json"

    result = load_data(str(data_file))

    assert result == []
    assert data_file.exists()


def test_load_data_reads_existing_file_without_touching_seed(tmp_path):
    seed_file = tmp_path / "seed.json"
    data_file = tmp_path / "data.json"
    seed_file.write_text(json.dumps([{"id": "seed"}]), encoding="utf-8")
    data_file.write_text(json.dumps([{"id": "existing"}]), encoding="utf-8")

    result = load_data(str(data_file), str(seed_file))

    assert result == [{"id": "existing"}]


def test_save_data_writes_json(tmp_path):
    data_file = tmp_path / "nested" / "data.json"

    save_data(str(data_file), [{"id": "1", "name": "Pizza Calabresa"}])

    assert json.loads(data_file.read_text(encoding="utf-8")) == [
        {"id": "1", "name": "Pizza Calabresa"}
    ]
