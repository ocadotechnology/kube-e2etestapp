from unittest import TestCase
from kubee2etests.apimixin import ApiMixin
import json


class TestSuiteParseError(TestCase):
    def setUp(self):
        self.json_str = json.dumps({'message': 'object unprocessable',
                                    'code': 422})
        self.mixin = ApiMixin(None)

    def testCode(self):
        code, error_dict = self.mixin.parse_error(self.json_str)
        self.assertEqual(code.name, code.UNPROCESSABLE_ENTITY.name)
        self.assertEqual(error_dict['message'], 'object unprocessable')
