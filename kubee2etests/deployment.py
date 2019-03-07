import collections
from kubernetes import client, watch
from kubernetes.client.rest import ApiException
from urllib3.exceptions import MaxRetryError, ReadTimeoutError
from http import HTTPStatus
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, ACTION_METRIC_NAME
from kubee2etests.apimixin import ApiMixin
import logging
from kubee2etests import Pod


LOGGER = logging.getLogger(__name__)


class Deployment(ApiMixin):
    def __init__(self, name, namespace, replicas=e2e_globals.TEST_REPLICAS,
                 cfgmap_name=e2e_globals.TEST_INDEX_NAME,
                 labels=e2e_globals.TEST_LABELS,
                 template_labels=e2e_globals.TEST_TEMPLATE_LABELS,
                 vol_claim=None):
        super().__init__(namespace=namespace)
        self.name = name
        self.replicas = replicas
        self.cfgmap_name = cfgmap_name
        self.labels = labels
        self.template_labels = template_labels
        self.vol_claim_name = vol_claim
        # Api used for deployment methods. Core api used for any pod methods
        self.extensions_api = client.ExtensionsV1beta1Api()
        self.pods = collections.defaultdict(list)
        self.old_pods = {}
        self.pod_requests = 0

    @property
    def label_selector(self):
        return ",".join(["%s=%s" % (key, value) for key, value in self.template_labels.items()])

    @property
    def k8s_object(self):
        depl = client.AppsV1beta1Deployment(
            metadata=client.V1ObjectMeta(
                name=self.name,
                labels=self.labels
            ),
            spec=client.AppsV1beta1DeploymentSpec(
                strategy=client.AppsV1beta1DeploymentStrategy(
                    type='RollingUpdate',
                    rolling_update=client.AppsV1beta1RollingUpdateDeployment(
                        max_surge=0
                    )
                ),
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(
                        labels=self.template_labels),
                    spec=client.V1PodSpec(
                        affinity=client.V1Affinity(
                            pod_anti_affinity=client.V1PodAntiAffinity(
                                required_during_scheduling_ignored_during_execution=[
                                    {"topologyKey": e2e_globals.ANTI_AFFINITY_KEY},
                                ]
                            ),
                        ),
                        volumes=[client.V1Volume(
                            name='data',
                            config_map=client.V1ConfigMapVolumeSource(
                                name=self.cfgmap_name)
                        )]
                        ,
                        containers=[client.V1Container(
                            image=e2e_globals.TEST_DEPLOYMENT_IMAGE,
                            name="testapp",
                            volume_mounts=[client.V1VolumeMount(
                                name='data',
                                mount_path='/usr/share/nginx/html')
                            ],
                            ports=[client.V1ContainerPort(
                                container_port=e2e_globals.TEST_CONTAINER_PORT)],
                            resources=client.V1ResourceRequirements(
                                requests={
                                    'cpu': '1m',
                                    'memory': '1Mi',
                                },
                            ),
                        )])),
                replicas=self.replicas)
        )
        if self.vol_claim_name is not None:
            volume = client.V1Volume(name='test-volume',
                                     persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                         claim_name=self.vol_claim_name))
            mount = client.V1VolumeMount(
                name='test-volume',
                mount_path='/usr/blank'
            )
            depl.spec.template.spec.containers[0].volume_mounts.append(mount)
            depl.spec.template.spec.volumes.append(volume)
        return depl


    def create(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("create")):
            try:
                self.extensions_api.create_namespaced_deployment(self.namespace, self.k8s_object)
                self.on_api = True

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                self.incr_error_metric(error_code.name.lower())
                self.add_error(error_dict['message'])
                if error_code == HTTPStatus.CONFLICT:
                    LOGGER.warning("Deployment already exists, continuing")
                    LOGGER.debug("Error msg: %s", error_dict['message'])

                elif error_code == HTTPStatus.FORBIDDEN:
                    LOGGER.error("Deployment creation forbidden - %s", error_dict['message'])

            except MaxRetryError:
                msg = "Error creating deployment %s, max retries exceeded"
                self.add_error("max retries exceeded")
                LOGGER.error(msg, self.name)
                self.incr_error_metric("max_retries_exceeded")

            else:
                self.wait_on_event(self.extensions_api.list_namespaced_deployment, e2e_globals.EventType.ADDED,
                                   args=(self.namespace,))

        super().create(report)

    def _read_from_k8s(self, should_exist=True):
        created_deployment = None
        try:
            self.extensions_api.read_namespaced_deployment(self.name, self.namespace)
            self.on_api = True
        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            LOGGER.debug(e)
            if error_code == HTTPStatus.NOT_FOUND:
                if should_exist:
                    LOGGER.error("deployment %s not found in namespace %s", self.name,self.namespace)
                    self.add_error("ERR %s: %s" % (error_code.name.lower(), error_dict['message']))
                    self.incr_error_metric(error_code.name.lower())
                self.on_api = False
            else:
                self.add_error("ERR %s: %s" % (error_code.name.lower(), error_dict['message']))
                self.incr_error_metric(error_code.name.lower())
            LOGGER.debug("Error code: %s", error_code)
            LOGGER.debug("Error message: %s", error_dict['message'])

        except MaxRetryError:
            self.add_error("max retries exceeded reading deployment %s" % self.name)
            LOGGER.error("Error reading deployment %s, max retries exceeded", self.name)
            self.incr_error_metric("max_retries_exceeded")

        else:
            if not should_exist:
                msg = "deployment %s still in namespace %s"
                parameters = self.name, self.namespace
                LOGGER.error(msg, *parameters)
                self.add_error(msg % parameters)
                LOGGER.debug(created_deployment)
                self.incr_error_metric("not_deleted", area="k8s")

    def change_cfg_map(self, new_cfgmap_name, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("update")):
            self.cfgmap_name = new_cfgmap_name
            self._update_k8s()
        if report:
            self.send_update("Update deployment")

    def scale(self, replicas, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("scale")):
            self.replicas = replicas
            self._update_k8s()
        if report:
            self.send_update("Scale deployment to %i replicas" % replicas)

    def _update_k8s(self):
        try:
            self.extensions_api.replace_namespaced_deployment(self.name, self.namespace, self.k8s_object)
            LOGGER.info("Updated deployment %s image", self.name)
            self.pod_requests = 0

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            msg = "Error updating deployment %s, code: %s msg: %s"
            self.add_error(msg % (self.name, error_code.name.lower(), error_dict['message']))
            LOGGER.error("Error updating deployment %s", self.name)
            LOGGER.error("Code: %s msg: %s", error_code, error_dict['message'])
            LOGGER.debug("Error dict: %s", error_dict)
            self.incr_error_metric(error_code.name.lower())

        except MaxRetryError:
            msg = "Error updating deployment %s, max retries exceeded"
            self.add_error(msg % self.name)
            LOGGER.error(msg, self.name)
            self.incr_error_metric("max_retries_exceeded")

    def delete(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("delete")):
            body = client.V1DeleteOptions(propagation_policy="Background")
            try:
                self.extensions_api.delete_namespaced_deployment(self.name, self.namespace, body)

            except ApiException as e:
                error_code, error_dict = self.parse_error(e.body)
                msg = "Delete deployment %s from namespace %s failed, code: %s, msg: %s"
                parameters = self.name, self.namespace, error_code.name.lower(), error_dict['message']
                self.add_error(msg % parameters)
                LOGGER.error(msg, *parameters)
                self.incr_error_metric(error_code.name.lower())

            except MaxRetryError:
                msg = "Error deleting deployment %s from namespace %s, max retries exceeded"
                parameters = self.name, self.namespace
                self.add_error(msg % parameters)
                LOGGER.error(msg, *parameters)
                self.incr_error_metric("max_retries_exceeded")

            else:
                self.wait_on_deleted()

        super().delete(report)

    def read_pods(self, report=True):
        """
        Method which will read all pods associated with this namespace and selector,
        but will not watch or stream events. If the pod isn't in the list right now
        it won't count it.

        Returns: None, updates self.pods and self.old_pods

        """
        try:
            pods = self.api.list_namespaced_pod(self.namespace,
                                                label_selector=self.label_selector)
            self.pods = collections.defaultdict(list)
            for pod in pods.items:
                p = Pod(pod.metadata.name, self.namespace)
                self.pods[pod.status.phase].append(p)

        except ApiException as e:
            error_code, error_dict = self.parse_error(e.body)
            LOGGER.error("Reading pods threw an ApiException: %s, msg: %s",
                         error_code.name.lower(), error_dict['message'])
            self.add_error(error_dict['message'])
            self.incr_error_metric(error_code.name.lower())

        except MaxRetryError as e:
            LOGGER.error("Reading pods threw a MaxRetryError: %s",
                         e.reason)
            self.add_error(e.reason)
            self.incr_error_metric("max_retries_exceeded")

        if report:
            self.send_update("Read pods")

    def _wait_on_pods(self, phase="any", event_type_enum=e2e_globals.EventType.ALL):
        """
        Method to watch events stream about pods and count the number in the selected phase. Will
        stop watching when the count reaches self.replicas as this is how many pods we should have in
        the right phase. Non-terminating pods will be added to self.pods
        If a pod is terminating, it won't count that pod. Pod will be put on self.old_pods.
        Args:
            phase: string, default any means it will count pods in any phase excluding terminating.
            event_type_enum: Event type - default all means it will count pods going through any event.

        Returns: None, updates old_pods, pods and errors. May also increment statsd metrics.

        """
        event_type = event_type_enum.value
        watcher = watch.Watch()
        total = 0
        self.pods = collections.defaultdict(list)
        try:
            for event in watcher.stream(self.api.list_namespaced_pod, self.namespace, label_selector=self.label_selector,
                                        _request_timeout=e2e_globals.TEST_EVENT_TIMEOUTS):
                LOGGER.debug("Event: %s %s", event['type'], event['object'].metadata.name)
                pod_name = event['object'].metadata.name

                pod_phase = event['object'].status.phase
                pod_obj = Pod(pod_name, self.namespace)
                self.pods[pod_phase].append(pod_obj)
                if event_type in (event['type'], 'ALL'):
                    if pod_name not in self.old_pods and phase in (pod_phase, 'any'):
                        LOGGER.info("Pod %s scheduled, phase %s", pod_name, pod_phase)
                        total += 1
                        if total >= self.replicas:
                            watcher.stop()

            LOGGER.info("All pods in correct phase")

        except ReadTimeoutError as e:
            self.incr_error_metric("waiting_on_phase", area="timeout")
            LOGGER.error("Pod event list read timed out, could not track pod scheduling")
            LOGGER.debug(e)
            self.add_error("Pod event list timed out")

    def wait_on_pods_ready(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("run", resource="Pod")):
            self._wait_on_pods(phase="Running")
        if report:
            self.send_update("Wait on pods ready")

    def wait_on_pods_scheduled(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("schedule", resource="Pod")):
            self._wait_on_pods(phase="Pending")
        if report:
            self.send_update("Wait on pod scheduling")

    def check_pods_deleted(self, phase="any", report=True):
        deleted = True
        if phase == "any":
            to_delete_pods = []
            [to_delete_pods.extend(pods) for pods in self.pods.values()]
        else:
            to_delete_pods = self.pods[phase]
        for pod in to_delete_pods:
            deleted = deleted and pod.deleted()
            self.add_errors(pod.results[1])
        if report:
            self.send_update("Check pods are deleted")

    def watch_pod_scaling(self, report=True):
        with STATSD_CLIENT.timer(ACTION_METRIC_NAME % self.action_data("scale", resource="Pod")):
            self._wait_on_pods(event_type_enum=e2e_globals.EventType.DELETED)
        if report:
            self.send_update("Watch pod deletion")

    def check_pods_on_different_nodes(self, report=True):
        nodes = {}
        for pod in self.pods["Running"]:
            node = pod.node
            self.add_errors(pod.results[1])
            nodes.setdefault(node, []).append(pod.name)

        for node, pods in nodes.items():
            if len(pods) > 1:
                msg = "Pods %s are on the same node - %s"
                params = ",".join(nodes[node]), node
                self.add_error(msg % params)
                LOGGER.error(msg, *params)
                self.incr_error_metric("same_node", area="k8s", resource="Pod")

        if report:
            self.send_update("Check pods on different nodes")

    def check_pods_on_different_data_centres(self, report=True):
        dcs = {}
        for pod in self.pods["Running"]:
            dc = pod.data_center
            self.add_errors(pod.results[1])
            if dc is not None:
                dcs.setdefault(dc, []).append(pod.name)

        for dc, pods in dcs.items():
            if len(pods) > 1:
                msg = "Pods %s are in the same data centre - %s"
                params = ",".join(dcs[dc]), dc
                self.add_error(msg % params)
                LOGGER.error(msg, *params)
                self.incr_error_metric("same_data_centre", area="k8s", resource="Pod")

        if report:
            self.send_update("Check pods on different data centres")

    def http_request_all_pods(self, cfgmap_text, report=True):
        """
        Method to send a get request to each pod ip/port pair.
        Assumes pods have already been loaded - do read_pods or wait_on_pods_x
        to load them before calling this method.

        Args:
            cfgmap_text: (string) text from the config map linked to this deployment.

        Returns: None, updates pod_requests and errors. May also increment a statsd metric

        """
        for pod in self.pods["Running"]:
            response = pod.make_http_request()
            self.add_errors(pod.results[1])
            if response is not None:
                if response.text != cfgmap_text:
                    self.add_error("Response text does not match expected text")
                    msg = "Response from pod %s didn't match exp output"
                    parameters = pod.name
                    LOGGER.error(msg, *parameters)
                    LOGGER.debug("Expected: %s received: %s", cfgmap_text, response.text)
                    self.incr_http_count_metric("wrong_response", resource="Pod")
                else:
                    self.incr_http_count_metric("200", resource="Pod")

        self.pod_requests += 1
        if report:
            self.send_update("HTTP request each pod")

    def validate_pod_log(self, service_requests=1, user_agent=e2e_globals.TEST_USER_AGENT, report=True):
        """
        Method to validate the right number of lines containing the user agent
        exists in each pod's log
        Args:
            service_requests: integer, number of requests made to the service for this deployment
            user_agent: string, user agent each log line should contain

        Returns: None, updates errors and a statsd metric if anything goes wrong

        """
        total_lines = 0
        for pod in self.pods["Running"]:
            log = pod.log
            self.add_errors(pod.results[1])
            user_agent_lines = [line for line in log if not user_agent or user_agent in line]
            count = len(user_agent_lines)
            total_lines += count
            if count < self.pod_requests:
                self.add_error("Not enough lines of output containing user agent to meet pod request count")
                break

        if not total_lines == service_requests + self.pod_requests * len(self.pods):
            self.add_error("Not enough lines of output containing user agent to meet pod request count"
                               " and service request count")
            self.incr_error_metric("log_incorrect", area="k8s", resource="Pod")

        if report:
            self.send_update("Validate pod logs")
