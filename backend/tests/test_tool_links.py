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


def test_qrcode_without_extension_counts_as_image():
    # 支付二维码常见形态：返回 image/* 但地址没有图片后缀
    text = '{"orderId":1,"payOrderQrCodeUrl":"https://open.lkcoffee.com/transfer/qrcode?token=abc"}'
    links, images = extract_tool_links(text)
    assert images == ["https://open.lkcoffee.com/transfer/qrcode?token=abc"]
    assert links == []


def test_extracts_payment_custom_scheme_as_link():
    # weixin:// 这类自定义协议要放行，前端才能点击唤起客户端
    text = '{"payOrderUrl":"weixin://wxpay/bizpayurl?pr=5QQN6R31TEIEPv8M"}'
    links, images = extract_tool_links(text)
    assert links == ["weixin://wxpay/bizpayurl?pr=5QQN6R31TEIEPv8M"]
    assert images == []


def test_payment_result_keeps_both_link_and_qrcode():
    # 真实工具返回：JSON 里同时有自定义协议支付链接与二维码地址
    text = (
        '{"code":0,"data":{"payOrderUrl":"weixin://wxpay/bizpayurl?pr=abc",'
        '"payOrderQrCodeUrl":"https://open.lkcoffee.com/transfer/qrcode?token=xyz"}}'
    )
    links, images = extract_tool_links(text)
    assert links == ["weixin://wxpay/bizpayurl?pr=abc"]
    assert images == ["https://open.lkcoffee.com/transfer/qrcode?token=xyz"]


def test_dangerous_schemes_are_not_extracted():
    # javascript:/data: 等不在白名单，不能变成可点击内容
    text = "javascript:alert(1) data:image/png;base64,AAAA file:///C:/x"
    assert extract_tool_links(text) == ([], [])


def test_mailto_and_tel_are_kept():
    links, images = extract_tool_links("联系 mailto:a@b.com 或 tel:+8613800000000")
    assert links == ["mailto:a@b.com", "tel:+8613800000000"]
    assert images == []
