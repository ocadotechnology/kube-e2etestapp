from kubee2etests.runners import deployment_runners, namespace_runner, request_runners, service_runners
from argparse import ArgumentParser
from kubee2etests import helpers_and_globals as e2e_globals
import os
import logging
import time


LOGGER = logging.getLogger(__name__)


def _determine_log_level():
    level_name = os.environ.get("LOG_LEVEL", "INFO")
    try:
        return getattr(logging, level_name.upper())
    except AttributeError:
        LOGGER.warning("Unknown log level {0}. Set to default INFO".format(level_name.upper()))
        return logging.INFO


def main():
    logging.basicConfig(level=_determine_log_level())
    suites = {"deployment": deployment_runners.DeploymentRunner,
              "deployment_pvc": deployment_runners.DeploymentVolumeClaimRunner,
              "namespace": namespace_runner.NamespaceRunner,
              "deployment_update": deployment_runners.DeploymentWithUpdateRunner,
              "deployment_scale": deployment_runners.DeploymentWithScalingRunner,
              "service": service_runners.ServiceRunner,
              "deployment_service": service_runners.ServiceWithDeploymentRunner,
              "deployment_scale_service": service_runners.ServiceWithScaledDeploymentRunner,
              "http": request_runners.HttpRequestRunner,
              "http_update": request_runners.PostUpdateHttpRequestRunner}
    namespace = os.environ.get("TEST_NAMESPACE", e2e_globals.TEST_NAMESPACE)
    deployment = os.environ.get("TEST_DEPLOYMENT", e2e_globals.TEST_DEPLOYMENT)
    service = os.environ.get("TEST_SERVICE", e2e_globals.TEST_SERVICE)
    seconds_to_wait = float(os.environ.get("SECONDS_BETWEEN_RUNS", e2e_globals.SECONDS_BETWEEN_RUNS))
    parser = ArgumentParser("Kubernetes end to end test runner.")
    parser.add_argument("suite", type=str, help="The suite to run", choices=set(list(suites.keys())))
    args = parser.parse_args()
    e2e_globals.load_kubernetes()
    test_class = suites[args.suite](namespace=namespace, deployment=deployment, service=service)
    while True:
        try:
            test_class.exec()
        except KeyboardInterrupt:
            LOGGER.error("Got keyboard interrupt, cleaning up and exiting")
            test_class.finish()
            raise RuntimeError
        time.sleep(seconds_to_wait)

if __name__ == '__main__':
    main()
