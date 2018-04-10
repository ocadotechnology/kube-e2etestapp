from kubernetes import client, watch
import json
import requests
import os
import logging
from http import HTTPStatus
from urllib3.exceptions import ReadTimeoutError
import copy
import time
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ERROR_METRIC_NAME, HTTP_COUNT_METRIC_NAME

LOGGER = logging.getLogger(__name__)


class ApiMixin(object):
    """
    Class which loosely wraps around a kubernetes client object to standardise some useful methods/avoid recurringly
    needing to update metrics and the frontend status page in multiple places.
    """
    def __init__(self, namespace):
        self.namespace = namespace
        self.api = client.CoreV1Api()
        # this will be filled with tuples containing (<error-msg>, <number-of-occurrences>
        self.errors = []
        self.on_api = False
        self.metric_data = {"resource": self.__class__.__name__,
                            "namespace": self.namespace
                            }

    @property
    def results(self):
        passed = len(self.errors) == 0
        error_msgs = copy.deepcopy(self.errors)
        self.errors = []
        return passed, error_msgs

    def add_error(self, err):
        error_list = [error[0] for error in self.errors]
        try:
            idx = error_list.index(err)
            self.errors[idx] = (err, self.errors[idx][1] + 1)
        except ValueError:
            self.errors.append((err, 1))

    def incr_error_metric(self, error, area="api", resource=None):
        """
        Helper method which takes in specific info about the data and
        combines it with data about the class, then increases the statsd
        metric

        Args:
            error: string representing what happened
            area: string representing which part of the test the error occurred - should be one of:
                - api (default)
                - k8s
                - timeout
                see troubleshooting.md for more explanation of which one you might need to use.
            resource: name of the resource being tested or being affected by the error. Default None
                uses the classname

        Returns: None, increments the statsd error metric
        """
        error_data = {"area": area, "error": error}
        error_data.update(self.metric_data)
        if resource is not None:
            error_data["resource"] = resource
        STATSD_CLIENT.incr(ERROR_METRIC_NAME % error_data)

    def incr_http_count_metric(self, result, resource=None):
        """
        Helper method which increments the http request count metric.

        Args:
            result: string of what happened - generally the HTTP status code
            resource: resource name, defaults to the class name

        Returns: None, increments the statsd http count metric

        """
        result_data = {"result": result}
        result_data.update(self.metric_data)
        if resource is not None:
            result_data["resource"] = resource
        STATSD_CLIENT.incr(HTTP_COUNT_METRIC_NAME % result_data)

    def action_data(self, action, resource=None):
        """
        Helper method to get the data about the action happening. Mostly,
        this avoids having "namespace" blah all over the place/doing dictionary
        updates/keeps metric data immutable.

        Args:
            action: action you are using
            resource: resource name

        Returns: Dictionary of labels to apply to statsd action metric

        """
        action_data = {"action": action}
        action_data.update(self.metric_data)
        if resource is not None:
            action_data["resource"] = resource
        return action_data

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

    def flush_errors(self):
        self.errors = []

    def parse_error(self, error_body):
        try:
            json_error = json.loads(error_body)
            code = HTTPStatus(int(json_error['code']))
            return code, json_error

        except json.decoder.JSONDecodeError as e:
            LOGGER.error("Decoder exception loading error msg: %s;"
                         "%s", error_body, str(e))
            return HTTPStatus(500), {"message": error_body}

    def exists(self, report=True):
        self._read_from_k8s()
        if report:
            self.send_update("Check %s exists" % self.__class__.__name__)
        return self.on_api

    def deleted(self, report=True):
        self._read_from_k8s(should_exist=False)
        if report:
            self.send_update("Check %s deleted" % self.__class__.__name__)
        return not self.on_api

    def _read_from_k8s(self, should_exist=True):
        LOGGER.warning("WARNING: no read_from_k8s method for class %s" % self.__class__.__name__)
        self.add_error("No read method for k8s")

    def create(self, report=True):
        if report:
            self.send_update("Create %s" % self.__class__.__name__)

    def delete(self, report=True):
        if report:
            self.send_update("Delete %s" % self.__class__.__name__)

    def wait_on_deleted(self, report=False):
        """
        method which returns when deleted is true. Used for
        deletions which happen too quick for us to track events

        Args:
            report: boolean, whether to report status to flask endpoint

        Returns: None

        """
        while not self.deleted(report=report):
            time.sleep(1)

    def create_if_not_exists(self, report=False):
        exists = self.exists(report)
        if not exists:
            self.create(report)

    def wait_on_event(self, method, event_type_enum, count=1, args=()):
        """
        Wrapper around the watcher object which does exception handling and tracks errors waiting on object events to change

        Args:
            method: (method) kubernetes client method to wait on
            event_type_enum: (EventType) enum from `helpers_and_globals` representing what object change to wait for
            count: (int) number of events to wait on
            args: (tuple) arguments which are needed by `method`

        Returns: (list) list of objects which were modified, added or removed in the stream.

        """
        event_type = event_type_enum.value
        resource = self.__class__.__name__
        watcher = watch.Watch()
        total = 0
        objects = []
        try:
            for event in watcher.stream(method, *args, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS):
                LOGGER.debug("Event: %s %s" % (event['type'], event['object'].metadata.name))
                if event['object'].metadata.name == self.name and event['type'] == event_type:
                    LOGGER.info("%s %s %s", resource, event['object'].metadata.name, event_type)
                    total += 1
                    objects.append(event['object'])
                    if total >= count:
                        watcher.stop()

        except ReadTimeoutError as e:
            LOGGER.error("%s event list read timed out, could not track events", resource)
            self.incr_error_metric("events", area="timeout")
            self.add_error("%s event list stream timed out" % resource)
            LOGGER.debug(e)
            LOGGER.debug(objects)
        return objects

    def send_update(self, name):
        """
        Method which will send an update on the current test to the flask frontend. If not running, will log it and carry on

        Args:
            name: (str) name of the test being ran

        Returns: (Response) requests response from the action.

        """
        namespace = os.environ.get("TEST_NAMESPACE", e2e_globals.TEST_NAMESPACE)
        passing, msgs = self.results
        event = e2e_globals.StatusEvent(name, passing, namespace, msgs)
        try:
            response = requests.post("http://localhost:{}/update".format(e2e_globals.FLASK_PORT), json=event.event_data)
            return response
        except Exception as e:
            LOGGER.error("Flask endpoint not available, continuing")
            LOGGER.debug("Exception: %s", str(e))
