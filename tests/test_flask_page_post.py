from unittest import TestCase
import os
import tempfile
from flask import Flask
import json
from kubee2etests.frontend.flask_app import healthcheck
from kubee2etests.helpers_and_globals import StatusEvent
from http import HTTPStatus

class TestFlaskPagePostSuite(TestCase):
    def setUp(self):
        self.app = Flask("test_app", template_folder='kubee2etests/frontend/templates')
        self.app.register_blueprint(healthcheck)
        self.db_fd, self.app.config['DATABASE'] = tempfile.mkstemp()
        self.app.config['TESTING'] = True
        self.app = self.app.test_client()

    def test_post_valid_entry(self):
        entry = StatusEvent("Hello world", True)
        result = self.app.post("/update", data=json.dumps(entry.event_data), content_type="application/json")
        self.assertEqual(result.status_code, HTTPStatus.OK)
        data = json.loads(list(result.response)[0].decode())
        self.assertIn("result", data)
        self.assertEqual(data["result"], "event put onto queue")

    def test_post_invalid_entry(self):
        data = {"wibble": "hello"}
        result = self.app.post("/update", data=json.dumps(data), content_type="application/json")
        self.assertEqual(result.status_code, HTTPStatus.UNPROCESSABLE_ENTITY)
        data = json.loads(list(result.response)[0].decode())
        self.assertIn("result", data)
        self.assertEqual(data["result"], "Event object invalid: keys missing - name, passing, info, namespace, time")

    def test_valid_entry_in_index(self):
        entry = StatusEvent("Hello world", True)
        result = self.app.post("/update", data=json.dumps(entry.event_data), content_type="application/json")
        self.assertEqual(result.status_code, HTTPStatus.OK)
        response = self.app.get("/")
        self.assertIn("Hello world", str(response.data))

    def test_invalid_entry_not_in_index(self):
        entry = {"wibble": "hello"}
        result = self.app.post("/update", data=json.dumps(entry), content_type="application/json")
        self.assertEqual(result.status_code, HTTPStatus.UNPROCESSABLE_ENTITY)
        response = self.app.get("/")
        self.assertNotIn("wibble", str(response.data))

    def test_time_is_correct(self):
        entry = StatusEvent("hello world", True)
        result = self.app.post("/update", data=json.dumps(entry.event_data), content_type="application/json")
        self.assertEqual(result.status_code, HTTPStatus.OK)
        response = self.app.get("/")
        self.assertIn("hello world", str(response.data))
        self.assertIn(entry.time.strftime('%Y-%m-%d %H:%M:%S'), str(response.data))

    def tearDown(self):
        os.close(self.db_fd)
