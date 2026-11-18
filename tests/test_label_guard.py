import unittest


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


if __name__ == "__main__":
    unittest.main()
