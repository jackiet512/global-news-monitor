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
