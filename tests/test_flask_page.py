import datetime
import math
import os
import queue
import tempfile
import unittest

from flask import Flask

from kubee2etests.frontend.flask_app import healthcheck, TEST_STATUS
from kubee2etests.helpers_and_globals import StatusEvent


class TestSuitePage(unittest.TestCase):
    def setUp(self):
        self.app = Flask("test_app", template_folder='kubee2etests/frontend/templates')
        self.app.register_blueprint(healthcheck)
        self.db_fd, self.app.config['DATABASE'] = tempfile.mkstemp()
        self.app.config['TESTING'] = True
        self.app = self.app.test_client()

    def test_get_none_ran(self):
        response = self.app.get('/')
        self.assertIn("No tests have ran yet, waiting...", str(response.data))

    def test_get_with_one_passing(self):
        TEST_STATUS.put(StatusEvent("Test passed", True))
        response = self.app.get('/')
        self.assertIn("Test passed", str(response.data))
        self.assertIn("bg-success text-success", str(response.data))
        self.assertNotIn("bg-danger text-danger", str(response.data))

    def test_get_with_one_failing(self):
        TEST_STATUS.put(StatusEvent("Test failed", False))
        response = self.app.get('/')
        self.assertIn("Test failed", str(response.data))
        self.assertNotIn("bg-success text-success", str(response.data))
        self.assertIn("bg-danger text-danger", str(response.data))

    def test_get_with_one_pass_one_fail(self):
        TEST_STATUS.put(StatusEvent("Test failed", False))
        TEST_STATUS.put(StatusEvent("Test passed", True))
        response = self.app.get('/')
        self.assertIn("Test failed", str(response.data))
        self.assertIn("Test passed", str(response.data))
        self.assertIn("bg-success text-success", str(response.data))
        self.assertIn("bg-danger text-danger", str(response.data))

    def test_get_twice_result_still_there(self):
        TEST_STATUS.put(StatusEvent("Test failed", False))
        response = self.app.get('/')
        response_two = self.app.get('/')
        data = response.data.decode()
        pre_table = data.split('<table class="status-table">')
        post_table = pre_table[1].split('</table')
        rows = post_table[0].split('<tr')
        data2 = response_two.data.decode()
        pre_table2 = data2.split('<table class="status-table">')
        post_table2 = pre_table2[1].split('</table')
        rows2 = post_table2[0].split('<tr')
        self.assertEqual(rows2[2], rows[2])

    def test_new_result_overwrites_old(self):
        test_name = "Test failed"
        TEST_STATUS.put(StatusEvent(test_name, False))
        response = self.app.get('/')
        TEST_STATUS.put(StatusEvent(test_name, True))
        response_two = self.app.get('/')
        data = response.data.decode()
        pre_table = data.split('<table class="status-table">')
        post_table = pre_table[1].split('</table')
        rows = post_table[0].split('<tr')
        self.assertEqual(len(rows), 3)
        self.assertIn("bg-danger text-danger", rows[2])
        self.assertIn(test_name, rows[2])
        data2 = response_two.data.decode()
        pre_table2 = data2.split('<table class="status-table">')
        post_table2 = pre_table2[1].split('</table')
        rows2 = post_table2[0].split('<tr')
        self.assertIn("bg-success text-success", rows2[2])
        self.assertIn(test_name, rows2[2])

    def test_first_result_still_there_second_overwritten(self):
        TEST_STATUS.put(StatusEvent("Test passed", True))
        TEST_STATUS.put(StatusEvent("Test failed", False))
        response = self.app.get('/')
        TEST_STATUS.put(StatusEvent("Test failed", True))
        response_two = self.app.get('/')
        self.assertIn("Test passed", str(response.data))
        self.assertIn("Test passed", str(response_two.data))
        self.assertNotEqual(str(response.data), str(response_two.data))

    def test_first_result_overwritten_second_still_there(self):
        TEST_STATUS.put(StatusEvent("Test passed", True))
        TEST_STATUS.put(StatusEvent("Test failed", False))
        response = self.app.get('/')
        TEST_STATUS.put(StatusEvent("Test passed", False))
        response_two = self.app.get('/')
        self.assertIn("Test failed", str(response.data))
        self.assertIn("Test failed", str(response_two.data))
        self.assertNotEqual(str(response.data), str(response_two.data))

    def test_time_shown(self):
        event = StatusEvent("Test passed", True)
        TEST_STATUS.put(event)
        response = self.app.get('/')
        self.assertIn(str(event.time), str(response.data))

    def test_show_error_if_time_an_hour_ago(self):
        nowish = datetime.datetime.now()
        event = StatusEvent("Test passed", True)
        event.time = datetime.datetime(day=nowish.day, month=nowish.month, year=nowish.year,
                              hour=nowish.hour - 1, minute=nowish.minute)
        TEST_STATUS.put(event)
        response = self.app.get('/')
        data = response.data.decode()
        expected_str = "ERROR! No test data for %i days %i hours and %i minutes" % (0, 1, 0)
        self.assertIn(str(event.time), data)
        self.assertIn(expected_str, data)

    def test_dont_show_error_if_time_within_last_hour(self):
        nowish = datetime.datetime.now()
        event = StatusEvent("Test passed", True)
        event.time = datetime.datetime(day=nowish.day, month=nowish.month, year=nowish.year,
                              hour=nowish.hour, minute=nowish.minute) - datetime.timedelta(minutes=10)
        TEST_STATUS.put(event)
        response = self.app.get("/")
        data = response.data.decode()
        expected_str = "ERROR! No test data for %i days %i hours and %i minutes" % (0, 0, math.floor(nowish.minute / 2))
        self.assertNotIn(expected_str, data)

    def tearDown(self):
        os.close(self.db_fd)
        while True:
            try:
                TEST_STATUS.get(block=False)
            except queue.Empty:
                break
