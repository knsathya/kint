#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Production kernel test script
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
import copy
import re

from lib.json_parser import JSONParser
from lib.build_kernel import BuildKernel, is_valid_kernel
from lib.decorators import format_h1
from lib.pyshell import PyShell, GitShell

RESULT_SCHEMA = os.path.join(os.getcwd(), 'config/kernel-test-results-schema.json')
TEST_SCHEMA = os.path.join(os.getcwd(), 'config/kernel-test-schema.json')
TEST_CONFIG = os.path.join(os.getcwd(), 'config/kernel-test-sample.json')

CHECK_PATCH_SCRIPT='scripts/checkpatch.pl'

supported_configs = ['allyesconfig', 'allmodconfig', 'allnoconfig', 'defconfig', 'randconfig']
supported_archs = ['x86_64', 'i386', 'arm64']

class KernelResults(object):
    def __init__(self, src=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.results = {}
        self.kernel_params = {}
        self.compile_results = []
        self.checkpatch_results = {}
        self.aiaiai_results = {}

        res_obj = {}

        self.kernel_params["head"] = ""
        self.kernel_params["base"] = ""
        self.kernel_params["branch"] = ""
        self.kernel_params["version"] = "Linux"

        for arch in supported_archs:
            compile_obj = {}
            compile_obj["arch_name"] = arch
            compile_obj["version"] = arch
            compile_obj["head"] = arch
            compile_obj["base"] = arch
            for config in supported_configs:
                compile_obj[config] = {}
                compile_obj[config]["status"] = "N/A"
                compile_obj[config]["warning_count"] = 0
                compile_obj[config]["error_count"] = 0

            self.compile_results.append(compile_obj)

        self.checkpatch_results["status"] = "N/A"
        self.checkpatch_results["warning_count"] = 0
        self.checkpatch_results["error_count"] = 0

        self.aiaiai_results["status"] = "N/A"
        self.aiaiai_results["warning_count"] = 0
        self.aiaiai_results["error_count"] = 0

        res_obj["kernel-params"] = self.kernel_params
        res_obj["compile-test"] = self.compile_results
        res_obj["checkpatch"] = self.checkpatch_results
        res_obj["aiaiai"] = self.aiaiai_results

        self.results = JSONParser(res_obj, RESULT_SCHEMA, extend_defaults=True)

    def update_compile_test_results(self, arch, config, status, warning_count=0, error_count=0):
        for obj in self.results["compile-test"]:
            if obj['arch_name'] == arch:
                obj[config]["status"] = "Passed" if status else "Failed"
                obj[config]["warning_count"] = warning_count
                obj[config]["error_count"] = error_count

    def update_aiaiai_results(self, status, warning_count=None, error_count=None):
        self.results["aiaiai"]["status"] = "Passed" if status else "Failed"
        if warning_count is not None:
            self.results["aiaiai"]["warning_count"] = warning_count
        if error_count is not None:
            self.results["aiaiai"]["error_count"] = warning_count

    def update_checkpatch_results(self, status, warning_count=None, error_count=None):
        self.results["checkpatch"]["status"] = "Passed" if status else "Failed"
        if warning_count is not None:
            self.results["checkpatch"]["warning_count"] = warning_count
        if error_count is not None:
            self.results["checkpatch"]["error_count"] = warning_count

    def update_kernel_params(self, version=None, branch=None, base=None, head=None):
        if version is not None:
            self.results["kernel-params"]["version"] = version
        if branch is not None:
            self.results["kernel-params"]["branch"] = branch
        if base is not None:
            self.results["kernel-params"]["base"] = base
        if head is not None:
            self.results["kernel-params"]["head"] = head

    def kernel_info(self):
        out = ''
        if self.src is not None:
            out += 'Kernel Info:\n'
            out += "\tVersion: %s" % self.results["kernel-params"]["version"]
        if self.branch is not None:
            out += "\tBranch: %s" % self.results["kernel-params"]["branch"]
        if self.head is not None:
            out += "\tHead: %s" % self.results["kernel-params"]["head"]
        if self.base is not None:
            out += "\tBase: %s" % self.results["kernel-params"]["base"]

        return out + '\n'

    def compile_test_results(self):
        width = len(max(supported_configs, key=len)) * 2
        out = 'Compile Test Results:\n'
        for obj in self.compile_results:
            out += '\t%s results:\n' % obj['arch_name']
            for config in supported_configs:
                out += '\t\t%s results:\n' % config
                out += ('\t\t\t%-' + str(width) + 's: %s\n') % (config, obj[config])

        return out + '\n'

    def checkpatch_test_results(self):
        out = 'Checkpatch Test Results:\n'
        out += '\tstatus       : %s\n' % self.checkpatch_results["status"]
        out += '\twarning_count: %s\n' % self.checkpatch_results["warning_count"]
        out += '\terror_count  : %s\n' % self.checkpatch_results["error_count"]

        return out + '\n'

    def aiaiai_test_results(self):
        out = 'AiAiAi Test Results:\n'
        out += '\tstatus       : %s\n' % self.aiaiai_results["status"]
        out += '\twarning_count: %s\n' % self.aiaiai_results["warning_count"]
        out += '\terror_count  : %s\n' % self.aiaiai_results["error_count"]

        return out + '\n'

    def print_test_results(self, test_type="compile"):
        out = ''
        out += self.kernel_info()
        if test_type == "compile":
            out += self.compile_test_results()
        elif test_type == "checkpatch":
            out += self.checkpatch_test_results()
        elif test_type == "aiaiai":
            out += self.aiaiai_test_results()
        elif test_type == "all":
            out += self.compile_test_results()
            out += self.checkpatch_test_results()
            out += self.aiaiai_test_results()

        self.logger.info(out)

class KernelTest(object):

    def __init__(self, src, cfg=None, branch=None, head=None, base=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.branch = branch
        self.head = head
        self.base = base
        self.valid_git = False
        self.cfg = JSONParser(cfg, TEST_SCHEMA, extend_defaults=True).get_cfg()
        self.resobj = KernelResults(self.src, logger)
        self.git = GitShell(wd=self.src, logger=logger)
        self.sh = PyShell(wd=self.src, logger=logger)
        self.checkpatch_source = CHECK_PATCH_SCRIPT
        self.aiaiai_source = ""

        if not is_valid_kernel(src, logger):
            return

        self.version = BuildKernel(self.src).uname

        if len(self.version) > 0:
            self.resobj.update_kernel_params(version=self.version)

        self.valid_git = True if self.git.valid() else False

        if self.valid_git:
            if self.branch is not None:
                if self.git.cmd('checkout', branch)[0] != 0:
                    self.logger.error("Git checkout command failed in %s", self.src)
                    return
            else:
                self.branch = self.git.current_branch()

            #update base & head if its not given
            if self.head is None:
                self.head = self.git.head_sha()
            if self.base is None:
                self.base = self.git.base_sha()

            self.resobj.update_kernel_params(base=self.base, head=self.head, branch=self.branch)

    def run_test(self):
        self.logger.info(format_h1("Running kernel tests from json", tab=2))

        status = True

        if self.cfg is None:
            self.logger.warning("Invalid JSON config file")
            return False

        compile_config = self.cfg.get("compile-config", None)

        if compile_config is not None and compile_config["enable"] is True:

            for obj in compile_config["test-list"]:
                def config_enabled(config):
                    return obj[config]

                for config in filter(config_enabled, supported_configs):
                    current_status = self.compile(obj["arch_name"], config,
                                                  obj["compiler_options"]["CC"],
                                                  obj["compiler_options"]["cflags"])
                    if current_status is False:
                        self.logger.error("Compilation of arch:%s config:%s failed\n" % (obj["arch_name"], config))

                    status &= current_status

        checkpatch_config = self.cfg.get("checkpatch-config", None)

        if checkpatch_config is not None and checkpatch_config["enable"] is True:
            if len(checkpatch_config["source"]) > 0:
                self.checkpatch_source = checkpatch_config["source"]
            status &= self.run_checkpatch()[0]

        aiaiai_config = self.cfg.get("aiaiai-config", None)

        if aiaiai_config is not None and aiaiai_config["enable"] is True:
            if len(aiaiai_config["source"]) > 0:
                self.aiaiai_source = aiaiai_config["source"]
            status &= self.run_aiaiai()

        return status

    def compile(self, arch='', config='', cc='', cflags=[]):
        if arch not in supported_archs or config not in supported_configs:
            self.logger.error("Invalid arch/config %s/%s" % (arch, config))
            return False

        kobj = BuildKernel(src_dir=self.src, out_dir=os.path.join(self.out, arch, config),
                           arch=arch, cc=cc, cflags=cflags, logger=self.logger)
        getattr(kobj, 'make_' + config)()

        status = True if kobj.make_kernel()[0] == 0 else False

        self.resobj.update_compile_test_results(arch, config, status)

        return status

    def compile_list(self, arch='', config_list=[], cc='', cflags=[]):
        self.logger.info(format_h1("Running compile tests", tab=2))
        result = []

        for config in config_list:
            result.append(self.compile(arch, config, cc, cflags))

        return result

    def run_aiaiai(self):
        self.logger.info(format_h1("Run AiAiAi Script", tab=2))

        return True

    def run_checkpatch(self):

        self.logger.info(format_h1("Runing checkpatch script", tab=2))

        self.enable_checkpatch = True

        get_val = lambda x, y: getattr(self, y) if x is None else x

        err_count = 0
        warning_count = 0

        try:
            if self.valid_git is False:
                raise Exception("Invalid git repo")

            if not os.path.exists(os.path.join(self.src, CHECK_PATCH_SCRIPT)):
                raise Exception("Invalid checkpatch script")

            ret, count, err = self.git.cmd('rev-list', '--count',  str(self.base) + '..'+ str(self.head))
            if ret != 0:
                raise Exception("git rev-list command failed")

            self.logger.debug("Number of patches between %s..%s is %d", self.base, self.head, int(count))

            def parse_results(data):
                regex = r"total: ([0-9]*) errors, ([0-9]*) warnings,"
                match = re.search(regex, data)
                if match:
                    return int(match.group(1)), int(match.group(2))

                return 0, 0

            prev_index = 0
            for index in range(1, int(count) + 1):
                commit_range = str(self.head) + '~' + str(index) + '..' + str(self.head) + '~' + str(prev_index)
                ret, out, err = self.sh.cmd(os.path.join(self.src, CHECK_PATCH_SCRIPT), '-g', commit_range)
                error, warning = parse_results(out)
                if error != 0 or warning != 0:
                    self.logger.debug(out)
                    self.logger.debug(err)
                err_count += error
                warning_count += warning
                prev_index = index
        except Exception as e:
            self.logger.error(e)
            return False, err_count, warning_count
        else:
            self.resobj.update_checkpatch_results(True, err_count, warning_count)
            return True, err_count, warning_count

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

    subparsers = parser.add_subparsers(help='Commands')
    compile_parser = subparsers.add_parser('compile', help='Run compile test')
    compile_parser.set_defaults(which='use_compile')
    compile_parser.add_argument('arch', choices=supported_archs, dest='arch', help='Arch to be tested')
    compile_parser.add_argument('--configs', default=[], nargs='*',
                        choices=supported_configs,
                        dest='config_list',
                        help='list of configs to be tested')
    compile_parser.add_argument('--cflags', default=[], nargs='*',
                        dest='cflags',
                        help='cflags')
    compile_parser.add_argument('--cc', default='', dest='cc', help='Cross Compile')

    checkpatch_parser = subparsers.add_parser('checkpatch', help='Run checkpatch test')
    checkpatch_parser.set_defaults(which='use_checkpatch')

    aiaiai_parser = subparsers.add_parser('aiaiai', help='Run AiAiAi test')
    aiaiai_parser.set_defaults(which='use_aiaiai')

    json_parser = subparsers.add_parser('use_json', help='Run json test')
    json_parser.add_argument('-c', action='store', dest='config',
                             default=TEST_CONFIG,
                             help='Kernel test config json file')

    aiaiai_parser.set_defaults(which='use_json')

    parser.add_argument('-i', '--kernel-dir', action='store', dest='source_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl source directory')
    parser.add_argument('--branch', default=None, dest='branch', help='Kernel branch name')
    parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    parser.add_argument('--base', default=None, dest='base', help='Base commit ID')
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


