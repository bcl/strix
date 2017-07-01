from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import sys

class Tox(TestCommand):
    user_options = [('tox-args=', 'a', "Arguments to pass to tox")]
    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.tox_args = ""
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True
    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import tox
        import shlex

        # It doesn't use the ini by default for some reason
        self.tox_args += " -c tox.ini"
        errno = tox.cmdline(args=shlex.split(self.tox_args))
        sys.exit(errno)

setup(
    name="strix",
    version="0.0.1",
    packages=find_packages(),
    setup_requires=['nose>=1.0', 'setuptools-lint'],
    tests_require=['tox', 'coverage', 'nose', 'pylint'],
    cmdclass={'test': Tox},

    author="Brian Lane",
    author_email="bcl@brianlane.com",
    description="A Motion Camera API Server and UI",
    license="NeedToDecide",
    keywords="motion security camera strix",
    url="https://www.brianlane.com/software/strix.html"
)
