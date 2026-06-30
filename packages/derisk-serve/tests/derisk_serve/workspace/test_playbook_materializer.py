"""Tests for playbook declaration materializer."""
import pytest
from unittest.mock import MagicMock, patch


def test_materialize_playbook_declaration_handles_skills_and_resources():
    from derisk_serve.workspace.materializer import materialize_playbook_declaration

    declaration = {
        "skills": [{"name": "skill-a", "type": "skill"}],
        "context": {"resources": [{"type": "mcp", "name": "mcp-x", "server_name": "s1"}]},
        "deliverables": [],
    }
    fake_system_app = MagicMock()
    with patch("derisk_serve.workspace.materializer._materialize_skill") as ms, \
         patch("derisk_serve.workspace.materializer._materialize_mcp") as mm:
        ms.return_value = MagicMock(spec=[], name="skill-resource")
        mm.return_value = MagicMock(spec=[], name="mcp-resource")
        result = materialize_playbook_declaration(fake_system_app, declaration)
        assert len(result) == 2
        assert all(not isinstance(r, list) for r in result)
        ms.assert_called_once_with("skill-a", {"name": "skill-a"})
        mm.assert_called_once_with("s1", {"name": "mcp-x", "server_name": "s1"})


def test_materialize_playbook_declaration_handles_string_skills():
    from derisk_serve.workspace.materializer import materialize_playbook_declaration

    declaration = {"skills": ["skill-a", "skill-b"]}
    fake_system_app = MagicMock()
    with patch("derisk_serve.workspace.materializer._materialize_skill") as ms:
        ms.return_value = MagicMock(spec=[], name="skill-resource")
        result = materialize_playbook_declaration(fake_system_app, declaration)
        assert len(result) == 2
        assert ms.call_count == 2


def test_materialize_playbook_declaration_empty():
    from derisk_serve.workspace.materializer import materialize_playbook_declaration

    fake_system_app = MagicMock()
    assert materialize_playbook_declaration(fake_system_app, {}) == []
    assert materialize_playbook_declaration(fake_system_app, None) == []
