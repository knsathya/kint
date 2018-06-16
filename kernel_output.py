#!/usr/bin/env python
#
# Production kernel output script
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
import tempfile
import argparse
import glob
import tarfile
import inspect
import shutil

from lib.json_parser import JSONParser
from lib.decorators import format_h1
from lib.pyshell import GitShell, PyShell
from lib.build_kernel import is_valid_kernel

def lineno():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno

class KernelOutput(object):

    def __init__(self, src=os.getcwd(), logger=None):

        self.logger = logger or logging.getLogger(__name__)
        self.src = src
        self.base = None
        self.head = None
        self.local_branch = None
        self.remote = None
        self.remote_branch = None
        self.git = GitShell(wd=self.src, logger=logger)
        self.sh = PyShell(wd=self.src, logger=logger)
        self.valid_git = False
        self.cfg = None
        self.bundle_modes = ['branch', 'diff', 'commit_count']

        #self.git.dryrun(True)
        #self.sh.dryrun(True)

        if not is_valid_kernel(src, logger):
            return

        if not os.path.exists(os.path.join(self.src, '.git')):
            self.logger.warning("Invalid git repo")
        else:
            self.valid_git = True

    def generate_output(self, schema, cfg):

        if not os.path.exists(os.path.abspath(cfg)):
            self.logger.error("Invalid config file %s", os.path.abspath(cfg))
            return False

        if not os.path.exists(os.path.abspath(schema)):
            self.logger.error("Invalid schema file %s", os.path.abspath(schema))
            return False

        parser = JSONParser(schema, cfg, extend_defaults=True, logger=self.logger)

        self.cfg = parser.get_cfg()

        return True

    def generate_quilt(self, local_branch=None, head=None, base=None,
                       patch_dir='quilt',
                       sed_file=None,
                       series_comment='',
                       upload_quilt=False, remote=None, remote_branch=None):

        set_val = lambda x, y: y if x is None else x

        clean_bkup = False

        self.logger.info(format_h1("Generating quilt series", tab=2))

        if not self.valid_git:
            self.logger.error("Invalid git repo %s", self.src)
            return False

        if sed_file is not None and not os.path.exists(sed_file):
            self.logger.error("sed pattern file %s does not exist", sed_file)
            return False

        local_branch = set_val(local_branch, self.git.current_branch())

        if local_branch is not None:
            ret, out, err = self.git.cmd('checkout', local_branch)
            if ret != 0:
                self.logger.error("Git checkout command failed in %s", self.src)
                return False

        try:
            patch_dir = os.path.abspath(patch_dir)
            patch_dir_bkup = patch_dir + '.old'
            if os.path.exists(patch_dir):
                clean_bkup = True
                shutil.move(patch_dir, patch_dir_bkup)

            os.makedirs(patch_dir)

            series_file = os.path.join(patch_dir, 'series')

            # if base SHA is not given use TAIL as base SHA
            if base is None:
                ret, out, err = self.git.cmd('log', '--oneline', '|', 'tail', '-1', '|', 'cut', "-d' '", '-f1')
                if ret != 0:
                    raise Exception("Git log command failed in %s" % err)
                base = out.strip()

            # if head SHA is not given use HEAD as head SHA
            if head is None:
                ret, out, err = self.git.cmd('log', '--oneline', '|', 'head', '-1', '|', 'cut', "-d' '", '-f1')
                if ret != 0:
                    raise Exception("Git log command failed in %s" % err)
                head = out.strip()


            ret, out, err = self.git.cmd('format-patch', '-C', '-M', base.strip() + '..' + head.strip(), '-o', patch_dir)
            if ret != 0:
                raise Exception("Git format patch command failed in %s" % err)

            if sed_file is not None:
                ret, out, err = self.sh.cmd('sed', '-i', '-f%s' % sed_file, '%s/*.patch' % patch_dir)
                if ret != 0:
                    raise Exception("sed command failed %s" % err)

            with open(series_file, 'w+') as fobj:
                fobj.write(series_comment)
            ret, out, err = self.sh.cmd('ls -1 *.patch >> series', wd=patch_dir, shell=True)
            if ret != 0:
                raise Exception("Writing to patch series file failed. Error: %s" % err)

        except Exception as e:
            if os.path.exists(patch_dir):
                shutil.rmtree(patch_dir)
            if clean_bkup is True:
                    shutil.move(patch_dir_bkup, patch_dir)
            self.logger.error(e)
            return False
        else:
            if clean_bkup is True:
                shutil.rmtree(patch_dir_bkup)
            return True


    def generate_git_bundle(self, mode='branch', local_branch=None, head=None, base=None,
                            commit_count=0, outfile='git.bundle'):

        set_val = lambda x, y: y if x is None else x

        if mode not in self.bundle_modes:
            self.logger.error("Invalid bundle mode %s", mode)
            return False

        if not self.valid_git:
            self.logger.error("Invalid git repo %s", self.src)
            return False

        if outfile is None:
            self.logger.error("Invalid bundle name %s", outfile)
            return False

        local_branch = set_val(local_branch, self.git.current_branch())

        outfile = os.path.abspath(outfile)
        if os.path.exists(outfile):
            shutil.rmtree(outfile)

        self.logger.info(format_h1("Generating git bundle", tab=2))

        if local_branch is not None:
            ret, out, err = self.git.cmd('checkout', local_branch)
            if ret != 0:
                self.logger.error("Git checkout command failed in %s", self.src)
                self.logger.error(err)
                return False

        if mode == 'branch' and local_branch is not None:
            ret, out, err = self.git.cmd('bundle', 'create',  outfile, local_branch)
            if ret != 0:
                self.logger.error("Git bundle create command failed")
                return False
        elif mode == 'diff' and head is not None and base is not None:
            ret, out, err = self.git.cmd('bundle', 'create', outfile, str(base) + '..' + str(head))
            if ret != 0:
                self.logger.error("Git bundle create command failed")
                return False
        elif mode == 'commit_count' and local_branch is not None:
            ret, out, err = self.git.cmd('bundle', 'create', outfile, '-' + str(commit_count), local_branch)
            if ret != 0:
                self.logger.error("Git bundle create command failed")
                return False

        return True

    def generate_tar_gz(self, local_branch=None, outfile=None):
        self.logger.info(format_h1("Generating tar gz", tab=2))

        set_val = lambda x, y: y if x is None else x

        if local_branch is not None and self.valid_git:
            ret, out, err = self.git.cmd('checkout', local_branch)
            if ret != 0:
                self.logger.error("Git checkout command failed in %s", self.src)
                return False

        outfile = set_val(outfile, os.path.join(self.src, 'kernel.tar.gz'))

        def valid_file(tarinfo):
            if '.git' in tarinfo.name:
                return None

            return tarinfo

        out = tarfile.open(outfile, mode='w:gz')
        out.add(self.src, recursive=True, filter=valid_file)

        return True

    def generate_timestamp_branch(self, local_branch=None):
        self.logger.info(format_h1("Generating timestamp branch", tab=2))

    def upload_timestamp_branch(self, local_branch=None, remote=None, remote_branch=None):
        self.logger.info(format_h1("Upload timestamp branch", tab=2))

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

    subparsers = parser.add_subparsers(help='commands')

    bundle_parser = subparsers.add_parser('bundle', help='Create git bundle')
    bundle_parser.set_defaults(which='bundle')
    bundle_parser.add_argument('-m', '--mode', action='store', default='branch', dest='mode',
                               choices=['branch', 'diff', 'commit_count'],
                               help='git bundle mode')
    bundle_parser.add_argument('-c', '--count', action='store', type=int, default=0,
                               dest='commit_count',
                               help='Bundle commit count')
    bundle_parser.add_argument('-o', '--out', default=None, dest='outfile',
                               help='Bundle output file name')
    bundle_parser.add_argument('-b', '--branch', default=None, dest='branch', help='Kernel branch name')
    bundle_parser.add_argument('-r', '--remote', default=None, dest='remote', help='Kernel remote name')
    bundle_parser.add_argument('--rbranch', default=None, dest='rbranch', help='Kernel remote branch name')
    bundle_parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    bundle_parser.add_argument('--base', default=None, dest='base', help='Base commit ID')

    quilt_parser = subparsers.add_parser('quilt', help='Create quilt patchset')
    quilt_parser.set_defaults(which='quilt')
    quilt_parser.add_argument('-o', '--out', default=None, dest='outfile', help='Quilt output folder path')
    quilt_parser.add_argument('-b', '--branch', default=None, dest='branch', help='Kernel branch name')
    quilt_parser.add_argument('-r', '--remote', default=None, dest='remote', help='Kernel remote name')
    quilt_parser.add_argument('--rbranch', default=None, dest='rbranch', help='Kernel remote branch name')
    quilt_parser.add_argument('--head', default=None, dest='head', help='Head commit ID')
    quilt_parser.add_argument('--base', default=None, dest='base', help='Base commit ID')
    quilt_parser.add_argument('--sed-fix', default=None, dest='sed_fix', help='Sed file with regex')

    tar_parser = subparsers.add_parser('tar', help='Create kernel tar source')
    tar_parser.set_defaults(which='tar')
    tar_parser.add_argument('-o', '--out', default=None, dest='outfile', help='Source tar file name')
    tar_parser.add_argument('-b', '--branch', default=None, dest='branch', help='Kernel branch name')

    upload_parser = subparsers.add_parser('upload', help='Upload kernel to remote branch')
    upload_parser.set_defaults(which='upload')
    upload_parser.add_argument('-b', '--branch', default=None, dest='branch', help='Kernel branch name')
    upload_parser.add_argument('-r', '--remote', default=None, dest='remote', help='Kernel remote name')
    upload_parser.add_argument('--rbranch', default=None, dest='rbranch', help='Kernel remote branch name')

    parser.add_argument('-j', action='store_true', dest='use_json', help='Use Json parser')

    parser.add_argument('-i', '--kernel-dir', action='store', dest='source_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl source directory')

    parser.add_argument('-s', '--schema-file', action='store', dest='config_schema',
                        default=os.path.join(os.getcwd(), 'config',
                                             'kernel-output-schema.json'),
                        help='Kernel test schema json file')
    parser.add_argument('-c', '--config-file', action='store', dest='config_data',
                        default=os.path.join(os.getcwd(), 'config',
                                             'kernel-output-sample.json'),
                        help='Kernel test config json file')
    parser.add_argument('-l', '--log', action='store', dest='log_file',
                        nargs='?',
                        const=os.path.join(os.getcwd(), 'ktest.log'),
                        help='Kernel test log file')
    parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                        help='Enable debug option')


if __name__ == "__main__":
    ret = True
    logging.basicConfig(level=logging.ERROR, format='%(message)s')

    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Script used for gnerating kernel output')

    add_cli_options(parser)

    args = parser.parse_args()

    print args

    if args.log_file is not None:
        if not os.path.exists(args.log_file):
            open(os.path.exists(args.log_file), 'w+').close()
            hdlr = logging.FileHandler(args.log_file)
            formatter = logging.Formatter('%(message)s')
            hdlr.setFormatter(formatter)
            logger.addHandler(hdlr)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    obj = KernelOutput(src=args.source_dir, logger=logger)

    if obj:
        if args.which == 'bundle':
            obj.generate_git_bundle(args.mode, args.branch, args.head, args.base,
                                    args.commit_count, args.outfile)
        if args.which == 'quilt':
            obj.generate_quilt(args.branch, args.head, args.base, args.outfile, args.sed_fix, '',
                               False, args.remote, args.rbranch)
        if args.which == 'tar':
            obj.generate_tar_gz(args.branch, args.outfile)

        if args.which == 'upload':
            obj.upload_timestamp_branch(args.branch, args.remote, args.rbranch)
    else:
        logger.error("Invalid kernel output obj")