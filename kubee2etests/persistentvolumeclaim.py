from kubernetes import client
from kubernetes.client.rest import ApiException
import logging

from http import HTTPStatus
from urllib3.exceptions import MaxRetryError

from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT
from kubee2etests.apimixin import ApiMixin



LOGGER = logging.getLogger(__name__)


class PersistentVolumeClaim(ApiMixin):
    def __init__(self, name=e2e_globals.TEST_VOLUME_CLAIM_NAME,
                 namespace=e2e_globals.TEST_NAMESPACE,
                 storage="1Gi"):
        super().__init__(namespace)
        self.name = name
        self.storage = storage

    @property
    def k8s_object(self):
        return client.V1PersistentVolumeClaim(spec=client.V1PersistentVolumeClaimSpec(
            access_modes=[
                "ReadWriteOnce"
            ],
            resources=client.V1ResourceRequirements(
                requests={
                    "storage": self.storage
                }
            )
        ),
            metadata=client.V1ObjectMeta(name=self.name,
                                         namespace=self.namespace))

    def create(self, report=True):
        with STATSD_CLIENT.timer(e2e_globals.ACTION_METRIC_NAME % self.action_data("create")):
            try:
                self.api.create_namespaced_persistent_volume_claim(self.namespace, self.k8s_object)

            except ApiException as e:
                msg = "Error creating volume claim %s, API exception: %s msg: %s"
                error_code, error_dict = self.parse_error(e.body)
                LOGGER.error(msg, self.name, error_code.name.lower(), error_dict['message'])
                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])

            else:
                self.wait_on_event(self.api.list_namespaced_persistent_volume_claim, e2e_globals.EventType.ADDED,
                                   args=(self.namespace,))
                self.on_api = True

        super().create(report)

    def delete(self, report=True):
        with STATSD_CLIENT.timer(e2e_globals.ACTION_METRIC_NAME % self.action_data("delete")):
            try:
                self.api.delete_namespaced_persistent_volume_claim(self.name, self.namespace, client.V1DeleteOptions())

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                LOGGER.error("Error deleting volume claim %s, API exception: %s msg: %s",
                             self.name, error_code.name.lower(), error_dict['message'])
                self.add_error(error_dict['message'])
                self.incr_error_metric(error_code.name.lower())

            else:
                self.wait_on_deleted(report)

        super().delete(report)

    def _read_from_k8s(self, should_exist=True):
        try:
            self.api.read_namespaced_persistent_volume_claim(self.name, self.namespace)
            self.on_api = True

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            params = self.name, self.namespace
            if error_code == HTTPStatus.NOT_FOUND:
                if should_exist:
                    LOGGER.error("vol claim %s not in namespace %s",
                                 *params)
                    self.add_error("vol claim not found")
                    self.incr_error_metric(error_code.name.lower())
                self.on_api = False
            else:
                LOGGER.error("ApiException reading vol claim %s - %s; msg: %s",
                             self.name, error_code.name.lower(), error_dict['message'])
                self.add_error(error_dict['message'])
                self.incr_error_metric(error_code.name.lower())

        except MaxRetryError:
            LOGGER.error("MaxRetryError reading vol claim %s", self.name)
            self.add_error("MaxRetryError")
            self.incr_error_metric("max_retries_exceeded")

        else:
            if not should_exist:
                LOGGER.error("vol claim %s still in namespace %s", self.name, self.namespace)
                self.add_error("vol claim still exists")
                self.incr_error_metric("not_deleted", area="k8s")
