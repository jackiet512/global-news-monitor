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
