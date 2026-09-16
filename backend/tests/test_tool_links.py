from app.ai.runtime import extract_tool_links


def test_extracts_links_and_images_from_json_text():
    # 工具常见返回：JSON 里带 url / 缩略图（就是普通子串，正则能命中）
    text = '{"results":[{"url":"https://a.com/x","title":"t"},{"thumb":"https://a.com/t.png"}]}'
    links, images = extract_tool_links(text)
    assert links == ["https://a.com/x"]
    assert images == ["https://a.com/t.png"]


def test_strips_trailing_punctuation_and_dedupes():
    text = "见 https://a.com/x。 还有 https://a.com/x 和 https://b.com/y,"
    links, images = extract_tool_links(text)
    assert links == ["https://a.com/x", "https://b.com/y"]
    assert images == []


def test_image_urls_classified_and_capped():
    text = " ".join(f"https://a.com/{i}.png" for i in range(8))
    links, images = extract_tool_links(text)
    assert links == []
    assert len(images) == 5  # TOOL_LINK_MAX


def test_no_url_returns_empty():
    assert extract_tool_links("") == ([], [])
    assert extract_tool_links("没有链接") == ([], [])


def test_recognises_image_with_query_string():
    links, images = extract_tool_links("https://a.com/t.JPEG?w=200")
    assert images == ["https://a.com/t.JPEG?w=200"]
    assert links == []
