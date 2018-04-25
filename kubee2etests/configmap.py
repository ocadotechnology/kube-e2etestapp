import logging
import sys



from kubernetes import client
from kubernetes.client.rest import ApiException
from http import HTTPStatus
from urllib3.exceptions import MaxRetryError
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ACTION_METRIC_NAME
from kubee2etests.apimixin import ApiMixin


LOGGER = logging.getLogger(__name__)


class ConfigMap(ApiMixin):
    def __init__(self, name=e2e_globals.TEST_INDEX_NAME,
                 index=e2e_globals.TEST_DEPLOYMENT_INDEX,
                 namespace=e2e_globals.TEST_NAMESPACE,
                 **kwargs):
        super().__init__(namespace=namespace)
        self.name = name
        self.index = index

    @property
    def k8s_object(self):
        return client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=self.name),
            data={'index.html': self.index}
        )

    def create(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("create")):
            try:
                self.api.create_namespaced_config_map(self.namespace, self.k8s_object)
                self.on_api = True

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])
                if error_code == HTTPStatus.CONFLICT:
                    LOGGER.warning("ConfigMap already created, continuing")

                elif error_code == HTTPStatus.NOT_FOUND:
                    not_found_msg = "namespaces \"{}\" not found".format(self.namespace)
                    if not_found_msg in error_dict['message']:
                        LOGGER.error("Namespace %s has disappeared, quitting", self.namespace)
                        sys.exit(error_dict['message'])
                else:
                    LOGGER.error("Error making configmap %s: %s", error_code, error_dict['message'])

            except MaxRetryError:
                msg = "Error creating config map %s, max retries exceeded"
                LOGGER.error(msg, self.name)
                self.incr_error_metric("max_retries_exceeded")
                self.add_error(msg % self.name)

            else:
                self.wait_on_event(self.api.list_namespaced_config_map, e2e_globals.EventType.ADDED,
                                   args=(self.namespace,))

        super().create(report)

    def _read_from_k8s(self, should_exist=True):
        try:
            self.api.read_namespaced_config_map(self.name, self.namespace)
            self.on_api = True

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            params = self.name, self.namespace
            if error_code == HTTPStatus.NOT_FOUND:
                if should_exist:
                    LOGGER.error("Config map %s not in namespace %s",
                                 *params)
                    self.add_error("Cfg map not found")
                    self.incr_error_metric("not_found", area="k8s")
                self.on_api = False
            else:
                LOGGER.error("ApiException reading Cfg map %s - %s; msg: %s",
                             self.name, error_code.name.lower(), error_dict['message'])
                self.add_error(error_dict['message'])
                self.incr_error_metric(error_code.name.lower())

        except MaxRetryError:
            LOGGER.error("MaxRetryError reading cfg map %s", self.name)
            self.add_error("MaxRetryError")
            self.incr_error_metric("max_retries_exceeded")

        else:
            if not should_exist:
                LOGGER.error("Cfgmap %s still in namespace %s", self.name, self.namespace)
                self.add_error("Cfg map still exists")
                self.incr_error_metric("still_exists", area="k8s")

    def delete(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("delete")):
            try:
                self.api.delete_namespaced_config_map(self.name, self.namespace, client.V1DeleteOptions())
                self.on_api = False

            except ApiException as e:
                msg = "Error deleting config map %s - %s:%s"
                error_code, error_dict = self.parse_error(e.body)
                parameters = self.name, error_code, error_dict['message']
                LOGGER.error(msg, *parameters)
                self.add_error(msg % parameters)
                self.incr_error_metric(error_code.name.lower())

            else:
                self.wait_on_deleted(report=False)

        super().delete(report)
