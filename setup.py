import os
from setuptools import find_packages, setup
import versioneer
from setuptools.command.test import test as TestCommand

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()
# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))
test_dependencies = ['nose', 'coverage'
]
dependencies = ['requests',
                'kubernetes',
                'prometheus_client'
                ]
class NoseTestCommand(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True
    def run_tests(self):
        # Run nose ensuring that argv simulates running nosetests directly
        import nose
        nose.run_exit(argv=['nosetests'])

cmdclass = versioneer.get_cmdclass()
cmdclass['test'] = NoseTestCommand
setup(
    name='kubee2etests',
    packages=find_packages(),
    include_package_data=True,
    description='Package for testing kubernetes end to end, intended for live clusters',
    long_description=README,
    url='https://gitlab.tech.lastmile.com/kubernetes/end2endtestapp',
    author='Charlotte Godley',
    author_email='c.godley@ocado.com',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    entry_points={
    },
    test_suite='tests',
    tests_require=test_dependencies,
    install_requires=dependencies,
    version=versioneer.get_version(),
    cmdclass=cmdclass
)
