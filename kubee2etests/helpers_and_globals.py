import ast
import datetime
import kubernetes
import logging
import os
import sys
import requests

from enum import Enum
from statsd import StatsClient
from kubernetes.config import ConfigException

from kubee2etests import __version__


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
DNS_COUNT_METRIC_NAME = "dns.%(result)s"

TEST_USER_AGENT = "e2etestapp-bot/" + __version__
TEST_REQUEST_HEADERS = {'User-Agent': TEST_USER_AGENT}

# resource names
TEST_NAMESPACE = "kubee2etests"
TEST_SERVICE = "kubee2etests"
TEST_DEPLOYMENT = "e2etestapp"
TEST_DNS_QUERY_NAME = "kubernetes.default.svc.cluster.local"

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

def add_error(self, err):
    error_list = [error[0] for error in self.errors]
    try:
        idx = error_list.index(err)
        self.errors[idx] = (err, self.errors[idx][1] + 1)
    except ValueError:
        self.errors.append((err, 1))

def add_errors(self, errors):
    """
    Method which adds errors to the object's error list - this allows us to batch send them
    when a status update is needed. It also does deduping of errors which have come up twice
    since the last status was sent to the frontend.

    Args:
        errors: (list) list of tuples to add to the error list - first entry being the error, second being the number of occurences

    Returns: None, as a side effect will update `self.errors`

    """
    error_list = [error[0] for error in self.errors]
    for err in errors:
        try:
            idx = error_list.index(err[0])
            self.errors[idx] = (err, self.errors[idx][1] + err[1])
        except ValueError:
            self.errors.append(err)

def send_update(self, name):
    """
    Method which will send an update on the current test to the flask frontend. If not running, will log it and carry on

    Args:
        name: (str) name of the test being ran

    Returns: (Response) requests response from the action.

    """
    namespace = os.environ.get("TEST_NAMESPACE", TEST_NAMESPACE)
    passing, msgs = self.results
    event = StatusEvent(name, passing, namespace, msgs)
    try:
        response = requests.post("http://localhost:{}/update".format(FLASK_PORT), json=event.event_data)
        return response
    except Exception as e:
        LOGGER.error("Flask endpoint not available, continuing")
        LOGGER.debug("Exception: %s", str(e))

