import logging
import requests

from http import HTTPStatus
from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from kubee2etests.apimixin import ApiMixin
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ACTION_METRIC_NAME


LOGGER = logging.getLogger(__name__)


class Service(ApiMixin):
    def __init__(self, service, subsets, addresses, namespace, **kwargs):
        super().__init__(namespace)
        self.name = service
        self.subsets = subsets
        self.addresses = addresses
        self.create_metric_name = e2e_globals.PROMETHEUS_PREFIX + 'create_service_seconds'

    @property
    def k8s_object(self):
        return client.V1Service(metadata=client.V1ObjectMeta(name=self.name,
                                               namespace=self.namespace),
                                spec=client.V1ServiceSpec(ports=[
                                    client.V1ServicePort(port=10, target_port=e2e_globals.TEST_CONTAINER_PORT),
                                ],
                                    selector=e2e_globals.TEST_TEMPLATE_LABELS)
                                )

    def _read_from_k8s(self, should_exist=True):
        try:
            self.api.read_namespaced_service(self.name, self.namespace, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
            LOGGER.info("Service %s exists in namespace %s", self.name, self.namespace)
            self.on_api = True

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)

            msg = "Error: %s message: %s"
            parameters = error_code, error_dict['message']
            if error_code == HTTPStatus.NOT_FOUND:
                if should_exist:
                    LOGGER.error(msg, *parameters)
                    self.add_error(msg % parameters)
                    self.incr_error_metric(error_code.name.lower())
                self.on_api = False
            else:
                LOGGER.error(msg, *parameters)
                self.add_error(msg % parameters)
                self.incr_error_metric(error_code.name.lower())

        except MaxRetryError:
            LOGGER.error("Max retries exceeded when trying check service exists")
            self.incr_error_metric("max_retries_exceeded")
            self.add_error("max retries exceeded")

        else:
            if not should_exist:
                self.incr_error_metric("not_deleted", area="k8s")

    def create(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("create")):
            try:
                returned_service = self.api.create_namespaced_service(self.namespace, self.k8s_object)
                LOGGER.debug(returned_service)
                LOGGER.info("Service being created")
                self.wait_on_event(self.api.list_namespaced_service, e2e_globals.EventType.ADDED, args=(self.namespace,))

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                if error_code == HTTPStatus.UNPROCESSABLE_ENTITY:
                    LOGGER.error("Service object not valid - %s", error_dict['message'])
                if error_code == HTTPStatus.CONFLICT:
                    LOGGER.error("Service %s already exists in namespace %s", self.name, self.namespace)

                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])
                LOGGER.debug(error_dict)

            except MaxRetryError:
                LOGGER.error("Max retries exceeded when trying to create service")
                self.incr_error_metric("max_retries_exceeded")
                self.add_error("Max retries exceeded")

        super().create(report)

    def delete(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("delete")):
            try:
                LOGGER.info("Deleting Service %s from Namespace %s", self.name, self.namespace)
                self.api.delete_namespaced_service(self.name, self.namespace, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)


            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                self.incr_error_metric(error_code.name.lower())
                LOGGER.error("Error deleting service %s from namespace %s", self.name, self.namespace)
                LOGGER.error("Error code: %s", error_code)
                LOGGER.error("Error msg: %s", error_dict['message'])
                LOGGER.debug("Error dict: %s", error_dict)
                self.add_error(error_dict['message'])

            except MaxRetryError:
                LOGGER.error("Max retries exceeded when trying to delete service")
                self.incr_error_metric("max_retries_exceeded")
                self.add_error("max retries exceeded")

            else:
                self.wait_on_deleted()

        super().delete(report)

    def watch_endpoints_till_correct(self, exp_subsets=1):
        """
        Method to wait for endpoints to be created/modified and track how many
        subsets/addresses the selected endpoint contains. When the expected number is matched
        the method ends.

        Args:
            endpoint (str): Name of the service for which the endpoint should exist
            exp_subsets (int): number of subsets of endpoints which should exist
            exp_addresses (int): number of addresses which should exist
            namespace (str): namespace to test
            postfix (str): text to add to the test name to differentiate between multiple uses of this method

        Returns: None

        """
        watcher = watch.Watch()
        subsets = 0
        addresses = 0
        try:
            for event in watcher.stream(self.api.list_namespaced_endpoints, self.namespace,
                                        _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS):
                body = event['object']
                name = body.metadata.name
                LOGGER.debug("Event: %s %s", event['type'], name)
                if name == self.name:
                    subsets = len(body.subsets)
                    if subsets > 0:
                        for subset in body.subsets:
                            if subset.addresses is not None:
                                addresses += len(subset.addresses)

                    if subsets == exp_subsets:
                        if addresses == self.addresses:
                            watcher.stop()

        except ReadTimeoutError as e:
            LOGGER.error("Endpoint event list read timed out, could not track events")
            LOGGER.debug(e)
            self.incr_error_metric("waiting_on_endpoints", area="timeout")
            self.add_error("Event list timed out")

        LOGGER.info("Endpoint for service: %s containing %s subsets containing %s addresses found",
                    self.name, subsets, addresses)
        if subsets == self.subsets:
            if addresses != self.addresses:
                self.add_error("Addresses doesn't match expected - found %i, not %i" %
                                   (addresses, self.addresses))
                self.incr_error_metric("incorrect_endpoint_count", area="k8s")
        else:
            self.add_error("Subsets doesn't match expected - found %i, not %i" %
                               (subsets, self.subsets))

    def read_endpoints(self, report=True):
        subsets = 0
        addresses = 0

        try:
            endpoints = self.api.read_namespaced_endpoints(self.name, namespace=self.namespace)
            subsets = len(endpoints.subsets)
            if subsets > 0:
                for subset in endpoints.subsets:
                    if subset.addresses is not None:
                        addresses += len(subset.addresses)
        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            LOGGER.error("Endpoint could not be read, code: %s msg: %s", error_code.name.lower(), error_dict['message'])
            LOGGER.debug(e)
            self.incr_error_metric(error_code.name.lower())
            self.add_error("Endpoint read error: {}".format(error_dict['message']))

        if subsets == self.subsets:
            if addresses != self.addresses:
                self.add_error("Addresses doesn't match expected - found %i, not %i" %
                                   (addresses, self.addresses))
        else:
            self.add_error("Subsets doesn't match expected - found %i, not %i" %
                               (subsets, self.subsets))
            self.incr_error_metric("incorrect_endpoint_count", area="k8s")

        LOGGER.info("Endpoint with %i subsets and %i addresses found", subsets, addresses)
        if report:
            self.send_update("Read service endpoints")

    def make_http_request(self, hostname=False):
        response = None
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("http_get")):
            try:
                svc = self.api.read_namespaced_service(self.name, self.namespace, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
                if hostname:
                    ip = "{}.{}.svc.cluster.local".format(self.name, self.namespace)
                else:
                    ip = svc.spec.cluster_ip
                port = svc.spec.ports[0].port
                address = "http://{}:{}".format(ip, port)
                try:
                    response = requests.get(address, headers=e2e_globals.TEST_REQUEST_HEADERS)
                    LOGGER.info("Service %s at address: %s GET request response code: %s",
                                self.name, address, response.status_code)
                    LOGGER.debug(response)
                    self.incr_http_count_metric(str(response.status_code))


                except requests.HTTPError as e:
                    LOGGER.error("Service %s at address: %s GET request failed: %s", self.name, address, e)
                    self.incr_http_count_metric(str(response.status_code))
                    self.add_error("HTTP error code %i" % response.status_code)

                except requests.ConnectionError as e:
                    LOGGER.error("Service %s at address: %s GET request failed: %s", self.name, address, e)
                    self.incr_http_count_metric("connection_error")
                    self.add_error("Service %s at address: %s gave connection error" % (self.name, address))

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                LOGGER.error("Error reading namespaced service in http service request test. Code: %s msg: %s",
                             error_code.name.lower(), error_dict['message'])
                self.add_error(error_dict['message'])
                self.incr_error_metric(error_code.name.lower())

        return response

    def request_n_times(self, n, expected_text, report=True, hostname=False):
        for i in range(n):
            response = self.make_http_request(hostname=hostname)
            if response is not None:
                if response.text != expected_text:
                    self.add_error("Response text did not match expected - request %i" % i)
                    self.incr_http_count_metric("wrong_response")

        if report:
            msg = "Request service by %s %i times"
            if hostname:
                form = "hostname"
            else:
                form = "ip"
            self.send_update(msg % (form, n))
