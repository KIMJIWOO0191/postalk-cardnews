import json
import os
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from . import design

Image.MAX_IMAGE_PIXELS = 32_000_000


def render_cards(photos: dict, shop: dict, profile: dict, style: dict, root: Path) -> list[Path]:
    template = style["template"]
    copy = design.default_copy(shop, profile)
    for card, fields in (style.get("copy") or {}).get(template, {}).items():
        if card in copy[template] and isinstance(fields, dict):
            copy[template][card].update({
                key: value[:500] for key, value in fields.items()
                if key in copy[template][card] and isinstance(value, str) and value.strip()
            })

    data = {
        "copy": copy,
        "vars": {"hand": "'GamjaFlower', 'NotoKR', cursive", **style.get("vars", {})},
        "photos": {role: design._uri(photos[role]) for role in design.PHOTO_ROLES},
        "tpl": template,
    }
    template_path = design.HERE / ("xmas.html" if template.startswith("x") else "mini3.html")
    # Escape script delimiters before inserting any generated text or user data.
    encoded = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    html = template_path.read_text(encoding="utf-8").replace("__DATA__", encoded)
    html = html.replace("<head>", f'<head><base href="{design.HERE.as_uri()}/">', 1)
    page_file = root / "page.html"
    page_file.write_text(html, encoding="utf-8")
    paths = [root / f"card-{i}.png" for i in range(1, 4)]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("CARDNEWS_CHROMIUM_PATH") or None)
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1350})
            page.route(re.compile(r"^https?://"), lambda route: route.abort())
            page.goto(page_file.as_uri())
            page.wait_for_selector('body[data-ready="1"]', timeout=20_000)
            for index, path in enumerate(paths, 1):
                page.locator(f"#{template}c{index}").screenshot(path=str(path), timeout=20_000)
        finally:
            browser.close()
    return paths
