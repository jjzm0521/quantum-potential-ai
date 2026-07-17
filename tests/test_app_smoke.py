from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_with_empty_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("QPOT_WORKSPACE_DIR", str(tmp_path / "workspace"))
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
