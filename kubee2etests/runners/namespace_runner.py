from kubee2etests.namespace import Namespace
from kubee2etests.helpers_and_globals import load_kubernetes, TEST_NAMESPACE


class NamespaceRunner(object):
    def __init__(self, namespace=TEST_NAMESPACE, **kwargs):
        load_kubernetes()
        self.namespace = namespace
        self.namespace_obj = Namespace(namespace)

    def start(self):
        self.namespace_obj.create()
        self.namespace_obj.exists()


    def run(self):
        self.namespace_obj.empty()

    def finish(self):
        self.namespace_obj.delete()
        self.namespace_obj.deleted()

    def exec(self):
        self.start()
        self.run()
        self.finish()
