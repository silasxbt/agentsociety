"""Capability questions are answered from the tool registry, not generated prose."""

from agentsociety2.env.base import EnvBase, tool
from agentsociety2.env.router_base import (
    format_registered_tool_catalog,
    is_capability_question,
    scrub_false_capability_denial,
)
from agentsociety2.env.router_codegen import CodeGenRouter


class _LifeEnv(EnvBase):
    """Elder life."""

    @tool(readonly=True, kind="observe")
    async def observe_my_life(self, agent_id: int) -> dict:
        """观察自己当前的生活处境。"""
        return {"ok": True}

    @tool(readonly=False)
    async def call_family(self, agent_id: int, child_name: str, reason: str) -> dict:
        """给子女打电话。"""
        return {"ok": True, "message": f"和{child_name}通了电话"}


def test_ordinary_call_is_not_a_capability_question():
    assert not is_capability_question("给孩子打电话，问问有没有空")
    assert not is_capability_question("<observe>")
    assert is_capability_question("环境是否提供联系子女、邻居的功能")
    assert is_capability_question("有没有打电话的功能")


def test_readonly_catalog_keeps_write_tools_as_existing(tmp_path):
    router = CodeGenRouter(
        env_modules=[_LifeEnv()],
        template_cache_enabled=False,
        template_cache_dir=str(tmp_path),
    )
    text = format_registered_tool_catalog(router._all_tools_info, readonly=True)
    assert "call_family（exists=true, callable_now=false）" in text
    assert "observe_my_life（exists=true, callable_now=true）" in text
    assert "readonly=false" in text


async def test_capability_ask_does_not_call_the_code_model(tmp_path):
    router = CodeGenRouter(
        env_modules=[_LifeEnv()],
        template_cache_enabled=False,
        template_cache_dir=str(tmp_path),
    )

    async def _boom(*_args, **_kwargs):
        raise AssertionError("capability questions must not call the code model")

    router.acompletion = _boom
    _ctx, answer = await router.ask(
        {"agent_id": 1},
        "有没有联系子女的功能",
        readonly=True,
    )
    assert "call_family" in answer
    assert "callable_now=false" in answer
    assert "不存在" not in answer.split("call_family", 1)[-1][:80]


def test_scrub_replaces_false_denial_and_keeps_real_tool_result(tmp_path):
    router = CodeGenRouter(
        env_modules=[_LifeEnv()],
        template_cache_enabled=False,
        template_cache_dir=str(tmp_path),
    )
    tools = router._all_tools_info
    replaced, denied = scrub_false_capability_denial(
        "环境只支持查询，不能打电话、不能串门。",
        "response = await modules['LifeEnv'].observe_my_life(ctx['agent_id'])",
        tools,
        readonly=True,
    )
    assert denied
    assert "exists=true" in replaced
    assert "不能打电话" not in replaced

    kept, denied = scrub_false_capability_denial(
        "联系人里没有「邓2」",
        "response = await modules['LifeEnv'].call_family(ctx['agent_id'], '邓2', '想聊聊')",
        tools,
        readonly=False,
    )
    assert not denied
    assert kept == "联系人里没有「邓2」"


def test_prompt_tells_the_agent_not_to_discover_tools():
    from agentsociety2.agent.person_prompt import build_preamble

    prompt = build_preamble(name="李阿姨", ask_mode=False)
    assert "readonly=false" in prompt
    assert "whether a function exists" in prompt
