from kubee2etests.runners.runnerbase import RunnerBase
from kubee2etests.runners.deployment_runners import DeploymentRunner
from kubee2etests import Service
from kubee2etests import helpers_and_globals as e2e_globals


class ServiceRunner(RunnerBase):
    def __init__(self, service=e2e_globals.TEST_SERVICE, **kwargs):
        super().__init__(**kwargs)
        self.service_name = service
        self.service = Service(service,
                               kwargs.get("subsets", 0),
                               kwargs.get("replicas", 0),
                               kwargs.get("namespace", e2e_globals.TEST_NAMESPACE))

    def setup(self):
        self.service.create_if_not_exists(report=False)

    def run(self):
        super().run()
        self.service.create()
        self.service.exists()
        self.service.read_endpoints()

    def finish(self):
        self.service.delete()
        self.service.deleted()
        super().finish()


class ServiceWithDeploymentRunner(ServiceRunner, DeploymentRunner):
    def __init__(self, *args, **kwargs):
        kwargs["replicas"] = kwargs.get("replicas", 3)
        ServiceRunner.__init__(self, *args, subsets=1, **kwargs)
        DeploymentRunner.__init__(self, *args, **kwargs)

    def start(self):
        ServiceRunner.setup(self)
        DeploymentRunner.setup(self)
        self.deployment.wait_on_pods_ready(report=False)

    def run(self):
        self.service.read_endpoints()

    def finish(self):
        pass

class ServiceWithScaledDeploymentRunner(ServiceWithDeploymentRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, replicas=0, **kwargs)

    def start(self):
        ServiceWithDeploymentRunner.start(self)
        self.deployment.scale(0, report=False)
        self.deployment.watch_pod_scaling(report=False)

    def finish(self):
        self.deployment.scale(3, report=False)
