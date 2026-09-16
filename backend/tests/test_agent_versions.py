import uuid

from sqlalchemy import select

from app.models import AgentTool, Message, Session, Tool, User

AGENT = {
    "name": "A",
    "system_prompt": "你是 {{agent.name}}",
    "model_config": {"model": "m1"},
    "tags": [],
    "examples": [],
}


async def _agent(client, auth_headers) -> dict:
    return (await client.post("/api/v1/agents", json=AGENT, headers=auth_headers)).json()


async def test_publish_creates_incrementing_versions(client, auth_headers):
    aid = (await _agent(client, auth_headers))["id"]
    v1 = await client.post(f"/api/v1/agents/{aid}/publish", headers=auth_headers)
    assert v1.status_code == 200 and v1.json()["version"] == 1 and v1.json()["status"] == "published"

    await client.patch(f"/api/v1/agents/{aid}", json={"name": "A2"}, headers=auth_headers)
    v2 = await client.post(f"/api/v1/agents/{aid}/publish", headers=auth_headers)
    assert v2.json()["version"] == 2

    versions = await client.get(f"/api/v1/agents/{aid}/versions", headers=auth_headers)
    assert [v["version"] for v in versions.json()] == [2, 1]
    assert versions.json()[1]["snapshot"]["name"] == "A"
    # 快照字段齐全（含 tool_slugs / skill_slugs / mcp_tools）
    assert set(versions.json()[1]["snapshot"]) == {
        "name",
        "emoji",
        "description",
        "tags",
        "system_prompt",
        "model_config",
        "welcome_msg",
        "examples",
        "tool_slugs",
        "skill_slugs",
        "mcp_tools",
    }
    assert versions.json()[1]["snapshot"]["tool_slugs"] == []


async def test_rollback_restores_snapshot_and_tools(client, auth_headers, session_maker):
    from app.ai.tools import sync_tools

    async with session_maker() as db:
        await sync_tools(db)
    aid = (await _agent(client, auth_headers))["id"]
    # 发布 v1（无工具），改名并绑定 time_now 后发布 v2
    await client.post(f"/api/v1/agents/{aid}/publish", headers=auth_headers)
    await client.patch(f"/api/v1/agents/{aid}", json={"name": "A2"}, headers=auth_headers)
    async with session_maker() as db:
        tool = await db.scalar(select(Tool).where(Tool.slug == "time_now"))
        assert tool is not None
        db.add(AgentTool(agent_id=uuid.UUID(aid), tool_id=tool.id))
        await db.commit()
    await client.post(f"/api/v1/agents/{aid}/publish", headers=auth_headers)

    # 改名后再回滚到 v1：状态回到 draft，current_version 保持最新发布号 2
    await client.patch(f"/api/v1/agents/{aid}", json={"name": "A3"}, headers=auth_headers)
    r = await client.post(
        f"/api/v1/agents/{aid}/rollback", json={"version": 1}, headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["name"] == "A"
    assert r.json()["status"] == "draft" and r.json()["current_version"] == 2
    async with session_maker() as db:
        rows = (await db.scalars(select(AgentTool).where(AgentTool.agent_id == uuid.UUID(aid)))).all()
        assert rows == []  # v1 无工具

    # 再回滚到 v2 → 工具绑定恢复为 time_now（重绑正路径）
    r2 = await client.post(
        f"/api/v1/agents/{aid}/rollback", json={"version": 2}, headers=auth_headers
    )
    assert r2.status_code == 200 and r2.json()["name"] == "A2"
    async with session_maker() as db:
        slugs = (
            await db.scalars(
                select(Tool.slug)
                .join(AgentTool, AgentTool.tool_id == Tool.id)
                .where(AgentTool.agent_id == uuid.UUID(aid))
            )
        ).all()
        assert list(slugs) == ["time_now"]

    # 回滚目标版本不存在 → 404
    missing = await client.post(
        f"/api/v1/agents/{aid}/rollback", json={"version": 99}, headers=auth_headers
    )
    assert missing.status_code == 404


async def test_delete_referenced_agent_conflicts(client, auth_headers, session_maker):
    aid = (await _agent(client, auth_headers))["id"]
    async with session_maker() as db:
        user = (await db.scalars(select(User))).first()
        s = Session(user_id=user.id, agent_id=uuid.UUID(aid))
        db.add(s)
        await db.flush()
        db.add(
            Message(
                session_id=s.id,
                role="user",
                blocks=[{"type": "text", "content": "x"}],
                agent_id=uuid.UUID(aid),
            )
        )
        await db.commit()
    r = await client.delete(f"/api/v1/agents/{aid}", headers=auth_headers)
    assert r.status_code == 409
    # 归档可行
    ok = await client.patch(
        f"/api/v1/agents/{aid}", json={"status": "archived"}, headers=auth_headers
    )
    assert ok.status_code == 200


async def test_delete_agent_referenced_only_by_session_conflicts(
    client, auth_headers, session_maker
):
    # 仅被 Session 引用、无消息时也应 409，避免 IntegrityError 500
    aid = (await _agent(client, auth_headers))["id"]
    async with session_maker() as db:
        user = (await db.scalars(select(User))).first()
        db.add(Session(user_id=user.id, agent_id=uuid.UUID(aid)))
        await db.commit()
    r = await client.delete(f"/api/v1/agents/{aid}", headers=auth_headers)
    assert r.status_code == 409
