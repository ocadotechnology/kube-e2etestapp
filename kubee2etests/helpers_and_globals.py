import kubernetes
import logging
import ast
import datetime

from enum import Enum
from statsd import StatsClient

from kubee2etests import __version__
from kubernetes.config import ConfigException
import sys
import os


LOGGER = logging.getLogger(__name__)

ANTI_AFFINITY_KEY = "failure-domain.beta.kubernetes.io/zone"
PROMETHEUS_PREFIX = 'e2etest'
STATSD_PORT = int(os.environ.get("STATSD_PORT", "8125"))
STATSD_CLIENT = StatsClient(port=STATSD_PORT, prefix=PROMETHEUS_PREFIX)
TIME_TO_REPORT_PARAMETER = 'TIME_TO_REPORT_PROBLEM'
SECONDS_BETWEEN_RUNS = '0.0'

ACTION_METRIC_NAME = "action.%(namespace)s.%(resource)s.%(action)s"
ERROR_METRIC_NAME = "error.%(namespace)s.%(resource)s.%(area)s.%(error)s"
HTTP_COUNT_METRIC_NAME = "http.%(namespace)s.%(resource)s.%(result)s"

TEST_USER_AGENT = "e2etestapp-bot/" + __version__
TEST_REQUEST_HEADERS = {'User-Agent': TEST_USER_AGENT}

# resource names
TEST_NAMESPACE = "kubee2etests"
TEST_SERVICE = "kubee2etests"
TEST_DEPLOYMENT = "e2etestapp"

# image from which to base the container, html string for index pages
NGINX_IMAGE = "nginx:alpine@sha256:aa0daf2b17c370a1da371a767110a43b390a9db90b90d2d1b07862dc81754d61"
TEST_DEPLOYMENT_IMAGE = os.path.join(os.environ.get("DOCKER_REGISTRY_HOST", ''), NGINX_IMAGE)
TEST_DEPLOYMENT_INDEX = """<html>
      <body>
        <h1>
          Hello World!
        </h1>
      </body>
    </html>"""
TEST_DEPLOYMENT_INDEX_CHANGED = """<html>
      <body>
        <h1>
          Hello Kubernetes!
        </h1>
      </body>
    </html>"""
TEST_INDEX_NAME = 'hello-world'
TEST_INDEX_NAME_CHANGED = 'hello-kubernetes'
TEST_VOLUME_CLAIM_NAME = 'test-claim'

TEST_REPLICAS = 3
CUSTOM_LABELS = ast.literal_eval(os.environ.get("CUSTOM_TEST_DEPLOYMENT_LABELS", '{}'))
TEST_LABELS = {'app': 'hellominikube'}
TEST_LABELS.update(CUSTOM_LABELS)
TEST_CONTAINER_PORT = 80

# time to wait for events before timing out, used in wait_on_event
TEST_EVENT_TIMEOUTS = 60

PROMETHEUS_PORT = 8080
FLASK_PORT = '8081'
STATSD_PORT = '8082'
STATSD_HOST = ''

class EventType(Enum):
    ADDED = "ADDED"
    DELETED = "DELETED"
    MODIFIED = "MODIFIED"
    ALL = "ALL"


class StatusEvent(object):
    def __init__(self, name, passing, namespace=TEST_NAMESPACE, info=None, time=None):
        self.name = name
        self.passing = passing
        self.info = info
        self.namespace = namespace
        if not time:
            self.time = datetime.datetime.now()
        else:
            self.time = datetime.datetime.strptime(time, '%Y-%m-%d %H:%M:%S')

    @property
    def event_data(self):
        data = {"name": self.name,
                "passing": self.passing,
                "namespace": self.namespace,
                "info": self.info,
                "time": self.time.strftime('%Y-%m-%d %H:%M:%S')}
        return data


def load_kubernetes():
    incluster = False
    try:
        kubernetes.config.load_kube_config()
    except (FileNotFoundError, ConfigException) as err:
        logging.debug("Not able to use Kubeconfig: %s", err)
        try:
            kubernetes.config.load_incluster_config()
            incluster = True
        except (FileNotFoundError, ConfigException) as err:
            logging.error("Not able to use in-cluster config: %s", err)
            sys.exit(1)
    return incluster
