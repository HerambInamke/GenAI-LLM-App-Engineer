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
