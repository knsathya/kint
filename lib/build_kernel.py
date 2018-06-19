#!/usr/bin/python
#
# Linux kernel compilation and config  classes
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
import multiprocessing
from shutil import copy
import sys
import tempfile
import subprocess
import errno
from pyshell import PyShell

MAKE_CMD = '/usr/bin/make'

def assert_exists(name, message=None, logger=None):
    if not os.path.exists(os.path.abspath(name)):
        if logger is not None:
            logger.error(("%s does not exist" % name) if message is None else message)
        raise IOError(("%s does not exist" % name) if message is None else message)

def copy2(src, dest):
    try:
        copy(src, dest)
    except IOError as e:
        # ENOENT(2): file does not exist, raised also on missing dest parent dir
        if e.errno != errno.ENOENT:
            raise
        # try creating parent directories
        os.makedirs(os.path.dirname(dest))
        copy(src, dest)

set_val = lambda k, v: v if k is None else k

class KernelConfig(object):
    def __init__(self, src, out=None, bkup=True, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        assert_exists(src, "%s kernel config does not exits" % src, logger=self.logger)
        self.src = src
        self.out = set_val(out, src)
        self.bkup = self.src + '.bkup' if bkup is True else self.src
        self.choices = ['y', 'm', 'n']

    def _format_config(self, option, value):
        return option + "=%s\n" % value if value in ["y", "m"] else "# " + option + " is not set\n"

    def _config_exists(self, option, content):
        for choice in self.choices:
            if self._format_config(option, choice) == content:
                return True

        return False

    def _mod_config(self, option, value, in_file=None, out_file=None):

        cfg_src = self.src if in_file is None else in_file

        if value not in self.choices:
            raise Exception("Invalid config set %s option" % value)

        tmp_file = tempfile.NamedTemporaryFile(mode='w+t')

        with open(cfg_src) as cfgobj:
            for line in cfgobj:
                if not self._config_exists(option, line):
                    tmp_file.write(line)
                else:
                    tmp_file.write(self._format_config(option, value))
        cfgobj.close()

        tmp_file.seek(0)

        if out_file is not None:
            copy2(tmp_file.name, out_file)
        else:
            copy2(cfg_src, self.bkup)
            copy2(tmp_file.name, self.out)

        tmp_file.close()

        return True

    def enable_config(self, option, out_file=None):
        return self._mod_config(option, 'y', out_file=out_file)

    def module_config(self, option, out_file=None):
        return self._mod_config(option, 'm', out_file=out_file)

    def disable_config(self, option, out_file=None):
        return self._mod_config(option, 'n',  out_file=out_file)

    def merge_config(self, diff_cfg, out_file=None):

        update_list = []
        diff_list = []

        if type(diff_cfg) is list:
            diff_list = diff_cfg
        else:
            assert_exists(diff_cfg, logger=self.logger)
            with open(diff_cfg) as diffobj:
                diff_list = diffobj.read().splitlines()
            diffobj.close()

        for line in diff_list:
            option = line.split('=')[0].strip()
            value = line.split('=')[1].strip()
            if not option.startswith("CONFIG_") or value not in self.choices:
                logger.error("Invalid config : %s or value : %s" % (option, value))
                return False
            else:
                update_list.append((option, value))

        in_file = None
        for item in update_list:
            self._mod_config(item[0], item[1], in_file=in_file, out_file=out_file)
            if out_file is not None:
                in_file = out_file

        return True

def is_valid_kernel(src, logger=None):
    logger = logger or logging.getLogger(__name__)

    def parse_makefile(data, field):
        regex = r"%s = (.*)" % field
        match = re.search(regex, data)
        if match:
            return match.group(1)
        else:
            None

    if os.path.exists(os.path.join(src, 'Makefile')):
        with open(os.path.join(src, 'Makefile'), 'r') as makefile:
            _makefile = makefile.read()
            if parse_makefile(_makefile, "VERSION") is None:
                logger.error("Missing VERSION field in Makefile")
                return False
            if parse_makefile(_makefile, "PATCHLEVEL") is None:
                logger.error("Missing PATCHLEVEL field in Makefile")
                return False
            if parse_makefile(_makefile, "SUBLEVEL") is None:
                logger.error("Missing SUBLEVEL field in Makefile")
                return False
            if parse_makefile(_makefile, "EXTRAVERSION") is None:
                logger.warn("Missing EXTRAVERSION field in Makefile")
            if parse_makefile(_makefile, "NAME") is None:
                logger.error("Missing NAME field in Makefile")
                return False

        return True

    logger.error("%s Invalid kernel source directory", src)

    return False

class BuildKernel(object):

    def __init__(self, src_dir=None, arch=None, cc=None, cflags=None, out_dir=None, threads=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)

        self.src = os.path.abspath(set_val(src_dir, os.getcwd()))
        self.out = os.path.abspath(set_val(out_dir, os.path.join(self.src, 'out')))
        self.cfg = os.path.abspath(os.path.join(self.out, '.config'))
        self._makefile = None
        self.threads = set_val(threads, multiprocessing.cpu_count())
        self.clags = set_val(cflags, [])
        self.arch =  set_val(arch, "x86_64")
        self.cc = cc

        try:
            with open(os.path.join(self.src, 'Makefile'), 'r') as makefile:
                self._makefile = makefile.read()
        except:
            self.logger.error("%s Invalid kernel source directory", self.src)
            raise IOError

        self.uname = PyShell(logger=logger).cmd("make", "kernelversion")[1].strip()

        def parse_makefile(field):
            regex = r"%s = (.*)" % field
            match = re.search(regex, self._makefile)
            if match:
                return match.group(1)

        self.version = set_val(parse_makefile("VERSION"), '0')
        self.level = set_val(parse_makefile("PATCHLEVEL"), '0')
        self.sublevel = set_val(parse_makefile("SUBLEVEL"), '0')
        self.extra_version = set_val(parse_makefile("EXTRAVERSION"), "")
        self.version_name = set_val(parse_makefile("NAME"), "")

        if len(self.uname) == 0:
            self.uname = " ".join(["Linux", ''.join(['.'.join([self.version, self.level,
                                                               self.sublevel]), self.extra_version])])

        self.config_targets = ["config", "nconfig", "menuconfig", "xconfig", "gconfig", "oldconfig",
                               "localmodconfig", "localyesconfig", "defconfig", "savedefconfig",
                               "allnoconfig", "allyesconfig", "allmodconfig", "alldefconfig" ,
                               "randconfig", "listnewconfig", "olddefconfig", "kvmconfig", "xenconfig",
                               "tinyconfig"]

        self.clean_targets = ["clean", "mrproper", "distclean"]

        self.misc_targets = ["kernelversion"]

        for target in self.config_targets +  self.clean_targets + self.misc_targets:
            def make_variant(self, target=target, flags=[], log=False, dryrun=False):
                self._make_target(target=target, flags=flags, log=log, dryrun=dryrun)
            setattr(self.__class__, 'make_' + target , make_variant)

    def _exec_cmd(self, cmd, log=False, dryrun=False):
        self.logger.debug("BuildKernel: Executing %s", ' '.join(map(lambda x: str(x), cmd)))

        shell = PyShell(logger=self.logger)

        return shell.cmd(*cmd, out_log=log, dry_run=dryrun)

    def _make_target(self, target=None, flags=[], log=False, dryrun=False):

        mkcmd = [MAKE_CMD] + self.clags + ['-j%d' % self.threads, "ARCH=%s" % self.arch, "O=%s" % self.out, "-C", self.src]

        # Make sure out dir exists
        if not os.path.exists(self.out):
            os.makedirs(self.out)

        if self.cc is not None and len(self.cc) > 0 :
            mkcmd.append("CROSS_COMPILE=%s" % self.cc)

        mkcmd += flags

        if target is not None:
            mkcmd.append(target)

        ret, out, err = self._exec_cmd(mkcmd, log=log, dryrun=dryrun)
        if ret != 0:
            self.logger.error(' '.join(mkcmd) + " Command failed")

        self.logger.debug(out)

        return ret, out, err

    def make_newconfig(self, cfg, flags=[], log=False, dryrun=False):
        assert_exists(self.cfg, logger=self.logger)
        copy(cfg, self.cfg)
        self._make_target(target='oldconfig', flags=flags, log=log, dryrun=dryrun)

    def make_kernel(self, flags=[], log=False, dryrun=False):
        assert_exists(self.cfg, "No config file found in %s" % self.cfg, logger=self.logger)
        return self._make_target(flags=flags, log=log, dryrun=dryrun)

    def merge_config(self, diff_cfg, dryrun=False):
        kobj = KernelConfig(self.cfg, logger=self.logger)
        kobj.merge_config(diff_cfg)

    def __str__(self):
        return self.uname

if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.DEBUG)

    #obj = BuildKernel(src_dir="../tmp", logger=logger)
    #kobj = KernelConfig(src="../tmp/out/.config", logger=logger)
    #kobj.enable_config('CONFIG_DEBUG_VM')
    #kobj.merge_config(['CONFIG_DEBUG_VIRTUAL=y', 'CONFIG_DEBUG_VM=y'], out_file="../tmp/out/.config.tmp")

    #logger.info(obj)
    #obj.make_clean()
    #obj.make_oldconfig(log=True)
    #obj.merge_config(['CONFIG_DEBUG_VIRTUAL=y', 'CONFIG_DEBUG_VM=y'])
    #obj.make_kernel()
