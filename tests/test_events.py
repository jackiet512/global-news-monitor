import unittest
from collector.events import signals, same_event

class EventTests(unittest.TestCase):
    def test_different_outlets_same_incident(self):
        rows=[
            ("Hegseth's team admonished for making noise at Tomb of the Unknown Soldier","赫格斯的团队因在无名烈士墓发出噪音而受到谴责"),
            ("Tomb of the Unknown Soldier guard scolds Hegseth and staff","无名烈士墓警卫斥责赫格塞斯和工作人员"),
            ("Guard appears to rebuke Hegseth's delegation at Tomb of Unknown Soldier","警卫似乎在无名烈士墓斥责赫格塞斯的代表团"),
            ("Hegseth and aides scolded by guard at Tomb of the Unknown Soldier","赫格斯和顾问在无名烈士墓受到守卫训斥")]
        events=[signals(*row,"2026-11-12T09:28:00+08:00") for row in rows]
        for event in events[1:]:
            self.assertTrue(same_event(events[0],event))
        unrelated=signals("House impeachment vote on Hegseth","众议院就赫格塞斯弹劾案投票","2026-11-12T09:28:00+08:00")
        self.assertFalse(same_event(events[0],unrelated))

    def test_bomb_threat_and_district_updates(self):
        from collector.events import incident_clues, matching_incident
        def clue(title,minute,lead=""):
            return incident_clues(dict(title=title,reading_text=lead,published_at=f"2026-11-12T22:{minute}:00+08:00"))
        self.assertTrue(matching_incident(clue("意大利多所学校收到炸弹威胁邮件","00"),clue("意大利至少300所学校因受炸弹威胁疏散","20")))
        self.assertFalse(matching_incident(clue("法国多所学校收到炸弹威胁","00"),clue("意大利学校收到炸弹威胁","00")))
        self.assertTrue(matching_incident(clue("首都洛根圆环有人被枪杀","10"),clue("华盛顿特区发生枪击事件","07")))

    def test_thanksgiving_storm_same_event(self):
        stamp1 = "2026-11-25T10:00:00+08:00"
        stamp2 = "2026-11-25T11:00:00+08:00"
        a = signals("Thanksgiving storm floods", "感恩节大风暴给美国带来洪水和航班延误", stamp1)
        b = signals("Thanksgiving storm outages", "强大的感恩节风暴导致洪水、停电", stamp2)
        self.assertTrue(same_event(a, b))

    def test_kuwait_attack_same_event(self):
        stamp = "2026-11-25T10:00:00+08:00"
        titles = [
            "两名意大利人在科威特袭击中丧生，伊朗否认对此负责",
            "伊朗被指控在科威特发动无人机袭击，造成两名意大利人死亡",
            "两名意大利人在科威特袭击事件中丧生，伊朗否认参与",
        ]
        events = [signals("Kuwait attack", t, stamp) for t in titles]
        for other in events[1:]:
            self.assertTrue(same_event(events[0], other))
        self.assertTrue(same_event(events[1], events[2]))

    def test_distinct_events_not_merged(self):
        stamp1 = "2026-11-25T10:00:00+08:00"
        stamp2 = "2026-11-25T11:00:00+08:00"
        pairs = [
            ("OpenAI发布新一代推理模型", "Anthropic发布新一代代码模型"),
            ("美联储宣布维持利率不变", "欧洲央行宣布降息25个基点"),
            ("法国多所学校收到炸弹威胁", "意大利多所学校收到炸弹威胁邮件"),
        ]
        for t1, t2 in pairs:
            a = signals("a", t1, stamp1)
            b = signals("b", t2, stamp2)
            self.assertFalse(same_event(a, b), f"should not merge: {t1} vs {t2}")
