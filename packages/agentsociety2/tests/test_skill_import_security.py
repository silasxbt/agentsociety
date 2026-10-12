from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from agentsociety2.backend.routers import agent_skills


@pytest.mark.asyncio
async def test_import_rejects_outside_and_prefix_sibling(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    for source in (tmp_path / "outside", tmp_path / "workspace-sibling"):
        source.mkdir()
        (source / "SKILL.md").write_text("test")
        with pytest.raises(HTTPException, match="inside the workspace"):
            await agent_skills.import_skill(
                agent_skills.ImportRequest(source_path=str(source))
            )
    assert not (workspace / "custom").exists()


@pytest.mark.asyncio
async def test_import_rejects_nested_symlink_before_replacing(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    source = workspace / "incoming" / "example"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("test")
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (source / "linked.txt").symlink_to(outside)
    destination = workspace / "custom" / "skills" / "example"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("existing")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    with pytest.raises(HTTPException, match="symbolic links"):
        await agent_skills.import_skill(
            agent_skills.ImportRequest(source_path=str(source))
        )
    assert (destination / "SKILL.md").read_text() == "existing"
    assert not (destination / "linked.txt").exists()


@pytest.mark.asyncio
async def test_import_valid_skill(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    source = workspace / "incoming" / "example"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("valid skill")
    (source / "scripts").mkdir()
    (source / "scripts" / "run.py").write_text("print('ok')")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    registry = Mock()
    monkeypatch.setattr(agent_skills, "get_skill_registry", lambda: registry)
    result = await agent_skills.import_skill(
        agent_skills.ImportRequest(source_path=str(source))
    )
    destination = workspace / "custom" / "skills" / "example"
    assert result.success
    assert (destination / "SKILL.md").read_text() == "valid skill"
    assert (destination / "scripts" / "run.py").is_file()
