from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
from .configmap import ConfigMap
from .pod import Pod
from .deployment import Deployment
from .persistentvolumeclaim import PersistentVolumeClaim
from .namespace import Namespace
from .service import Service
