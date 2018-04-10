from kubee2etests.runners.service_runners import ServiceWithDeploymentRunner
from kubee2etests import ConfigMap
from kubee2etests.helpers_and_globals import TEST_DEPLOYMENT_INDEX, TEST_DEPLOYMENT_INDEX_CHANGED, \
    TEST_REPLICAS, TEST_INDEX_NAME_CHANGED


class HttpRequestRunner(ServiceWithDeploymentRunner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.exp_text = TEST_DEPLOYMENT_INDEX
        self.service_requests = kwargs.get("service_requests", TEST_REPLICAS * 2)

    def run(self):
        self.service.request_n_times(self.service_requests, self.exp_text)
        self.service.request_n_times(self.service_requests, self.exp_text, hostname=True)
        self.deployment.http_request_all_pods(self.exp_text)


class PostUpdateHttpRequestRunner(ServiceWithDeploymentRunner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        kwargs["index"] = kwargs.get("exp_text", TEST_DEPLOYMENT_INDEX_CHANGED)
        kwargs["name"] = kwargs.get("new_cfgmap_name", TEST_INDEX_NAME_CHANGED)
        self.new_cfgmap = ConfigMap(**kwargs)
        self.service_requests = kwargs.get("service_requests", TEST_REPLICAS * 2)

    def start(self):
        super().start()
        self.new_cfgmap.create_if_not_exists(report=False)
        self.deployment.change_cfg_map(self.new_cfgmap.name, report=False)
        self.deployment.read_pods(report=False)

    def run(self):
        self.service.request_n_times(self.service_requests, self.new_cfgmap.index)
        self.deployment.http_request_all_pods(self.new_cfgmap.index)

    def finish(self):
        self.deployment.change_cfg_map(self.cfgmap.name, report=False)
