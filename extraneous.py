#!/bin/env python
# Copyright (C) 2018 Arrai Innovations Inc. - All Rights Reserved
import argparse
import os
import re
from itertools import chain

from colors import color
from pip._internal import get_installed_distributions
from pip._internal.utils.misc import dist_is_editable
from pipdeptree import build_dist_index, construct_tree, reverse_tree

flatten = chain.from_iterable
re_operator = re.compile(r'[>=]')
__version__ = '1.0.0'


def parse_requirement(line):
    if line.startswith('-e'):
        return line
    return re_operator.split(line)[0]


def read_requirements(verbose=True, include=None):
    cwd = os.getcwd()
    if verbose:
        print('reading requirements from:')
    reqs = set()
    for rname in include:
        relative_path = os.path.relpath(rname, cwd)
        try:
            with open(relative_path) as rfile:
                if verbose:
                    print('\t{}'.format(relative_path))
                reqs |= set(parse_requirement(line) for line in rfile.read().split('\n') if line)
        except FileNotFoundError:
            if verbose:
                print('\t{} (Not Found)'.format(relative_path))
    if not reqs:
        raise ValueError('No requirements found.{}'.format(
            '' if verbose else ' Use -v for more information.'
        ))
    return reqs


def read_installed(verbose=True):
    cwd = os.getcwd()
    from site import getsitepackages
    site_package_dirs = getsitepackages()
    if verbose:
        print('reading installed from:\n\t{}'.format(
            '\n\t'.join([os.path.relpath(x, cwd) for x in site_package_dirs])
        ))
    pkgs = get_installed_distributions()
    dist_index = build_dist_index(pkgs)
    tree = construct_tree(dist_index)
    branch_keys = set(r.key for r in flatten(tree.values()))
    nodes = [p for p in tree.keys() if p.key not in branch_keys]
    project_names = set(p.project_name for p in nodes)
    editable_packages = dict((p.render(frozen=True), p.project_name) for p in nodes if dist_is_editable(p._obj))
    return set(project_names), editable_packages, tree


def package_tree_to_name_tree(tree):
    return {k.project_name: set(i.project_name for i in v) for k, v in tree.items()}


def find_requirements_unique_to_projects(tree, root_package_names_to_uninstall):
    name_tree = package_tree_to_name_tree(tree)
    name_rtree = package_tree_to_name_tree(reverse_tree(tree))
    packages_to_uninstall = set(name for name in root_package_names_to_uninstall)

    def add_to_uninstall(packages):
        for package in packages:
            required_by = name_rtree.get(package, set())
            other_required_by = required_by - root_package_names_to_uninstall
            if not other_required_by:
                packages_to_uninstall.add(package)
                p_requirements = name_tree.get(package, None)
                if p_requirements:
                    add_to_uninstall(p_requirements)
    add_to_uninstall(root_package_names_to_uninstall)
    return packages_to_uninstall


if __name__ == '__main__':
    default_not_extraneous = ['extraneous', 'pipdeptree', 'pip', 'setuptools']
    default_requirements = ['requirements.txt', 'local_requirements.txt', 'test_requirements.txt']
    parser = argparse.ArgumentParser(
        description='Identifies packages that are installed but not defined in requirements files. Prints the'
                    " 'pip uninstall' command that removes these extraneous packages and any non-common"
                    ' dependencies.'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Prints installed site-package folders and requirements files.'
    )
    parser.add_argument(
        '--include', '-i',
        metavar='paths',
        action='append',
        help='Requirements file paths to look for. If not defined, looks for {}.'.format(default_requirements)
    )
    parser.add_argument(
        '--exclude', '-e',
        metavar='names',
        action='append',
        default=[],
        help='Package names to not consider extraneous.'
             ' {} are not considered extraneous packages.'.format(default_not_extraneous)
    )
    parser.add_argument(
        '--full', '-f',
        action='store_true',
        help='Allows {} as extraneous packages.'.format(default_not_extraneous)
    )
    args = parser.parse_args()
    installed, editable, tree = read_installed(args.verbose)
    requirements = read_requirements(
        args.verbose,
        include=args.include or default_requirements
    )
    for frozen, name in editable.items():
        if frozen in requirements:
            requirements.remove(frozen)
            requirements.add(name)
    not_extraneous = set(args.exclude)
    if not args.full:
        not_extraneous |= set(default_not_extraneous)
    extraneous = installed - requirements - not_extraneous
    if extraneous:
        extraneous_str = ' '.join(sorted(extraneous))
        print(color(
            'extraneous packages:\n\t{}'.format(extraneous_str),
            fg='yellow'
        ))
        uninstall = find_requirements_unique_to_projects(tree, extraneous) - not_extraneous - extraneous
        print('uninstall via:\n\tpip uninstall -y {} {}'.format(
            extraneous_str,
            ' '.join(sorted(uninstall))
        ))
