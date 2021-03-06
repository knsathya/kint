#!/usr/bin/env python
#
# Linux Kernel release script
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
import datetime
import tarfile
import tempfile
import shutil
import glob

from lib.json_parser import JSONParser
from lib.decorators import format_h1
from lib.pyshell import GitShell, PyShell
from lib.build_kernel import is_valid_kernel

class KernelRelease(object):

    def __init__(self, src=os.getcwd(), logger=None):

        self.logger = logger or logging.getLogger(__name__)
        self.src = os.path.abspath(src)
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

        if self.git.valid():
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

    def get_upload_params(self):
        default_params = {
            "remote": (),
            "remotebranch": "master",
            "new_commit": False,
            "file_format": ["*"],
            "remotedir": '.',
            "destdir": None,
            "commit_msg": "first commit",
            "clean_update": False,
            "use_refs": False,
            "force_update": False,
            "timestamp_suffix": False,
            "timestamp_format": "%m%d%Y%H%M%S",
            "tag_list": []
        }

        return default_params

    def upload_release(self, src, remote_cfg=None):
        '''

        :param src: Source dir. Either kernel, quilt or tar file.
        :param format: List of glob regex format of file to copied.
        :param remote_cfg: List of following dict
        "remote"               : (Remote Name, Remote URL)
        "remotebranch"         : Remote Branch
        "new_commit"           : Create new commit and then upload (True|False).
            "file_format"      : List of glob format of the files to be added to the commit.
            "remotedir"        : Relative dir (in remote)
            "commit_msg"       : Commit Message ()
            "clean_update"     : Remove existing changes before adding new changes (True | False).
            "destdir"          : destination directory for creating and uploading the new changes.
        "use_refs"             : Use refs/for when pushing (True | False).
        "force_update"         : Force update when pushing (True | False).
        "clean_update"         : Clean git remote before pushing your change (True | False).
        "timestamp_suffix"     : Add time stamp suffix to remotebranch before pushing.
                                 It will create a new branch (Trie | False).
        "timestamp_format"    : "%m%d%Y%H%M%S"
        "tag_list"            : [("name", "msg")], empty list if no tagging support needed. Use None for no message.
        :return:
        '''

        if remote_cfg is None:
            return False

        src = os.path.abspath(src)
        dest_dir = src
        used_temp = False

        try:
            for cfg in remote_cfg:

                dest_dir = src
                used_temp = False

                if len(cfg["remote"]) > 0 and cfg["remote"] is not None and cfg["remote"][1] is not None:
                    remote_list = [cfg["remote"]]
                else:
                    Exception("Incorrect remote name %s or url %s" % cfg["remote"])

                rbranch = cfg["remotebranch"]

                if cfg["timestamp_suffix"] and len(rbranch) > 0:
                    self.logger.info(format_h1("Upload timestamp branch", tab=2))
                    ts = datetime.datetime.utcnow().strftime(cfg["timestamp_format"])
                    rbranch = rbranch + '-' + ts

                if cfg["new_commit"] is True:
                    file_list = []

                    if cfg["destdir"] is not None:
                        if not os.path.exists(cfg["destdir"]):
                            Exception("Destination dir %s does not exist", cfg["destdir"])
                        else:
                            dest_dir = os.path.abspath(cfg["destdir"])
                    else:
                        used_temp = True
                        dest_dir = tempfile.mkdtemp()

                    git = GitShell(wd=dest_dir, init=True, remote_list=remote_list, fetch_all=True, logger=self.logger)

                    git.cmd("checkout", cfg["remote"][0] + '/' + cfg["remotebranch"])

                    if os.path.isdir(src):
                        for format in cfg["file_format"]:
                            file_list += glob.glob(os.path.join(os.path.abspath(src), format))
                    else:
                            file_list = [src]

                    # If clean update is True, then remove all contents of the repo.
                    if cfg["clean_update"] is True:
                        ret = git.cmd('rm', cfg["remotedir"] + '/*' if cfg["remotedir"] != '.' else '*')[0]
                        if ret != 0:
                            Exception("git rm -r *.patch failed")

                    if cfg["remotedir"] != '.' and not os.path.exists(os.path.join(dest_dir, cfg["remotedir"])):
                        os.makedirs(os.path.join(dest_dir, cfg["remotedir"]))

                    for item in file_list:
                        dest_path = os.path.join(os.path.abspath(dest_dir), cfg["remotedir"], os.path.basename(item))

                        from shutil import copyfile

                        copyfile(item, dest_path)

                        ret = git.cmd('add', cfg["remotedir"] + '/' + os.path.basename(item))
                        if ret != 0:
                            Exception("git add %s failed", cfg["remotedir"] + '/' + os.path.basename(item))

                    ret = git.cmd('commit -s -m "' + cfg["commit_msg"] + '"')[0]
                    if ret != 0:
                        Exception("git commit failed")

                git = GitShell(wd=dest_dir, init=True, remote_list=remote_list, fetch_all=True, logger=self.logger)

                ret = git.push('HEAD', cfg["remote"][0], rbranch, force=cfg["force_update"],
                               use_refs=cfg["use_refs"])[0]
                if ret != 0:
                        Exception("git push to %s %s failed" % (cfg["remote"][0], rbranch))

                for tag in cfg["tag_list"]:
                    # Push the tags if required
                    if tag[0] is not None:
                        if tag[1] is not None:
                            ret = git.cmd('tag', '-a', tag[0], '-m', tag[1])[0]
                        else:
                            ret = git.cmd('tag', tag[0])[0]
                        if ret != 0:
                            Exception("git tag %s failed" % (tag[0]))

                        ret = git.cmd('push', cfg["remote"][0], tag[0])[0]
                        if ret != 0:
                            Exception("git push tag to %s failed" % (cfg["remote"][0]))
        except Exception as e:
            self.logger.error(e)
            if used_temp is True:
                shutil.rmtree(dest_dir)
            return False
        else:
            return True

    def generate_quilt(self, local_branch=None, base=None, head=None,
                       patch_dir='quilt',
                       sed_file=None,
                       series_comment=''):


        set_val = lambda x, y: y if x is None else x

        clean_bkup = False

        self.logger.info(format_h1("Generating quilt series", tab=2))

        if not self.valid_git:
            self.logger.error("Invalid git repo %s", self.src)
            return None

        if sed_file is not None and not os.path.exists(sed_file):
            self.logger.error("sed pattern file %s does not exist", sed_file)
            return None

        local_branch = set_val(local_branch, self.git.current_branch())

        if local_branch is not None:
            if self.git.cmd('checkout', local_branch)[0] != 0:
                self.logger.error("git checkout command failed in %s", self.src)
                return None

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
                base = self.git.base_sha()
                if base is None:
                    raise Exception("git log command failed")

            # if head SHA is not given use HEAD as head SHA
            if head is None:
                head = self.git.head_sha()
                if head is None:
                    raise Exception("git fetch head SHA failed")

            ret, out, err = self.git.cmd('format-patch', '-C', '-M', base.strip() + '..' + head.strip(), '-o',
                                         patch_dir)
            if ret != 0:
                raise Exception("git format patch command failed out: %s error: %s" % (out, err))

            if sed_file is not None:
                ret, out, err = self.sh.cmd('sed -i -f%s %s/*.patch' % (sed_file, patch_dir), shell=True)
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
            return None
        else:
            if clean_bkup is True:
                shutil.rmtree(patch_dir_bkup)
            return patch_dir


    def generate_git_bundle(self, mode='branch', local_branch=None, head=None, base=None,
                            commit_count=0, outfile='git.bundle'):

        set_val = lambda x, y: y if x is None else x

        if mode not in self.bundle_modes:
            self.logger.error("Invalid bundle mode %s", mode)
            return None

        if not self.valid_git:
            self.logger.error("Invalid git repo %s", self.src)
            return None

        if outfile is None:
            self.logger.error("Invalid bundle name %s", outfile)
            return None

        local_branch = set_val(local_branch, self.git.current_branch())

        outfile = os.path.abspath(outfile)
        if os.path.exists(outfile):
            shutil.rmtree(outfile)

        self.logger.info(format_h1("Generating git bundle", tab=2))

        try:
            if local_branch is not None:
                ret, out, err = self.git.cmd('checkout', local_branch)
                if ret != 0:
                    raise Exception("Git checkout command failed in %s" % self.src)

            if mode == 'branch' and local_branch is not None:
                ret, out, err = self.git.cmd('bundle', 'create',  outfile, local_branch)
                if ret != 0:
                    raise Exception("Git bundle create command failed")
            elif mode == 'diff' and head is not None and base is not None:
                ret, out, err = self.git.cmd('bundle', 'create', outfile, str(base) + '..' + str(head))
                if ret != 0:
                    raise Exception("Git bundle create command failed")
            elif mode == 'commit_count' and local_branch is not None:
                ret, out, err = self.git.cmd('bundle', 'create', outfile, '-' + str(commit_count), local_branch)
                if ret != 0:
                    raise Exception("Git bundle create command failed")
        except Exception as e:
            self.logger.error(e)
            return None
        else:
            return outfile

    def generate_tar_gz(self, local_branch=None, outfile=None):
        self.logger.info(format_h1("Generating tar gz", tab=2))

        set_val = lambda x, y: y if x is None else x

        if local_branch is not None and self.valid_git:
            ret, out, err = self.git.cmd('checkout', local_branch)
            if ret != 0:
                self.logger.error("Git checkout command failed in %s", self.src)
                return None

        outfile = set_val(outfile, os.path.join(self.src, 'kernel.tar.gz'))

        def valid_file(tarinfo):
            if '.git' in tarinfo.name:
                return None

            return tarinfo

        out = tarfile.open(outfile, mode='w:gz')
        out.add(self.src, recursive=True, filter=valid_file)

        return outfile


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

    quilt_parser.add_argument('-u', action='store_true', dest='upload', help='Upload the quilt series')
    quilt_parser.add_argument('-o', '--out', default=None, dest='outfile', help='Quilt output folder path')
    quilt_parser.add_argument('-b', '--branch', default=None, dest='branch', help='Kernel branch name')
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
    logging.basicConfig(level=logging.INFO, format='%(message)s')

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

    obj = KernelRelease(src=args.source_dir, logger=logger)

    if obj:
        if args.which == 'bundle':
            obj.generate_git_bundle(args.mode, args.branch, args.head, args.base,
                                    args.commit_count, args.outfile)
        if args.which == 'quilt':
            obj.generate_quilt(args.branch, args.base, args.head, args.outfile, args.sed_fix, '',
                               False, args.remote, args.rbranch)
        if args.which == 'tar':
            obj.generate_tar_gz(args.branch, args.outfile)

        if args.which == 'upload':
            obj.upload_timestamp_branch(args.branch, args.remote, args.rbranch)
    else:
        logger.error("Invalid kernel output obj")
