from kubee2etests.runners.runnerbase import RunnerBase
from kubee2etests import Deployment, ConfigMap, PersistentVolumeClaim
from kubee2etests import helpers_and_globals as e2e_globals


class DeploymentRunner(RunnerBase):
    def __init__(self, deployment=e2e_globals.TEST_DEPLOYMENT, namespace=e2e_globals.TEST_NAMESPACE,
                 replicas=e2e_globals.TEST_REPLICAS, cfgmap_name=e2e_globals.TEST_INDEX_NAME,
                 cfgmap_index=e2e_globals.TEST_DEPLOYMENT_INDEX,
                 labels=e2e_globals.TEST_LABELS,
                 template_labels=e2e_globals.TEST_TEMPLATE_LABELS,
                 volume_claim=None,
                 claim_storage=None,
                 **kwargs):
        super().__init__(namespace=namespace)
        self.name = deployment
        self.volume_claim = volume_claim
        self.deployment = Deployment(self.name,
                                                namespace,
                                                replicas,
                                                cfgmap_name,
                                                labels,
                                                template_labels)
        self.cfgmap = ConfigMap(name=cfgmap_name,
                                index=cfgmap_index,
                                namespace=namespace)
        self.volclaim = PersistentVolumeClaim(name=self.volume_claim,
                                              namespace=namespace,
                                              storage=claim_storage)

    def setup(self):
        self.cfgmap.create_if_not_exists()
        self.deployment.create_if_not_exists()
        self.deployment.read_pods(report=False)

    def run(self):
        self.cfgmap.create()
        if self.volume_claim is not None:
            self.volclaim.create()
        self.deployment.create()
        self.deployment.exists()
        self.deployment.wait_on_pods_scheduled()
        self.deployment.wait_on_pods_ready()
        self.deployment.check_pods_on_different_nodes()
        self.deployment.check_pods_on_different_data_centres()

    def finish(self):
        self.deployment.delete()
        self.deployment.deleted()
        self.deployment.watch_pod_scaling()
        self.deployment.read_pods(report=False)
        self.deployment.check_pods_deleted()
        if self.volume_claim is not None:
            self.volclaim.delete()
            self.volclaim.deleted()
        self.cfgmap.delete()
        self.cfgmap.deleted()
        super().finish()

class DeploymentVolumeClaimRunner(DeploymentRunner):
    def __init__(self, deployment=e2e_globals.TEST_DEPLOYMENT, namespace=e2e_globals.TEST_NAMESPACE, storage="3.14Gi",
                 **kwargs):
        super().__init__(deployment=deployment, namespace=namespace, volume_claim=e2e_globals.TEST_VOLUME_CLAIM_NAME,
                         claim_storage=storage, **kwargs)


class DeploymentWithUpdateRunner(DeploymentRunner):
    def __init__(self,
                 new_cfg_map=e2e_globals.TEST_INDEX_NAME_CHANGED,
                 new_index=e2e_globals.TEST_DEPLOYMENT_INDEX_CHANGED,
                 **kwargs):
        super().__init__(**kwargs)
        self.updated_cfgmap = ConfigMap(new_cfg_map,
                                        new_index,
                                        kwargs.get("namespace", e2e_globals.TEST_NAMESPACE))

    def start(self):
        super().start()
        super().setup()
        self.updated_cfgmap.create_if_not_exists(report=False)

    def run(self):
        self.deployment.change_cfg_map(new_cfgmap_name=self.updated_cfgmap.name)
        self.deployment.wait_on_pods_scheduled()
        self.deployment.wait_on_pods_ready()
        self.deployment.check_pods_deleted(phase="Terminating")

    def finish(self):
        self.deployment.change_cfg_map(new_cfgmap_name=self.cfgmap.name, report=False)
        self.deployment.flush_errors()


class DeploymentWithScalingRunner(DeploymentRunner):
    def start(self):
        super().start()
        super().setup()

    def run(self):
        self.deployment.scale(0)
        self.deployment.watch_pod_scaling()
        self.deployment.check_pods_deleted()

    def finish(self):
        self.deployment.scale(3, report=False)
        self.deployment.flush_errors()
