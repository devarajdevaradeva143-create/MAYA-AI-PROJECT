"""Embedding wrapper tests — no model download, no network."""


from custom import config
from custom.tools import embeddings


def test_default_model_name(monkeypatch):
    monkeypatch.delenv("MAYA_EMBED_MODEL", raising=False)
    monkeypatch.setattr(config, "load_settings", lambda: {})
    assert embeddings.model_name() == embeddings.DEFAULT_MODEL_NAME


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("MAYA_EMBED_MODEL", "someone/other-model")
    assert embeddings.model_name() == "someone/other-model"


def test_settings_override(monkeypatch):
    monkeypatch.delenv("MAYA_EMBED_MODEL", raising=False)
    monkeypatch.setattr(
        config, "load_settings", lambda: {"knowledge": {"embedding_model": "x/y"}}
    )
    assert embeddings.model_name() == "x/y"


def test_broken_settings_fall_back_to_default(monkeypatch):
    monkeypatch.delenv("MAYA_EMBED_MODEL", raising=False)

    def boom():
        raise RuntimeError("bad yaml")

    monkeypatch.setattr(config, "load_settings", boom)
    assert embeddings.model_name() == embeddings.DEFAULT_MODEL_NAME


def test_unknown_model_is_not_cached():
    assert embeddings.model_cached("nobody/definitely-not-downloaded") is False


def test_available_never_downloads(monkeypatch):
    monkeypatch.setenv("MAYA_EMBED_MODEL", "nobody/definitely-not-downloaded")
    report = embeddings.available()
    assert report["model_cached"] is False
    assert report["package"] is True
    assert report["hf_home"].endswith("Model\\hf") or report["hf_home"].endswith("Model/hf")


def test_embed_returns_empty_without_model(monkeypatch):
    monkeypatch.setattr(embeddings, "get_model", lambda name=None: None)
    assert embeddings.embed(["hello"]) == []


def test_load_embedder_returns_none_when_missing(monkeypatch):
    monkeypatch.setenv("MAYA_EMBED_MODEL", "nobody/definitely-not-downloaded")
    assert embeddings.load_embedder() is None


def test_embedder_name(monkeypatch):
    monkeypatch.setenv("MAYA_EMBED_MODEL", "someone/other-model")
    assert embeddings.Model2VecEmbedder().name == "model2vec:someone/other-model"


def test_hf_home_defaults_inside_project(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    assert embeddings.hf_home() == embeddings.DEFAULT_HF_HOME
    assert "MAYA AI" in str(embeddings.hf_home())


def test_model_dim_reads_cached_config(tmp_path, monkeypatch):
    snapshot = tmp_path / "hub" / "models--fake--model" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text(
        '{"model_type": "model2vec", "hidden_dim": 256}', encoding="utf-8"
    )
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert embeddings.model_dim("fake/model") == 256


def test_model_dim_default_when_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert embeddings.model_dim("nobody/none") == embeddings.DEFAULT_MODEL_DIM
