import logging
import requests

from http import HTTPStatus
from urllib3.exceptions import MaxRetryError
from kubee2etests.apimixin import ApiMixin
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ACTION_METRIC_NAME, add_error
from kubernetes.client.rest import ApiException


LOGGER = logging.getLogger(__name__)


class Pod(ApiMixin):
    def __init__(self, name, namespace):
        super().__init__(namespace)
        self.name = name
        self._k8s_object = None

    @property
    def log(self):
        loglines = []
        try:
            logs = self.api.read_namespaced_pod_log(self.name, self.namespace)
            loglines.extend(logs.split('\n'))
        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            msg = "Reading pod log threw ApiException, code: %s msg: %s"
            parameters = error_code.name.lower(), error_dict['message']
            LOGGER.error(msg, *parameters)
            add_error(self,(msg % parameters))
            self.incr_error_metric(error_code.name.lower())
        return loglines

    @property
    def node(self):
        if self._k8s_object is None:
            self._read_from_k8s()
        if len(self.errors) == 0:
            return self._k8s_object.spec.node_name

    @property
    def phase(self):
        if self._k8s_object is None:
            self._read_from_k8s()

        return self._k8s_object.status.phase

    def _read_from_k8s(self, should_exist=True):
        try:
            self._k8s_object = self.api.read_namespaced_pod(self.name, self.namespace)
        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)

            if error_code == HTTPStatus.NOT_FOUND:
                self.on_api = False
                if should_exist:
                    LOGGER.error("Pod %s does not exist", self.name)
                    add_error(self,"Does not exist")
                    self.incr_error_metric(error_code.name.lower())
                else:
                    LOGGER.info("Pod %s deleted", self.name)
            else:
                msg = "Error reading pod %s, code: %s msg: %s"
                parameters = self.name, error_code.name.lower(), error_dict['message']
                LOGGER.error(msg, *parameters)
                add_error(self,(msg % parameters))
                self.incr_error_metric(error_code.name.lower())

        else:
            self.on_api = True
            if not should_exist:
                msg = "pod %s still exists, phase: %s"
                parameters = self.name, self._k8s_object.status.phase
                LOGGER.error(msg, *parameters)
                add_error(self,(msg % parameters))
                self.incr_error_metric("not_deleted", area="k8s")

    @property
    def data_center(self):
        data_centre = None
        if self.node is None:
            add_error(self,"Pod %s has no node" % self.name)
            return None
        try:
            node = self.api.read_node(self.node)
            data_centre = node.metadata.labels.get(e2e_globals.ANTI_AFFINITY_KEY)
            if data_centre is None:
                msg = "Node: %s containing pod: %s has no data centre label."
                parameters = self.node, self.name
                LOGGER.error(msg, *parameters)
                self.incr_error_metric("no_zone_label_on_node", area="k8s")
                add_error(self,(msg % parameters))

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            msg = "Error reading node %s, code: %s"
            parameters = error_code, self.name
            LOGGER.error(msg, *parameters)
            LOGGER.error("Error msg: %s", error_dict['message'])
            self.incr_error_metric(error_code.name.lower())
            add_error(self,(msg % parameters))

        except MaxRetryError:
            LOGGER.error("Max retries exceeded when trying to list nodes")
            self.incr_error_metric("max_retries_exceeded")
            add_error(self,"max retries exceeded when trying to list nodes")

        return data_centre

    def make_http_request(self):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("http_get")):
            response = None
            if self._k8s_object is None:
                self._read_from_k8s()
            else:
                url = "http://{}:{}".format(self._k8s_object.status.pod_ip,
                                        self._k8s_object.spec.containers[0].ports[0].container_port)
                try:
                    response = requests.get(url, headers=e2e_globals.TEST_REQUEST_HEADERS)
                    self.incr_http_count_metric(str(response.status_code))

                except requests.HTTPError as e:
                    LOGGER.error("Pod %s at address: %s GET request failed: %s", self.name, url, e)
                    self.incr_http_count_metric(str(response.status_code))
                    add_error(self,"HTTP error code %i" % response.status_code)

                except requests.ConnectionError as e:
                    LOGGER.error("Pod %s at address: %s GET request failed: %s", self.name, url, e)
                    self.incr_http_count_metric("connection_error")
                    add_error(self,"Pod %s at address: %s gave connection error" % (self.name, url))

            return response
