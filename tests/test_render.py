import io
import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from cardnews import api


class CardNewsRenderTest(unittest.TestCase):
    project = "https://test.supabase.co"
    job_id = "11111111-1111-4111-8111-111111111111"
    headers = {"x-cardnews-api-key": "test-key"}

    def setUp(self):
        env = patch.dict(os.environ, {
            "SUPABASE_URL": self.project, "CARDNEWS_INTERNAL_API_KEY": "test-key", "OPENAI_API_KEY": "",
        })
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(api.app)

    def body(self, theme="minimal", cards=4):
        return {
            "job_id": self.job_id, "theme": theme, "store_name": "떡집 </script>", "menu_name": "쑥떡",
            "store_address": "시장로 15", "menu_details": [{"name": "쑥떡", "description": "현미, 쑥으로 만들어요."}],
            "photos": [
                {"role": role, "download_url": f"{self.project}/storage/v1/object/sign/uploads/{role}.jpg?token=test"}
                for role in api.design.PHOTO_ROLES
            ],
            "uploads": [
                f"{self.project}/storage/v1/object/upload/sign/uploads/store/submission/generated/{self.job_id}-{i}.png?token=test"
                for i in range(1, cards + 1)
            ],
        }

    def test_healthz_identifies_the_service_and_storage(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "ok", "service": "postalk-cardnews", "mediaProvider": "supabase",
        })

    def test_rejects_missing_credentials_and_foreign_storage(self):
        body = self.body()
        self.assertEqual(self.client.post("/cardnews/renders", json=body).status_code, 401)
        body["photos"][0]["download_url"] = "https://other.example/photo"
        self.assertEqual(self.client.post("/cardnews/renders", headers=self.headers, json=body).status_code, 400)

    def test_streams_progress_and_preserves_validation_errors(self):
        def steps(body, destinations):
            for stage in ["preparing", "scripting", "designing", "rendering", "uploading"]:
                yield {"type": "progress", "stage": stage}
            yield {"type": "result", "result": {"cards": [], "template": "t1", "fallback": True}}

        headers = {**self.headers, "accept": "application/x-ndjson"}
        with patch.object(api, "render_steps", side_effect=steps):
            response = self.client.post("/cardnews/renders", headers=headers, json=self.body())
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers["content-type"])
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([event["stage"] for event in events[:-1]], ["preparing", "scripting", "designing", "rendering", "uploading"])
        self.assertEqual(events[-1]["type"], "result")
        body = self.body()
        body["photos"][0]["download_url"] = "https://other.example/photo"
        self.assertEqual(self.client.post("/cardnews/renders", headers=headers, json=body).status_code, 400)

    def test_stream_errors_are_terminal_without_a_success_result(self):
        def broken_steps(*args):
            yield {"type": "progress", "stage": "rendering"}
            raise api.HTTPException(502, "Unable to create card news")

        with patch.object(api, "render_steps", side_effect=broken_steps):
            response = self.client.post("/cardnews/renders", headers={**self.headers, "accept": "application/x-ndjson"}, json=self.body())
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1], {"type": "error", "code": "RENDER_FAILED"})
        self.assertFalse(any(event["type"] == "result" for event in events))

    def test_both_themes_render_cover_and_body_with_legacy_support(self):
        for theme, template, count in [("minimal", "t1", 4), ("christmas", "x1", 4), ("minimal", "t1", 3)]:
            with self.subTest(theme=theme, count=count):
                uploads = {}

                def storage(request):
                    if request.method == "GET":
                        color = list(api.design.PHOTO_ROLES).index(request.url.path.split("/")[-1][:-4])
                        photo = io.BytesIO()
                        Image.new("RGB", (260, 320), (30 + color * 25, 60, 100)).save(photo, "JPEG")
                        return httpx.Response(200, content=photo.getvalue())
                    self.assertEqual(request.method, "PUT")
                    self.assertEqual(request.headers["content-type"], "image/png")
                    uploads[request.url.path.split("/uploads/")[-1]] = request.read()
                    return httpx.Response(200, json={})

                transfer = httpx.Client(transport=httpx.MockTransport(storage))
                with patch.object(api.httpx, "Client", return_value=transfer):
                    response = self.client.post("/cardnews/renders", headers=self.headers, json=self.body(theme, count))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["template"], template)
                self.assertEqual(len(uploads), count)
                self.assertIn("쑥떡", response.json()["caption"])
                self.assertIn("시장로 15", response.json()["caption"])
                self.assertIn("#쑥떡", response.json()["hashtags"])
                for card in response.json()["cards"]:
                    image = uploads[card["key"]]
                    self.assertEqual(len(image), card["bytes"])
                    with Image.open(io.BytesIO(image)) as rendered:
                        self.assertEqual(rendered.format, "PNG")
                        self.assertEqual(rendered.size, (1080, 1350))
                        self.assertGreater(len(rendered.getcolors(512) or [None] * 513), 5)

    def test_caption_rejects_unsupported_promotion_and_respects_owner_input(self):
        shop = {"name": "시장떡집", "area": "중앙시장", "desc": "20년째 떡을 만들어요", "menus": ["쑥떡"]}
        profile = {"main_food": "쑥떡"}
        invalid = {"hook": "오늘 무료로 드려요", "body": "할인 이벤트가 열리고 있어요."}
        fallback = api.design.clean_caption(invalid, shop, profile)
        self.assertNotIn("무료", fallback["text"])
        self.assertIn("📍 시장떡집", fallback["text"])
        valid = {"hook": "20년째 떡을 만들어요", "body": "쑥떡이 눈에 들어오는 곳이에요.", "hashtags": ["#쑥떡", "#쑥떡"]}
        cleaned = api.design.clean_caption(valid, shop, profile)
        self.assertIn(valid["hook"], cleaned["text"])
        self.assertEqual(cleaned["hashtags"].count("#쑥떡"), 1)

    def test_ai_style_keeps_cover_and_caption_for_selected_template(self):
        shop = {"name": "시장떡집", "area": "중앙시장", "desc": "20년째 떡을 만들어요", "menus": ["쑥떡"]}
        raw = {"template": "t2", "copy": {"t2": {"c0": {"q": "오늘은 쑥떡?"}}},
               "caption": {"hook": "20년째 떡을 만들어요", "body": "쑥떡이 눈에 들어오는 곳이에요.", "hashtags": ["#쑥떡"]}}
        with patch.object(api.design, "ask_gpt", return_value=(raw, "test-model")):
            style = api.design.make_style(None, "귀엽게", shop, profile={"main_food": "쑥떡"})
        self.assertFalse(style["fallback"])
        self.assertEqual(style["copy"]["t2"]["c0"]["q"], "오늘은 쑥떡?")
        self.assertIn(raw["caption"]["hook"], style["caption"]["text"])

    def test_unsupported_ad_claims_are_removed_from_cards_caption_and_tags(self):
        shop = {"name": "바다한상", "menus": ["간장게장"], "desc": "간장게장을 만들어요"}
        profile = {"shop_type": "횟집", "main_food": "간장게장"}
        raw = {
            "template": "t1",
            "copy": {"t1": {"c0": {"sub": "20년째 같은 자리", "t": "간장게장\n만나보세요 . ~~ .."},
                            "c2": {"desc": "모란시장의 횟집"}}},
            "caption": {"hook": "20년째 같은 자리", "body": "간장게장을 만드는 횟집입니다.", "hashtags": ["#횟집"]},
        }
        with patch.object(api.design, "ask_gpt", return_value=(raw, "test-model")):
            style = api.design.make_style(None, "", shop, profile=profile)
        self.assertEqual(style["copy"]["t1"]["c0"], {"t": "간장게장\n만나보세요."})
        self.assertEqual(style["copy"]["t1"]["c2"], {})
        self.assertNotIn("횟집", str(style["caption"]))
        self.assertNotIn("20년째", style["caption"]["text"])
        self.assertIn("오늘의 메뉴는 간장게장입니다.", style["caption"]["text"])
        self.assertNotIn("횟집", str(api.design.default_copy(shop, profile)))

    def test_design_request_cannot_be_used_as_cover_copy(self):
        shop = {"name": "바다한상", "menus": ["간장게장"]}
        raw = {"template": "t1", "copy": {"t1": {"c0": {"t": "딥네이비 / 크림색", "sub": "간장게장"}}}}
        with patch.object(api.design, "ask_gpt", return_value=(raw, "test-model")):
            style = api.design.make_style(None, "딥네이비 / 크림색", shop)
        self.assertEqual(style["copy"]["t1"]["c0"], {"sub": "간장게장"})

    def test_incomplete_cover_title_uses_menu_fallback(self):
        shop = {"name": "바다한상", "menu_details": [{"name": "간장게장"}]}
        for title in ("신선한 꽃게가", "오늘의 메뉴\n신선한 꽃게가", "싱싱한 게\n그리고", "싱싱한 게\n간장게장을 먹으러"):
            with self.subTest(title=title):
                raw = {"template": "t3", "copy": {"t3": {"c0": {"t": title, "sub": "대표 메뉴"}}}}
                with patch.object(api.design, "ask_gpt", return_value=(raw, "test-model")):
                    style = api.design.make_style(None, "", shop)
                self.assertEqual(style["copy"]["t3"]["c0"], {"sub": "대표 메뉴"})
                self.assertEqual(api.design.default_copy(shop)["t3"]["c0"]["t"], "오늘의 메뉴\n간장게장.zip")

    def test_cover_keeps_complete_titles_and_normalizes_model_line_breaks(self):
        for template, title, expected in (
            ("t1", "오늘의 메뉴 / 간장게장", "오늘의 메뉴\n간장게장"),
            ("t3", "골목 맛집\\n한 접시.zip", "골목 맛집\n한 접시.zip"),
            ("x3", "Cozy\nTable", "Cozy\nTable"),
        ):
            with self.subTest(template=template):
                raw = {"template": template, "copy": {template: {"c0": {"t": title}}}}
                with patch.object(api.design, "ask_gpt", return_value=(raw, "test-model")):
                    style = api.design.make_style(None, "", {"name": "가게", "menus": ["간장게장"]}, theme="christmas" if template.startswith("x") else "minimal")
                self.assertEqual(style["copy"][template]["c0"]["t"], expected)

    def test_caption_normalizes_punctuation_and_excludes_unconfirmed_hashtags(self):
        shop = {"name": "바다한상", "menus": ["간장게장"]}
        caption = api.design.clean_caption({
            "hook": "간장게장을 만나보세요 . ~~ ..",
            "body": "가게에서 간장게장을 맛보세요 ~ !",
            "hashtags": ["#횟집", "#20년째", "#간장게장"],
        }, shop)
        self.assertEqual(caption["hook"], "간장게장을 만나보세요.")
        self.assertEqual(caption["body"], "가게에서 간장게장을 맛보세요!")
        self.assertEqual(caption["hashtags"], ["#간장게장", "#바다한상"])

    def test_smaller_price_does_not_match_a_substring_of_owner_price(self):
        shop = {"name": "바다한상", "menu_details": [{"name": "간장게장", "description": "15,000원"}]}
        raw = {"hook": "간장게장 한 접시", "body": "간장게장 한 접시는 5,000원이에요."}
        self.assertNotIn("5,000원", api.design.clean_caption(raw, shop)["text"])
        raw["body"] = "간장게장 한 접시는 15,000원이에요."
        self.assertIn("15,000원", api.design.clean_caption(raw, shop)["text"])

    def test_internal_openapi_describes_json_ndjson_and_errors(self):
        responses = self.client.get("/openapi.json").json()["paths"]["/cardnews/renders"]["post"]["responses"]
        self.assertEqual(set(responses["200"]["content"]), {"application/json", "application/x-ndjson"})
        self.assertTrue({"400", "401", "422", "502", "503"} <= responses.keys())
