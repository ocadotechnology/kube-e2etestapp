import dns.resolver
import logging
from kubee2etests.runners.service_runners import ServiceWithDeploymentRunner
from kubee2etests import ConfigMap
from kubee2etests import helpers_and_globals as e2e_globals
from kubee2etests.helpers_and_globals import STATSD_CLIENT, TEST_DEPLOYMENT_INDEX, TEST_DEPLOYMENT_INDEX_CHANGED, \
    TEST_REPLICAS, TEST_INDEX_NAME_CHANGED, TEST_DNS_QUERY_NAME, DNS_COUNT_METRIC_NAME

LOGGER = logging.getLogger(__name__)

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


class DNSRequestRunner():
    def __init__(self,namespace,service,deployment):
        super().__init__()
        self.qname = TEST_DNS_QUERY_NAME

    def add_error(self, err):
        error_list = [error[0] for error in self.errors]
        try:
            idx = error_list.index(err)
            self.errors[idx] = (err, self.errors[idx][1] + 1)
        except ValueError:
            self.errors.append((err, 1))

    def incr_dns_count_metric(self,result):
        """
        Helper method which increments the dns request count metric.
        Args:
            result: string of what happened - healthy, nxdomain etc
        Returns: None, increments the statsd dns count metric
        """
        result_data = {"result": result}
        STATSD_CLIENT.incr(DNS_COUNT_METRIC_NAME % result_data)

    def exec(self):
        try:
            dns.resolver.query(self.qname)
            result="healthy"
            LOGGER.info("DNS healthy")
        except Exception as ex:
            result=type(ex).__name__.lower()
            LOGGER.error("Querying %s failed. %s", self.qname, ex)
            self.add_error(ex)
        self.incr_dns_count_metric(result)
        

        