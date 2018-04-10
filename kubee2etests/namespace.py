from kubee2etests.apimixin import ApiMixin
from kubernetes import client
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ACTION_METRIC_NAME
import logging
from http import HTTPStatus


LOGGER = logging.getLogger(__name__)

class Namespace(ApiMixin):
    def __init__(self, namespace):
        super().__init__(namespace)
        self.name = namespace

    @property
    def k8s_object(self):
        return client.V1Namespace(metadata=client.V1ObjectMeta(name=self.name))

    def create(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("create")):
            try:
                self.api.create_namespace(self.k8s_object)
                self.on_api = True

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                LOGGER.error(error_dict['message'])
                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])

            except MaxRetryError:
                LOGGER.error("Maximum number of retries exceeded")
                self.incr_error_metric("max_retries_exceeded")
                self.add_error("max retries exceeded")

            else:
                self.wait_on_event(self.api.list_namespace, e2e_globals.EventType.ADDED)

        super().create(report)

    def empty(self, report=True):
        extended_api = client.ExtensionsV1beta1Api()
        resources = dict()
        resource_name = "deployments"
        try:
            resources[resource_name] = extended_api.list_namespaced_deployment(self.name,
                                                                               _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
            resource_name = 'services'
            resources[resource_name] = self.api.list_namespaced_service(self.name,
                                                                   _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
            resource_name = 'pods'
            resources[resource_name] = self.api.list_namespaced_pod(self.name, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
            resource_name = 'endpoints'
            resources[resource_name] = self.api.list_namespaced_endpoints(self.name,
                                                                     _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)

        except MaxRetryError:
            msg = "Maximum number of retries exceeded when reading %s"
            LOGGER.error(msg, resource_name)
            self.incr_error_metric("max_retries_exceeded")
            self.add_error(msg % resource_name)

        log_msg = "Namespace %s contains %s %s"
        result_msg = ""
        empty = True
        for key in resources:
            LOGGER.debug(log_msg, self.name, len(resources[key].items), key)
            if len(resources[key].items) > 0:
                empty = False
                result_msg += log_msg % (self.name, len(resources[key].items), key)

        if not empty:
            LOGGER.error("Namespace %s is not empty", self.name)
            self.incr_error_metric("not_empty", area="k8s")
            self.add_error(result_msg)

        else:
            LOGGER.info("Namespace %s is empty", self.name)

        if report:
            self.send_update("Check namespace empty")

        return empty

    def delete(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("delete")):
            body = client.V1DeleteOptions()
            try:
                self.api.delete_namespace(self.name, body, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
                LOGGER.info("Namespace being deleted")

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                LOGGER.debug(error_code)
                LOGGER.debug(error_dict)
                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])

            except MaxRetryError:
                self.incr_error_metric("api", "max_retries_exceeded")
                LOGGER.error("Max retries exceeded when deleting a namespace")
                self.add_error("max retries exceeded")

            else:
                self.wait_on_event(self.api.list_namespace, e2e_globals.EventType.DELETED)


        super().delete(report)

    def _read_from_k8s(self, should_exist=True):
        try:
            namespace = self.api.read_namespace(self.name, _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS)
            LOGGER.info("Namespace %s exists", self.name)
            LOGGER.debug(namespace)
            self.on_api = True

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            if error_code == HTTPStatus.NOT_FOUND:
                if should_exist:
                    LOGGER.error("Namespace %s not created", self.name)
                    self.add_error("Namespace not created")
                self.on_api = False
            else:
                self.add_error(error_dict['message'])
            LOGGER.debug("Error code: %s error dict: %s", error_code, error_dict)
            self.incr_error_metric(error_code.name.lower())

        except MaxRetryError:
            LOGGER.error("Maximum number of retries exceeded")
            self.incr_error_metric("api", "max_retries_exceeded")
            self.add_error("max retries exceeded")

        else:
            if not should_exist:
                msg = "Namespace %s still exists"
                parameters = self.name
                LOGGER.error(msg, parameters)
                self.add_error(msg % parameters)
                self.incr_error_metric("not_deleted", area="k8s")
