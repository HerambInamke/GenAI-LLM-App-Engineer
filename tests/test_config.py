import shutil

import pytest
import yaml
from pydantic import ValidationError

from deadair.config import CONFIG_DIR, load_config


def test_repo_config_loads():
    cfg = load_config()
    assert {s.id for s in cfg.stations} == {"deadair", "rival"}
    assert all(len(s.hosts) >= 2 for s in cfg.stations)
    assert cfg.feeds.poll_minutes == 5 and cfg.feeds.max_age_hours == 48


@pytest.fixture
def cfg_dir(tmp_path):
    shutil.copytree(CONFIG_DIR, tmp_path / "config")
    return tmp_path / "config"


def _edit(path, **changes):
    data = yaml.safe_load(path.read_text())
    data.update(changes)
    path.write_text(yaml.safe_dump(data))


def test_too_many_catchphrases_rejected(cfg_dir):
    _edit(cfg_dir / "personas" / "max.yaml", catchphrases=["a", "b", "c", "d"])
    with pytest.raises(ValidationError, match="catchphrases"):
        load_config(cfg_dir)


def test_unknown_persona_rejected(cfg_dir):
    (cfg_dir / "personas" / "juniper.yaml").unlink()
    with pytest.raises(ValidationError, match="unknown personas"):
        load_config(cfg_dir)


def test_load_dotenv(tmp_path, monkeypatch):
    from deadair.config import load_dotenv

    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "DA_KEY=sk-123        # inline comment\n"
        "DA_EMPTY=            # nothing set\n"
        'DA_QUOTED="pa ss #word"\n'
        "export DA_EXPORTED=yes\n"
        "DA_KEEP=from-file\n"
    )
    for k in ("DA_KEY", "DA_EMPTY", "DA_QUOTED", "DA_EXPORTED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DA_KEEP", "from-env")
    assert load_dotenv(env) == 3
    import os

    assert os.environ["DA_KEY"] == "sk-123" and os.environ["DA_QUOTED"] == "pa ss #word"
    assert os.environ["DA_EXPORTED"] == "yes" and "DA_EMPTY" not in os.environ
    assert os.environ["DA_KEEP"] == "from-env"  # real env vars always win
    assert load_dotenv(tmp_path / "missing.env") == 0
