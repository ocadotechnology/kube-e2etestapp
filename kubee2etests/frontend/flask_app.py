from flask import Blueprint, render_template, request, jsonify
from kubee2etests.helpers_and_globals import TIME_TO_REPORT_PARAMETER, StatusEvent
import queue
from collections import OrderedDict
from datetime import datetime
import logging
import os
from http import HTTPStatus

# queue for passing test status from post request to get request
TEST_STATUS = queue.Queue()
LOGGER = logging.getLogger(__name__)
healthcheck = Blueprint("healthcheck", __name__, template_folder="templates", static_folder="static")


def days_hours_minutes(td):
    return td.days, td.seconds//3600, (td.seconds//60)%60


@healthcheck.route("/")
def status():
    """
    This is a fairly messy method and it probably needs refactoring. Essentially what it should do,
    as confirmed by tests in ../tests/test_flask_page.py, is:
    1. Get the messages from the test status queue
    3. Put it into a dictionary. Overwrites naturally occur for later events.
    3. Put the statuses we selected onto the test status queue for the next GET, which should now be empty.
    4. Return the template with the dictionary of statuses, ordered by time.

    Returns: a http response with the list of tests in a nicely formatted Jinja2 template.

    """
    time_to_report = float(os.environ.setdefault(TIME_TO_REPORT_PARAMETER, "20"))
    status = {}
    while True:
        try:
            result = TEST_STATUS.get(block=False)
            status[result.namespace + result.name] = result
        except queue.Empty:
            break
    errors = []
    ordered = OrderedDict(sorted(status.items(), key=lambda x: x[1].time, reverse=True))
    if len(ordered) > 0:
        latest = list(ordered.items())[0][1].time
        now = datetime.now()
        delta = now - latest
        days, hours, minutes = days_hours_minutes(delta)
        minutes_since_test = delta.seconds / 60
        if minutes_since_test >= time_to_report:
            errors.append("ERROR! No test data for %i days %i hours and %i minutes" % (days, hours, minutes))
            LOGGER.error(errors[-1])
    for elem, value in status.items():
        TEST_STATUS.put(value)

    return render_template('index.html', results=ordered, errors=errors)

@healthcheck.route("/update", methods=['POST'])
def update():
    """
    Post endpoint for test containers to send their updates into.
    
    Returns: dictionary describing what happened followed by HTTP status code

    """
    data = request.get_json()
    required_fields = ["name", "passing", "info", "namespace", "time"]
    missing = [field for field in required_fields if field not in data]
    result = {"result": "event put onto queue"}
    http_status = HTTPStatus.OK

    if len(missing) == 0:
        event = StatusEvent(data['name'], data['passing'], data['namespace'], data['info'], data['time'])
        TEST_STATUS.put(event)

    else:
        result["result"] = "Event object invalid: keys missing - {}".format(", ".join(missing))
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
    return jsonify(result), http_status
