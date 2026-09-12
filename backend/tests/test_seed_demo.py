import json


def test_flagship_messages_cover_all_demo_blocks():
    from scripts.seed_demo_sessions import build_flagship_messages

    messages = build_flagship_messages()
    assert messages[0]["role"] == "user"
    assert [m["role"] for m in messages].count("assistant") >= 2  # 主回答 + 接力回答
    types = [block["type"] for message in messages for block in message["blocks"]]
    for expected in ("thinking", "tool_call", "tool_result", "citation", "text"):
        assert expected in types


def test_flagship_thinking_duration_and_json_roundtrip():
    from scripts.seed_demo_sessions import build_flagship_messages

    messages = build_flagship_messages()
    thinking = [
        block for message in messages for block in message["blocks"] if block["type"] == "thinking"
    ]
    assert thinking and all(block["duration_ms"] > 0 for block in thinking)
    dumped = json.dumps(messages, ensure_ascii=False)
    assert "线程池" in dumped  # 直接写入 JSONB：可序列化且中文不转义
