import unittest
from unittest.mock import patch


class LabelGuardTest(unittest.TestCase):
    """사진 인식이 실패해도 GPT 가 메뉴 이름·가게 설명을 지어내 사진 라벨에 붙이지 않아야 해요."""
    shop = {"name": "포스트톡베이커리", "area": "", "address": "", "hours": ""}

    def _client(self, copy, caption):
        import json
        out = {"template": "t2", "default": False, "summary_ko": "x", "keywords_ko": [], "copy": copy, "caption": caption}
        msg = type("M", (), {"content": json.dumps(out, ensure_ascii=False)})()
        resp = type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
        return type("Cl", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(lambda **k: resp)})()})()})()

    def test_blind_profile_drops_invented_labels_and_caption(self):
        from cardnews import design
        bad = {"t2": {"c3": {"p1": "소금빵", "p2": "마카롱", "p3": "오레오 쿠키", "p4": "커피"}}}
        cap = {"hook": "방앗간에서 직접 만든 빵 ~~ ..", "body": "쌀가루로 아침마다 구워요 ~~ ..", "hashtags": []}
        st = design.make_style(self._client(bad, cap), "", self.shop, profile={"main_food": "소금빵"}, force="t2")
        self.assertEqual(st["copy"], {"t2": {}})
        self.assertNotIn("방앗간", st["caption"]["text"])

    def test_t2_store_labels_are_never_food_names(self):
        from cardnews import design
        prof = {"main_food": "소금빵", "dish": {"food1": "소금빵", "food2": "오레오쿠키"}}
        bad = {"t2": {"c3": {"p1": "마카롱", "p2": "마카롱", "p3": "커피", "p4": "커피"}}}
        st = design.make_style(self._client(bad, {"hook": "소금빵 ~~ ..", "body": "맛있어요 ~~ ..", "hashtags": []}), "", self.shop, profile=prof, force="t2")
        c3 = st["copy"]["t2"]["c3"]
        self.assertEqual((c3["p1"], c3["p3"]), ("소금빵", "오레오쿠키"))
        self.assertNotIn(c3["p2"], ("마카롱", "커피"))
        self.assertNotIn(c3["p4"], ("마카롱", "커피"))

    def test_owner_menus_follow_photo_order(self):
        from cardnews import design
        p = design.apply_owner_menus({"main_food": "x"}, ["소금빵", "마카롱", "오레오 쿠키", "무시"])
        self.assertEqual(p["dish"], {"bowl": "소금빵", "zoom": "소금빵", "food1": "마카롱", "food2": "오레오 쿠키"})
        self.assertEqual(design.apply_owner_menus({"a": 1}, []), {"a": 1})


    def test_partial_owner_menus_cannot_leave_invented_photo_labels(self):
        from cardnews import design
        for names in (["쿠키"], ["쿠키", "소금빵"], ["쿠키", "소금빵", "초코빵"]):
            with self.subTest(names=names):
                shop = {**self.shop, "menus": names}
                prof = design.apply_owner_menus({}, names)
                bad = {"t2": {"c3": {"p1": "마카롱", "p2": "커피", "p3": "라떼", "p4": "홍차"}}}
                style = design.make_style(self._client(bad, {}), "", shop, profile=prof, force="t2")
                actual = design.default_copy(shop, prof)["t2"]["c3"]
                actual.update(style["copy"]["t2"].get("c3", {}))
                self.assertEqual(actual["p1"], names[1] if len(names) > 1 else "오늘의 메뉴")
                self.assertEqual(actual["p3"], names[2] if len(names) > 2 else "메뉴 사진")
                self.assertEqual((actual["p2"], actual["p4"]), ("우리 가게 ✧", "편안한 공간"))

    def test_menu_details_are_owner_input_and_order_is_used_without_openai(self):
        import os
        from cardnews import api, design
        body = self._body(menu_details=[{"name": "쿠키"}, {"name": "소금빵"}, {"name": "초코빵"}])
        shop = {**self.shop, "menu_details": [menu.model_dump() for menu in body.menu_details]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            profile, style = api.build_style(body, {}, shop)
        self.assertTrue(style["fallback"])
        self.assertEqual(profile["dish"], {"bowl": "쿠키", "zoom": "쿠키", "food1": "소금빵", "food2": "초코빵"})
        self.assertEqual(design.default_copy(shop, profile)["t2"]["c3"]["p1"], "소금빵")
        with patch.object(design, "ask_gpt", return_value=({"template": "t2", "copy": {"t2": {"c0": {"q": "오늘은 쿠키?"}}}}, "fake")):
            style = design.make_style(None, "", shop, force="t2")
        self.assertFalse(style["fallback"])
        self.assertEqual(style["copy"]["t2"]["c0"]["q"], "오늘은 쿠키?")

    def test_legacy_menu_name_is_also_used_without_openai(self):
        import os
        from cardnews import api
        body = self._body(menu_name="쿠키")
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            profile, _ = api.build_style(body, {}, self.shop)
        self.assertEqual(profile["dish"]["bowl"], "쿠키")

    def test_blind_or_empty_recognition_skips_ad_copy_generation(self):
        from cardnews import design
        for profile in ({}, {"dish": {"bowl": "", "food1": ""}}):
            with self.subTest(profile=profile), patch.object(design, "ask_gpt") as ask:
                style = design.make_style(None, "", self.shop, profile=profile, force="t2")
                ask.assert_not_called()
                self.assertTrue(style["fallback"])
                self.assertEqual(style["copy"], {"t2": {}})

    def test_openai_timeout_does_not_multiply_sdk_and_model_retries(self):
        import os
        from cardnews import api, design
        body = self._body(menus=["쿠키", "소금빵"])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-test-key"}),              patch.object(api, "OpenAI") as client,              patch.object(design, "analyze_photos", return_value={"error": "timeout"}) as analyze,              patch.object(design, "make_style", return_value={}) as make:
            profile, _ = api.build_style(body, {}, {**self.shop, "menus": body.menus})
        client.assert_called_once_with(timeout=60.0, max_retries=0)
        self.assertEqual(analyze.call_args.kwargs["models"], design.MODELS[:1])
        self.assertEqual(make.call_args.kwargs["models"], design.MODELS[:1])
        self.assertEqual(profile["dish"]["food1"], "소금빵")

    def test_unrecognized_christmas_photo_labels_drop_dependent_copy(self):
        from cardnews import design
        for tpl in ("x2", "x4"):
            with self.subTest(template=tpl):
                raw = {tpl: {"c2": {"n1": "마카롱", "n2": "커피", "d2": "커피 설명", "n3": "라떼", "d3": "라떼 설명"}}}
                style = design.make_style(self._client(raw, {}), "", self.shop,
                                          profile={"main_food": "쿠키", "dish": {"bowl": "쿠키"}}, force=tpl, theme="christmas")
                labels = style["copy"][tpl]["c2"]
                self.assertEqual(labels["n1"], "쿠키")
                for key in ("n2", "n3", "d2", "d3"):
                    self.assertNotIn(key, labels)

    def _body(self, **fields):
        from cardnews import api
        return api.RenderRequest(
            job_id="11111111-1111-4111-8111-111111111111", store_name=self.shop["name"],
            photos=[{"role": role, "download_url": "unused"} for role in api.design.PHOTO_ROLES],
            uploads=["unused"] * 4, **fields,
        )


if __name__ == "__main__":
    unittest.main()
