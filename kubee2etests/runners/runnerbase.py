from kubee2etests.helpers_and_globals import load_kubernetes, TEST_DEPLOYMENT_INDEX
from kubee2etests import Deployment, Namespace, ConfigMap, Service
from kubee2etests.exceptions import PrerequisiteMissingException
from kubee2etests.statussender import StatusSender
from kubee2etests import helpers_and_globals as e2e_globals


class RunnerBase(StatusSender):
    def __init__(self, namespace, **kwargs):
        super().__init__()
        load_kubernetes()
        self.namespace = Namespace(namespace)


    def start(self):
        created = self.namespace.exists(report=False)
        if not created:
            raise PrerequisiteMissingException("NAMESPACE %s DOES NOT EXIST, QUITTING TEST" % self.namespace.name)

    def run(self):
        pass

    def finish(self):
        pass

    def exec(self):
        self.start()
        self.run()
        self.finish()


class RunnerBaseWithDeployment(RunnerBase):
    def __init__(self, namespace,
                 deployment,
                 replicas=e2e_globals.TEST_REPLICAS,
                 labels=e2e_globals.TEST_LABELS,
                 cfgmap=e2e_globals.TEST_INDEX_NAME, **kwargs):
        super().__init__(namespace)
        self.labels = labels
        self.deployment = Deployment(deployment, namespace, replicas, cfgmap, labels)
        self.cfgmap = ConfigMap(name=cfgmap,
                                index=TEST_DEPLOYMENT_INDEX,
                                namespace=self.namespace)

    def start(self):
        super().start()
        self.deployment.create_if_not_exists()

        self.cfgmap.create_if_not_exists()
        self.deployment.read_pods(report=False)

    def run(self):
        self.deployment.flush_errors()
        self.cfgmap.flush_errors()


class RunnerBaseWithDeploymentAndService(RunnerBaseWithDeployment):
    def __init__(self,
                 replicas=e2e_globals.TEST_REPLICAS,
                 service=e2e_globals.TEST_SERVICE,
                 namespace=e2e_globals.TEST_NAMESPACE,
                 **kwargs):
        super().__init__(namespace=namespace, **kwargs)
        self.service = Service(service=service, subsets=1, addresses=replicas,
                               namespace=namespace)

    def start(self):
        super().start()
        self.service.create_if_not_exists()

    def run(self):
        self.deployment.flush_errors()
        self.cfgmap.flush_errors()
        self.service.flush_errors()
