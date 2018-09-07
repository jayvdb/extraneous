# Copyright (C) 2018 Arrai Innovations Inc. - All Rights Reserved
import json
import os
import subprocess
import venv
import sys
from tempfile import TemporaryDirectory, NamedTemporaryFile
from unittest import TestCase

from colors import color


class ExtraneousTestCase(TestCase):
    cwd_path = ''
    env_path = ''
    _cwd_path = TemporaryDirectory()
    _env_path = TemporaryDirectory()

    @classmethod
    def setUpClass(cls):
        cls.cwd_path = cls._cwd_path.__enter__()
        cls.env_path = cls._env_path.__enter__()
        cls.setup_venv()
        cls.subcmd('coverage erase', cwd_path=os.getcwd(), parent_envs=True)

    @classmethod
    def tearDownClass(cls):
        cls.subcmd('cp {cwd_path}/.coverage.* {real_cwd}/'.format(cwd_path=cls.cwd_path, real_cwd=os.getcwd()))
        cls.subcmd('coverage combine', cwd_path=os.getcwd(), parent_envs=True)
        try:
            cls.subcmd('rm -rf htmlcov', cwd_path=os.getcwd(), parent_envs=True)
        except subprocess.CalledProcessError:
            pass
        cls.subcmd('coverage html', cwd_path=os.getcwd(), parent_envs=True)
        cls._env_path.__exit__(None, None, None)
        cls._cwd_path.__exit__(None, None, None)

    @classmethod
    def subcmd(cls, cmd, cwd_path=None, coverage=False, parent_envs=False):
        kwargs = {
            'shell': True,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'check': False,
            'cwd': cls.cwd_path if not cwd_path else cwd_path
        }
        if not parent_envs:
            kwargs['env'] = cls.env_vars
        if coverage:
            cmd = 'coverage run -p ' + cmd
        ran = subprocess.run(cmd, **kwargs)
        try:
            ran.check_returncode()
        except subprocess.CalledProcessError as e:
            if ran.stdout:
                print('stdout', ran.stdout)
            if ran.stderr:
                print('stderr', ran.stderr)
            raise
        return ran

    @classmethod
    def pip_install(cls, package, editable=False, upgrade=False):
        return cls.subcmd(
            'python -m pip install {upgrade}{editable}{package}'.format(
                env_path=cls.env_path,
                upgrade='--upgrade ' if upgrade else '',
                editable='-e ' if editable else '',
                package=package
            )
        )

    @classmethod
    def setup_venv(cls, editable=False):
        real_cwd = os.getcwd()
        venv.create(cls.env_path, with_pip=True)
        venv_vars = subprocess.run(
            'deactivate; source {env_path}/bin/activate; jq -n -M env'.format(env_path=cls.env_path),
            **{'shell': True, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'check': True}
        ).stdout
        cls.env_vars = json.loads(venv_vars)
        cls.env_vars.pop('PYTHONPATH')
        cls.pip_install('pip setuptools coverage', upgrade=True)
        cls.pip_install(real_cwd, editable=True)
        cls.subcmd('echo "import coverage; coverage.process_startup()" > `{env_path}/bin/python -c "import sys; print([x for x in sys.path if \'site-packages\' in x][0] + \'/coverage-all-the-things.pth\')"`'.format(
            env_path=cls.env_path
        ))
        cls.pip_install(' '.join('{}/test_packages/{}'.format(real_cwd, package) for package in [
            'extraneous_sub_package_1',
            'extraneous_sub_package_2',
            'extraneous_top_package_1',
            'extraneous_top_package_2',
            'extraneous_top_package_3',
        ]), editable=editable)
        with open('{cwd_path}/requirements.txt'.format(cwd_path=cls.cwd_path), mode='w') as w:
            w.write('extraneous-top-package-1\n')
        with open('{cwd_path}/test_requirements.txt'.format(cwd_path=cls.cwd_path), mode='w') as w:
            w.write('extraneous-top-package-3\ncoverage\n')
        with open('{cwd_path}/.coveragerc'.format(cwd_path=cls.cwd_path), mode='w') as w:
            w.write('''[run]
branch = True
parallel = True
concurrency = multiprocessing
include = *extraneous/extraneous.py

[report]
exclude_lines =
    raise NotImplementedError
    except ImportError'''.format(env_path=cls.env_path))

    @classmethod
    def get_sitepackages_for_venv(cls):
        ran = cls.subcmd(
            'python -c "from site import getsitepackages; import os;'
            'print(\'\\n\\t\'.join([os.path.relpath(x, os.getcwd()) for x in getsitepackages()]))"'.format(
                env_path=cls.env_path
            )
        )
        return ran.stdout.decode('utf8').strip()

    def test_verbose(self):
        extraneous = self.subcmd(
            '{env_path}/bin/extraneous.py -v'.format(env_path=self.env_path),
            coverage=True
        )
        self.assertMultiLineEqual(
            'reading installed from:\n\t{site_packages}\n'
            'reading requirements from:\n\t{requirements}\n'
            '{extraneous}\n'
            'uninstall via:\n\tpip uninstall -y {uninstall}\n'.format(
                site_packages=self.get_sitepackages_for_venv(),
                requirements='\n\t'.join([
                    'requirements.txt',
                    'local_requirements.txt (Not Found)',
                    'test_requirements.txt'
                ]),
                extraneous=color(
                    'extraneous packages:\n\t{}'.format(' '.join(sorted({
                        'extraneous-top-package-2',
                    }))),
                    fg='yellow'
                ),
                uninstall=' '.join(sorted({
                    'extraneous-top-package-2',
                }) + sorted({
                    'extraneous-sub-package-2',
                })),
            ),
            extraneous.stdout.decode('utf8')
        )

    def test_full(self):
        extraneous = self.subcmd(
            '{env_path}/bin/extraneous.py -f'.format(env_path=self.env_path),
            coverage=True
        )
        self.assertMultiLineEqual(
            '{extraneous}\n'
            'uninstall via:\n\tpip uninstall -y {uninstall}\n'.format(
                extraneous=color(
                    'extraneous packages:\n\t{}'.format(' '.join(sorted({
                        'extraneous-top-package-2', 'extraneous', 'setuptools'
                    }))),
                    fg='yellow'
                ),
                uninstall=' '.join(sorted({
                    'extraneous-top-package-2', 'extraneous', 'setuptools'
                }) + sorted({
                    'extraneous-sub-package-2', 'ansicolors', 'pipdeptree'
                })),
            ),
            extraneous.stdout.decode('utf8')
        )

    def test_exclude_top(self):
        extraneous = self.subcmd(
            '{env_path}/bin/extraneous.py -e extraneous-top-package-2'.format(env_path=self.env_path),
            coverage=True
        )
        self.assertMultiLineEqual(
            '',
            extraneous.stdout.decode('utf8')
        )

    def test_exclude_sub(self):
        extraneous = self.subcmd(
            '{env_path}/bin/extraneous.py -e extraneous-sub-package-2'.format(env_path=self.env_path),
            coverage=True
        )
        self.assertMultiLineEqual(
            '{extraneous}\n'
            'uninstall via:\n\tpip uninstall -y {uninstall}\n'.format(
                extraneous=color(
                    'extraneous packages:\n\t{}'.format(' '.join(sorted({
                        'extraneous-top-package-2',
                    }))),
                    fg='yellow'
                ),
                uninstall=' '.join(sorted({
                }) + sorted({
                    'extraneous-top-package-2'
                })),
            ),
            extraneous.stdout.decode('utf8')
        )

    def test_include(self):
        other_req = NamedTemporaryFile(mode='w+', delete=False)
        other_req.write('extraneous-top-package-2\ncoverage\n')
        other_req.close()
        try:
            extraneous = self.subcmd(
                '{env_path}/bin/extraneous.py -v -i {other_req}'.format(
                    env_path=self.env_path, other_req=other_req.name
                ),
                coverage=True
            )
            self.assertMultiLineEqual(
                'reading installed from:\n\t{site_packages}\n'
                'reading requirements from:\n\t{requirements}\n'
                '{extraneous}\n'
                'uninstall via:\n\tpip uninstall -y {uninstall}\n'.format(
                    site_packages=self.get_sitepackages_for_venv(),
                    requirements='\n\t'.join([
                        other_req.name
                    ]),
                    extraneous=color(
                        'extraneous packages:\n\t{}'.format(' '.join(sorted({
                            'extraneous-top-package-1', 'extraneous-top-package-3',
                        }))),
                        fg='yellow'
                    ),
                    uninstall=' '.join(sorted({
                        'extraneous-top-package-1', 'extraneous-top-package-3',
                    })),
                ),
                extraneous.stdout.decode('utf8')
            )
        finally:
            os.unlink(other_req.name)

    def test_installed_editable(self):
        # todo: implement
        pass
