import logging
import requests
import os
import copy
from kubee2etests.helpers_and_globals import TEST_NAMESPACE, FLASK_PORT, StatusEvent

LOGGER = logging.getLogger(__name__)

class StatusSender(object):
    def __init__(self):
        self.errors = []

    @property
    def results(self):
        passed = len(self.errors) == 0
        error_msgs = copy.deepcopy(self.errors)
        self.errors = []
        return passed, error_msgs

    def flush_errors(self):
        self.errors = []

    def add_error(self, err):
        error_list = [error[0] for error in self.errors]
        try:
            idx = error_list.index(err)
            self.errors[idx] = (err, self.errors[idx][1] + 1)
        except ValueError:
            self.errors.append((err, 1))

    def add_errors(self, errors):
        """
        Method which adds errors to the object's error list - this allows us to batch send them
        when a status update is needed. It also does deduping of errors which have come up twice
        since the last status was sent to the frontend.

        Args:
            errors: (list) list of tuples to add to the error list - first entry being the error, second being the number of occurences

        Returns: None, as a side effect will update `self.errors`

        """
        error_list = [error[0] for error in self.errors]
        for err in errors:
            try:
                idx = error_list.index(err[0])
                self.errors[idx] = (err, self.errors[idx][1] + err[1])
            except ValueError:
                self.errors.append(err)

    def send_update(self, name):
        """
        Method which will send an update on the current test to the flask frontend. If not running, will log it and carry on

        Args:
            name: (str) name of the test being ran

        Returns: (Response) requests response from the action.

        """
        namespace = os.environ.get("TEST_NAMESPACE", TEST_NAMESPACE)
        passing, msgs = self.results
        event = StatusEvent(name, passing, namespace, msgs)
        try:
            response = requests.post("http://localhost:{}/update".format(FLASK_PORT), json=event.event_data)
            return response
        except Exception as e:
            LOGGER.error("Flask endpoint not available, continuing")
            LOGGER.debug("Exception: %s", str(e))
