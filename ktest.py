#!/usr/bin/env python
#
# Production kernel intergration test script
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
import logging, logging.config
import argparse

from lib.json_parser import JSONParser
from lib.build_kernel import BuildKernel
from lib.decorators import format_h1


supported_configs = ['allyesconfig', 'allmodconfig', 'allnoconfig', 'defconfig', 'randconfig']

supported_archs = ['x86_64', 'i386', 'arm64']

class KernelTest(object):
    def _get_testobj(self, name):
        for obj in self.tests:
            if obj['arch_name'] == name:
                return obj

        return None

    def _get_resobj(self, name):
        for obj in self.results:
            if obj['arch_name'] == name:
                return obj

        return None

    def __init__(self, src=os.getcwd(), out=None,
                 test_archs=[],
                 config_list=[], logger=None):

        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.out = os.path.join(src, 'out') if out is None else out
        self.results = []
        self.tests = []

        for arch_name in supported_archs:
            testobj = {}
            resobj = {}
            testobj['arch_name'] = arch_name
            testobj['compiler_options'] = { 'CC': "", 'cflags': [] }
            resobj['arch_name'] = arch_name
            for config in supported_configs:
                testobj[config] = True if arch_name in test_archs and config in config_list else False
                resobj[config] = '"N/A"'
            self.results.append(resobj)
            self.tests.append(testobj)

    def print_test_cfg(self):
        for obj in self.tests:
            self.logger.info(format_h1("Arch Name: " + obj['arch_name'], tab=2))
            for config in supported_configs:
                self.logger.info("Config: %-20s\t Status: %-10s", config, obj[config])

    def print_test_results(self):
        for obj in self.results:
            self.logger.info(format_h1("Arch Name: " + obj['arch_name'], tab=2))
            for config in supported_configs:
                self.logger.info("Config: %-20s\t Status: %-10s", config, obj[config])

    def json_config(self, schema, cfg):
        if not os.path.exists(os.path.abspath(cfg)):
            self.logger.error("Invalid config file")
            return

        if not os.path.exists(os.path.abspath(schema)):
            self.logger.error("Invalid schema file")
            return

        parser = JSONParser(cfg, schema, logger=self.logger)

        self.cfg = parser.get_cfg()

        if len(self.cfg["results-template"]) > 0:
            self.results = self.cfg["results-template"]

        # Make sure all arch/configs are supported
        if len(self.cfg["test-list"]) > 0:
            for test in self.cfg["test-list"]:
                obj = self._get_testobj(test['arch_name'])
                if obj is None:
                    self.logger.error("%s arch is not supported", test['arch_name'])
                    return

        # update the arch/config configuration.
        if len(self.cfg["test-list"]) > 0:
            for test in self.cfg["test-list"]:
                obj = self._get_testobj(test['arch_name'])
                for config in supported_configs:
                    if test.get(config, None) is not None:
                        obj[config] = test[config]

        parser.print_cfg()


    def run(self):
        self.logger.info("Running kernel tests")

        def update_results(arch, config, status):
            resobj = self._get_resobj(arch)
            if resobj is None:
                self.logger.warn("Results template does not have %s arch name", arch)

            resobj[config] = status

        for test in self.tests:
            self.logger.debug(test)
            arch_name = test.get('arch_name', None)
            for config in supported_configs:
                if test[config] is True:
                    if arch_name is None:
                        self.logger.error("arch %s is not supported")
                    else:
                        kobj = BuildKernel(src_dir=self.src, out_dir=os.path.join(self.out, test['arch_name'], config),
                                           arch=test['arch_name'],
                                           cc=test['compiler_options']['CC'],
                                           cflags=test['compiler_options']['cflags'],
                                           logger=self.logger)
                        getattr(kobj, 'make_' + config)()
                        ret, out, err = kobj.make_kernel()
                        update_results(arch_name, config, True if ret == 0 else False)

        return self.results

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
    parser.add_argument('--archs', default=[], nargs='*',
                        choices=supported_archs,
                        dest='arch_list',
                        help='list of archs to be tested')
    parser.add_argument('--configs', default=[], nargs='*',
                        choices=supported_configs,
                        dest='config_list',
                        help='list of configs to be tested')
    parser.add_argument('-s', '--schema-file', action='store', dest='config_schema',
                        default=os.path.join(os.getcwd(), 'kint-configs', 'ktest-schema.json'),
                        help='Kernel test schema json file')
    parser.add_argument('-c', '--config-file', action='store', dest='config_data',
                        default=os.path.join(os.getcwd(), 'kint-configs', 'ktest-sample.json'),
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

    parser = argparse.ArgumentParser(description='Script used for running automated kerenl compilation testing')

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
        obj =  KernelTest(logger=logger)
        obj.json_config(args.config_schema, args.config_data)
    else:
        obj =  KernelTest(src=args.source_dir, test_archs=args.arch_list, config_list=args.config_list, logger=logger)

        obj.run()

        if args.debug:
            obj.print_test_cfg()

        obj.print_test_results()

