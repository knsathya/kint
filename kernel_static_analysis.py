#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Script for running static tests in kernel.
#
# Copyright (C) 2018 Sathya Kuppuswamy
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# @Author  : Sathya Kupppuswamy(sathyaosid@gmail.com)
# @History :
#            @v0.0 - Basic class support
# @TODO    :
#
#

import os
import re
import logging
import argparse

from lib.pyshell import GitShell, PyShell
from lib.build_kernel import is_valid_kernel
from lib.json_parser import JSONParser
from lib.decorators import format_h1

CHECK_PATCH_SCRIPT='scripts/checkpatch.pl'

class KernelStaticAnalysis(object):

    def __init__(self, src, branch=None, base=None, head=None, logger=None):

        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.base = base
        self.head = head
        self.branch = branch
        self.git = GitShell(wd=self.src, logger=logger)
        self.sh = PyShell(wd=self.src, logger=logger)
        self.valid_git = False
        self.cfg = None

        if not is_valid_kernel(src, logger):
            return

        if branch is not None and base is not None:
            ret, out, err = self.git.send_cmd(['checkout', branch])
            if ret != 0:
                self.logger.error("Git checkout command failed in %s", self.src)
                return
            else:
                self.valid_git = True

    def json_config(self, schema, cfg):
        if not os.path.exists(os.path.abspath(cfg)):
            self.logger.error("Invalid config file")
            return

        if not os.path.exists(os.path.abspath(schema)):
            self.logger.error("Invalid schema file")
            return

        parser = JSONParser(cfg, schema, extend_defaults=True, logger=self.logger)

        self.cfg = parser.get_cfg()

        parser.print_cfg()


    def run_checkpatch(self, branch=None, base=None, head=None):

        get_val = lambda x, y: getattr(self, y) if x is None else x

        err_count = 0
        warning_count = 0

        if self.valid_git is False:
            return -1, err_count, warning_count

        if not os.path.exists(os.path.join(self.src, CHECK_PATCH_SCRIPT)):
            return -1, err_count, warning_count

        branch = get_val(branch, 'branch')
        base = get_val(base, 'base')
        head = get_val(head, 'head')

        if branch is not None:
            ret, out, err = self.git.send_cmd(['checkout', branch])
            if ret != 0:
                return -1, err_count, warning_count

        ret, count, err = self.git.send_cmd(['rev-list', '--count',  str(base) + '..'+ str(head)])
        if ret != 0:
            return -1, err_count, warning_count

        self.logger.debug("Number of patches between %s..%s is %d", base, head, int(count))

        def parse_results(data):
            regex = r"total: ([0-9]*) errors, ([0-9]*) warnings,"
            match = re.search(regex, data)
            if match:
                self.logger.info(match.groups())
                return int(match.group(1)), int(match.group(2))

            return 0, 0

        prev_index = 0
        for index in range(1, int(count) + 1):
            commit_range = str(head) + '~' + str(index) + '..' + str(head) + '~' + str(prev_index)
            ret, out, err = self.sh.send_cmd([os.path.join(self.src, CHECK_PATCH_SCRIPT), '-g', commit_range])
            error, warning = parse_results(out)
            if error != 0 or warning != 0:
                self.logger.info(out)
                self.logger.info(err)
            err_count += error
            warning_count += warning
            prev_index = index

        self.logger.info("Total Error Count: %s", str(err_count))
        self.logger.info("Total Warning Count: %s", str(warning_count))

    def print_test_cfg(self):
        self.logger.info(format_h1("Static Test Config", tab=2))
        self.logger.info("Kernel Source: %s", self.src)
        self.logger.info("Kernel Branch: %s", self.branch)
        self.logger.info("Head: %s", self.head)
        self.logger.info("Base: %s\n", self.base)

def is_valid_dir(parser, arg):
    if not os.path.isdir(arg):
        yes = {'yes', 'y', 'ye', ''}
        print 'The directory {} does not exist'.format(arg)
        print 'Press y to create new directory'
        choice = raw_input().lower()
        if choice in yes:
            os.makedirs(arg)
        else:
            parser.error('The directory {} does not exist'.format(arg))

    return os.path.abspath(arg)

def add_cli_options(parser):

    parser.add_argument('-j', action='store_true', dest='use_json', help='Use Json parser')

    parser.add_argument('-i', '--kernel-dir', action='store', dest='source_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl source directory')
    parser.add_argument('-b', '--branch', default=None,
                        dest='branch', help='Kernel branch name')
    parser.add_argument('--head', default=None,
                        dest='head', help='Head commit ID')
    parser.add_argument('--base', default=None,
                        dest='base', help='Base commit ID')
    parser.add_argument('-s', '--schema-file', action='store', dest='config_schema',
                        default=os.path.join(os.getcwd(), 'config', 'test-configs',
                                             'kernel-compile-test-schema.json'),
                        help='Kernel test schema json file')
    parser.add_argument('-c', '--config-file', action='store', dest='config_data',
                        default=os.path.join(os.getcwd(), 'kint-configs', 'test-configs',
                                             'kernel-compile-test-sample.json'),
                        help='Kernel test config json file')
    parser.add_argument('-l', '--log', action='store', dest='log_file',
                        nargs='?',
                        const=os.path.join(os.getcwd(), 'ktest.log'),
                        help='Kernel test log file')
    parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                        help='Enable debug option')

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format='%(message)s')

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Script used for running static analysis test')

    add_cli_options(parser)

    args = parser.parse_args()

    if args.log_file is not None:
        if not os.path.exists(args.log_file):
            open(os.path.exists(args.log_file), 'w+').close()
            hdlr = logging.FileHandler(args.log_file)
            formatter = logging.Formatter('%(message)s')
            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)

    if args.debug:
            logger.setLevel(logging.DEBUG)

    obj= None

    if args.use_json is True:
        obj =  KernelStaticAnalysis(logger=logger)
        obj.json_config(args.config_schema, args.config_data)
    else:
        obj =  KernelStaticAnalysis(src=args.source_dir, branch=args.branch, base=args.base,
                                    head=args.head, logger=logger)

    if obj:
        if args.debug:
            obj.print_test_cfg()
        obj.run_checkpatch(branch=args.branch, head=args.head, base=args.base)






