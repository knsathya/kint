#!/usr/bin/env python
#
# Linux Kernel intergration script
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
import yaml
from shutil import rmtree, move

from lib.json_parser import JSONParser
from lib.build_kernel import BuildKernel
from lib.decorators import format_h1
from lib.rand_utils import git_send_email
from lib.pyshell import GitShell, PyShell


GIT_COMMAND_PATH='/usr/bin/git'

set_val = lambda k, v: v if k is None else k

set_list_val = lambda k, v: k if len(k) > 0 else v

class KernelInteg(object):

    def _git(self, *args, **kwargs):
        # type: (object, object) -> object
        """
        Execute the given git command using subprocess and return command output.
        :rtype: str
        :param args: List of git command arguments.
        :param kwargs:
                      silent - Set True to suppress any exceptions.
                      wd - Set work directory for given command.
        :return: Command output
        """
        silent = kwargs.pop('silent', False)

        ret_code, std_out, std_err = self.git.cmd(*args, **kwargs)

        if ret_code != 0:
            if silent is False:
                self.logger.error(' '.join(self.git.curr_cmd) + " command failed")
                self.logger.error(std_err)
                err_msg = "%s. Code: %s" % (std_err.strip(), ret_code)
                raise Exception(err_msg)

        return std_out

    def _git_merge(self, *args, **kwargs):
        """

        Execute given git merge/rebase command, and use rrcache to resolve any conflicts if auto_merge is set True in
        kwargs. Also send email to recipients mentioned in email-options of KI json file, if needed manual effort in
        resolving the conflict.
            :param args: Merge params.
            :param kwargs:
            Dict options.
            silent - Set True to supress any exceptions.
            wd - Work directory of git command.
            send_email - Set True if you want to send merge conflict email.
            :return: None
        """
        yes = {'yes', 'y', 'ye', ''}

        ret_code, std_out, std_err = self.git.cmd(*args, **kwargs)

        if ret_code != 0:
            use_manual_merge = True
            self.logger.error(' '.join(self.git.curr_cmd) + " command failed")
            self.logger.error(std_err)

            status = self.git.cmd('diff')[1]

            if kwargs.pop('auto_merge', False) == True and ">>>>>" not in status and "<<<<<<" not in status:
                if "rebase" in list(args):
                    while True:
                        self.git.cmd('rebase', '--continue')
                        if not os.path.exists(os.path.join(self.repo_dir, '.git/rebase-apply')):
                            break
                    status = self.git.cmd('diff')[1]
                    if not ">>>>>" in status and not "<<<<<<" in status:
                        use_manual_merge = False
                elif "merge" in list(args) or "pull" in list(args):
                    self.git.cmd('commit','-as', '--no-edit')
                    use_manual_merge = False

            if use_manual_merge is True:
                if  kwargs.pop('send_email', False) is True:
                    status = self.git.cmd('status')[1]
                    content = "Following is the status of command: \n" + ' '.join(args) + '\n'
                    content += 'Stdout Message:\n\n' + std_out if len(std_out) > 0 else "None" + '\n'
                    content += 'Error Message:\n\n' + std_err if len(std_err) > 0 else "None" + '\n'
                    content += "Git Status:\n\n" + status + '\n'
                    self.send_email(subject_prefix=kwargs.pop('subject_prefix', ''),
                                    subject=kwargs.pop('subject', 'Merge Conflict'),
                                    content=content)
                while True:
                    print 'Please resolve the issue and then press y to continue'
                    choice = raw_input().lower()
                    if choice in yes:
                        status = self.git.cmd('diff')[1]
                        if ">>>>>" in status or "<<<<<<" in status:
                            continue
                        else:
                            break

    def _is_valid_head(self, head):
        """
        Check whether given SHA ID is valid or not. Executing git show <SHA ID> will fail if the <SHA ID> is incorrect.
        :param head: SHA ID
        :return: True if the SHA ID or head is valid, otherwise return False.
        """
        ret, out, err  = self.git.cmd('show', head)
        if ret == 0:
            return True

        return False

    def _is_valid_local_branch(self, branch):
        """
        Check whether given branch is available in repo directory or not.
        :param branch: git branch name.
        :return: True if the branch name is valid, otherwise False.
        """
        branches = self._git('branch')
        self.logger.info(map(lambda it: it.strip().replace('* ', ''), branches.splitlines()))
        # Check if given branch name is branch of 'git branch' command output.
        if branch not in map(lambda it: it.strip().replace('* ', ''), branches.splitlines()):
            self.logger.error("%s invalid branch name\n" % branch)
            return False

        return True

    def __init__(self, cfg, schema, repo_head='', repo_dir=os.getcwd(), subject_prefix='', skip_rr_cache=False, logger=None):
        # type: (json, jsonschema, str, str, str, boolean, boolean) -> object
        """
        Constructor of KernelInteg class.
        :rtype: object
        :param cfg: Kernel Integration Json config file.
        :param schema: Kernel Integration Json schema file.
        :param repo_head: SHA-ID or Tag of given branch.
        :param repo_dir: Repo directory.
        :param subject_prefix: Prefix for email subject.
        :param skip_rr_cache: Skip rr cache if set True.
        :param logger: Logger object
        """
        self.logger = logger or logging.getLogger(__name__)
        self.cfg = JSONParser(cfg, schema, logger=self.logger).get_cfg()
        self.remote_list = self.cfg['remote-list']
        self.repos = self.cfg['repos']
        self.kint_repos = self.cfg['kint-list']
        self.email_options = self.cfg['email-options']
        self.test_profiles = self.cfg['test-profiles']
        self.repo_dir = repo_dir
        self.skip_rr_cache = skip_rr_cache
        self.subject_prefix = subject_prefix
        # All git commands will be executed in repo directory.
        self.git = GitShell(wd=self.repo_dir, logger=self.logger)

        # git init
        self.logger.info(format_h1("Initalizing repo", tab=2))
        if not os.path.exists(os.path.join(self.repo_dir, ".git")):
            self._git("init", ".")

        # Create out dir if its not exists.
        out_dir = os.path.join(self.repo_dir, 'out')
        if not os.path.exists(out_dir):
            self.logger.info(format_h1("Create out dir", tab=2))
            os.makedirs(out_dir)

        # Add git remote
        self.logger.info(format_h1("Add remote", tab=2))
        for remote in self.remote_list:
            self._git("remote", "add", remote['name'], remote['url'], silent=True)

        # Get the latest updates
        self._git("remote", "update")

        valid_repo_head = False

        # Check if the repo head is valid.
        if len(repo_head) > 0:
            if self._is_valid_head(repo_head) is False:
                raise Exception("Invalid repo head %s" % repo_head)
            else:
                valid_repo_head = True

         #if repo head is given in config file, check whether its valid, make exception if not valid.
        for repo in self.repos:
            if valid_repo_head is True:
                repo['repo-head'] = repo_head
            else:
                if len(repo['repo-head']) == 0:
                    raise Exception("No valid repo head found for %s" % repo['repo-name'])
                else:
                    if self._is_valid_head(repo['repo-head']) is False:
                        raise Exception("Invalid repo head %s" % repo['repo-head'])

        # Checkout some random HEAD
        self._git("checkout", 'HEAD~1', silent=True)

    def clean_repo(self):
        """
        Clean the git repo and delete all local branches.
        :return: None
        """
        self.logger.info(format_h1("Cleaning repo", tab=2))
        self._git("reset", "--hard")
        self._git("clean", "-fdx")

        local_branches = [x.strip() for x in self._git('branch').splitlines()]
        for branch in local_branches:
            if branch.startswith('* '):
                continue
            self._git("branch", "-D", branch)

    def send_email(self, to='', cc='', subject_prefix='', subject='test subject',  content='test content'):
        # type: (str, str, str, str, str) -> None
        """
        Send email to given recipients mentioned in to and cc fields using given subject_prefix, subject and content.
        :param to: To addresses seperated by commas.
        :param cc: Cc addresses seperated by commas.
        :param subject_prefix: Prefix to be added to subject.
        :param subject: Subject of email message.
        :param content: Content of the email.
        :return: None
        """
        _smtp_server = self.email_options['smtp-server']
        _from = self.email_options['from']
        _to = self.email_options['to'] + ',' + to
        _cc = self.email_options['cc'] + ',' + cc
        decorate_subject = lambda s: "[ " + str(s) + " ]" if len(s) > 0 else ''
        prefix = decorate_subject(self.subject_prefix) + decorate_subject(subject_prefix)
        git_send_email(_from, _to, _cc,
                       subject=prefix + ' ' + subject,
                       content=content)

    def _compile_test(self, options):
        # type: (dict) -> boolean, str
        """
        Run selected compile tests for selected architectures.
        Supported architectures are,  i386, x86_64, arm64.
        Supported configurations are allyesconfig, allnoconfig, allmodconfig, defconfig.

        :param options: List of compile configurations. Each configuration shall have following options.

        arch_name  - Name of the architecture.
        compiler_options - Dictionary with compiler options.
                         - CC - Compiler name
                         - cflags - Array of compiler options.
        allyesconfig - Option to select allyesconfig configuration.
        allnoconfig - Option to select allnoconfig configuration.
        allmodconfig - Option to select allmodconfig configuration.
        defconfig - Option to select defconfig configuration.

        :return: Overal status of compile tests, and test output. Deafult status is True and output is empty string.
        """
        supported_archs = ['i386', 'x86_64', 'arm64']
        supported_configs = ['allyesconfig', 'allnoconfig', 'allmodconfig', 'defconfig']
        status = True

        self.logger.info(format_h1("Compile tests", tab=2))

        # Two dimensional status array arch/config
        def results_template():
            results = {}
            for arch in supported_archs:
                results[arch] = {}
                for config in supported_configs:
                    results[arch][config] = 'N/A'

            return results

        results = results_template()

        # String output with compile test results.
        def generate_results(results):
            width = len(max(supported_configs, key=len)) * 2
            out = 'Compile Test Results:\n'
            for arch in supported_archs:
                out += '\t%s results:\n' % arch
                for config in supported_configs:
                    out += ('\t\t%-' + str(width) + 's: %s\n') % (config, results[arch][config])

            return out + '\n\n'

        # For every compile configuration, run compile tests and gather results.
        for params in options:
            if params['arch_name'] not in supported_archs:
                continue
            arch = params['arch_name']

            def update_compile_results(arch, config, ret, out, err):
                if ret == 0:
                    results[arch][config] = 'Passed'
                else:
                    results[arch][config] = 'Failed'
                    self.logger.error('Compile test %s/%s failed\n\n' % (arch, config))
                    self.logger.error(err)

            for config in supported_configs:
                if params[config] is True:
                    out_dir = os.path.join(self.repo_dir, 'out', arch, config)
                    ret, out, err = 0, '', ''

                    kobj = BuildKernel(src_dir=self.repo_dir, out_dir=out_dir,
                                       arch=params['arch_name'],
                                       cc=params['compiler_options']['CC'],
                                       cflags=params['compiler_options']['cflags'],
                                       logger=self.logger)

                    getattr(kobj, 'make_' + config)()
                    ret, out, err = kobj.make_kernel()
                    update_compile_results(arch, config, ret, out, err)
                    if ret != 0:
                        status = False

        return status, generate_results(results)

    def _static_analysis(self, options):
        """
        Run static analysis tests.
        Supported tests are checkpatch, aiaiai.
        :param options:
        :return:
        """
        supported_tests = ['checkpatch', 'aiaiai']

        self.logger.info(format_h1("Static Analysis tests", tab=2))

        # Create a result list for supported test types. Default result type is 'N/A'.
        def results_template():
            results = {}
            for test in supported_tests:
                results[test] = 'N/A'

            return results

        results = results_template()

        # Generate test results string.
        def generate_results(results):
            out = 'Static Analysis Results:\n'
            width = len(max(supported_tests, key=len)) * 2
            for test in supported_tests:
                out += ('\t%-' + str(width) + 's: %s\n') % (test, results[test])

            return out + '\n\n'

        if options['checkpatch']:
            self.logger.info(format_h1("Checkpatch tests", tab=2))

        if options['aiaiai']:
            self.logger.info(format_h1("AiAiAi tests", tab=2))

        return generate_results(results)

    def _test_branch(self, branch_name, test_options):
        """
        Test given branch and return the status of tests.
        :param branch_name: Name of the kernel branch.
        :param test_options: Dict with test_options.
                profiles - List of test profiles. Supported profiles are,
                           "compile-tests",
                           "static-analysis",
                           "bat-tests".
                Options assosiated with these profiles are defined in self.test_profiles.

        :return: Status of the test.
        """
        self.logger.info(format_h1("Testing %s", tab=2) % branch_name)
        profile_list = test_options['profiles']
        status = True
        out = '\n\n'

        self._git("checkout", branch_name)

        # For every test profile, run test and gather status and output.
        for profile in profile_list:
            if profile == 'compile-tests':
                test_status, test_out = self._compile_test(self.test_profiles['compile-tests'])
                out += test_out
                if test_status is False:
                    status = False
            elif profile == 'static-analysis':
                test_status, test_out = self._static_analysis(self.test_profiles['static-analysis'])
                out += test_out
                if test_status is False:
                    status = False

        self.logger.debug(out)

        # If send-email flag is set, then send test results back to given recipients.
        if test_options['send-email'] is True:
            content = "Following is the test results for branch %s\n" % branch_name
            content += out
            self.send_email(subject_prefix=test_options['subject-prefix'], subject="Test Results", content=content)

        return status

    def _generate_output(self, head, branch_name, output_options):
        """
        Generate alternate outputs for given repo. Currently supported format is 'quilt'.
        If quilt option is selected, then following command are executed.
        git format-patch -C -M HEAD..<branch_name SHA_ID> -o quilt-folder.
        Write patch names back to series file.

        :param head: SHA ID or Tag of head of the kernel branch.
        :param branch_name: Name of the branch.
        :param output_options:
        :return:
        """

        if output_options is None:
            return

        quilt_params = output_options.get('quilt', None)

        if quilt_params is not None:
            quilt_folder = os.path.join(self.repo_dir, 'quilt')
            if quilt_params["quilt-folder"] != "":
                quilt_folder = os.path.join(self.repo_dir, quilt_params["quilt-folder"])

            self.logger.info(format_h1("Generating quilt patches in %s", tab=2) % quilt_folder)
            self.logger.info(quilt_folder)

            if os.path.exists(quilt_folder):
                rmtree(quilt_folder, ignore_errors=True)

            os.makedirs(quilt_folder)
            tail = self.git.cmd('rev-parse', branch_name)[1]
            err_code, output, err =  self.git.cmd('format-patch', '-C', '-M',
                                                        head.strip() + '..' + tail.strip(),
                                                        '-o', quilt_folder)
            if err_code == 0:
                def get_file_name(path):
                    head, tail =  os.path.split(path)
                    return tail
                with open(os.path.join(quilt_folder, 'series.txt'), 'w') as f:
                    patch_list = map(get_file_name, output.split('\n'))
                    f.write(str('\n'.join(patch_list)))


    def _config_rr_cache(self, params):
        """
        Config git re re re cache.
        :param params: Dict with rr-cache options.
            use-auto-merge - Enable rerere.autoupdate if set True, otherwise do nothing.
            use-remote-cache - Get remote cache params if set True, otherwise no remote rerere cache is available.
            remote-cache-params - Parms for remote cache.
                                - sync-protocol - Remote sync protocol (SMB, Rsync)
                                - server-name - Name of the remote server.
                                - Share-point - Name of the share folder.

        :return:
        """
        if params is None:
            return

        rr_cache_dir = os.path.join(self.repo_dir, '.git', 'rr-cache')
        rr_cache_old_dir = os.path.join(self.repo_dir, '.git', 'rr-cache.old')

        self._git("config", "rerere.enabled", "true")

        # Remove old cache
        sh = PyShell(wd=self.repo_dir, logger=self.logger)

        # Check and enable auto merge
        if params['use-auto-merge'] == True:
            self._git("config", "rerere.autoupdate", "true")

        # Check and add remote cache
        if params['use-remote-cache'] == True:
            remote_params = params['remote-cache-params']
            if os.path.exists(rr_cache_dir):
                rmtree(rr_cache_old_dir, ignore_errors=True)
                move(rr_cache_dir, rr_cache_old_dir)
            os.makedirs(rr_cache_dir)
            if remote_params['sync-protocol'] == 'smb':
                cmd = ["//" + remote_params['server-name'] + '/' + remote_params['share-point']]
                if len(remote_params['password']) > 0:
                    cmd.append(remote_params['password'])
                else:
                    cmd.append("-N")
                if len(remote_params['username']) > 0:
                    cmd.append("-U")
                    cmd.append(remote_params['username'])

                cmd = ['smbclient'] + cmd + remote_params['sync-options']
                ret, out, err = sh.cmd(*cmd, wd=rr_cache_dir)
                if ret != 0:
                    self.logger.error(ret)
                    self.logger.error(err)
                    self.logger.error(out)

    def _reset_rr_cache(self, params):
        """
        Reset git rerere cache
        :param params: Dict with remote cache related params.
        :return:
        """
        if params is None:
            return

        rr_cache_dir = os.path.join(self.repo_dir, '.git', 'rr-cache')
        rr_cache_old_dir = os.path.join(self.repo_dir, '.git', 'rr-cache.old')

        self._git("config", "rerere.enabled", "false")

        sh = PyShell(wd=self.repo_dir, logger=self.logger)

        if params.get('upload-remote-cache', False) is True and os.path.exists(rr_cache_dir):
            if params['use-remote-cache'] == True:
                remote_params = params['remote-cache-params']
                if remote_params['upload-protocol'] == 'smb':
                    cmd = ["//" + remote_params['server-name'] + '/' + remote_params['share-point']]
                    if len(remote_params['password']) > 0:
                        cmd.append(remote_params['password'])
                    else:
                        cmd.append("-N")
                    if len(remote_params['username']) > 0:
                        cmd.append("-U")
                        cmd.append(remote_params['username'])

                    cmd = ['smbclient'] + cmd + remote_params['upload-options']
                    ret, out, err = sh.cmd(*cmd, wd=os.path.join(self.repo_dir,'.git', 'rr-cache'))
                    self.logger.error(ret)
                    self.logger.error(err)
                    self.logger.error(out)

        if params['use-remote-cache'] == True  and os.path.exists(rr_cache_old_dir):
            rmtree(rr_cache_dir, ignore_errors=True)
            sh.cmd('mv', rr_cache_old_dir, rr_cache_dir)

    def _merge_branches(self, mode, merge_list, dest, params):
        """
        Merge the branches given in merge_list and create a output branch.
        Basic logic is,
        if mode is rebase, then git rebase all branches in merge_list onto to dest branch.
        if mode is merge, then git merge/pull all branches on top of dest branch.
        :param mode:  Rebase, merge, pull
        :param merge_list: List of (remote, branch) tupule.
        :param dest: Dest branch name.
        :param params: Dict with merge params.
        use-rr-cache -  Use git rerere cache.
        no-ff - Set True if you want to disable fast forward in merge.
        add-log - Set True if you want to add merge log.

        :return: True
        """
        rr_cache_params = params.get('rr-cache', None)
        if self.skip_rr_cache == False and params['use-rr-cache'] is True:
            self._config_rr_cache(rr_cache_params)
        self._git("checkout", dest)
        if mode == "merge":
            for remote, branch in merge_list:
                options = []
                if params['no-ff'] is True:
                    options.append('--no-ff')
                if params['add-log'] is True:
                    options.append('--log')
                if remote != '':
                    options.append(remote)
                    options = ["pull"] + options
                else:
                    options = ["merge"] + options
                options.append(branch)

                self._git_merge(*options, send_email=True, subject_prefix=dest, subject='Merge Failed',
                                auto_merge=params['use-rr-cache'])
        elif mode == "rebase":
            for remote, branch in merge_list:
                if remote != '':
                    self._git("checkout", remote + '/' + branch)
                else:
                    self._git("checkout", branch)
                self._git_merge("rebase", dest, send_email=True, subject_prefix=dest, subject='Rebase Failed',
                                auto_merge=params['use-rr-cache'])
                self._git("branch", '-D', dest)
                self._git("checkout", '-b', dest)

        if self.skip_rr_cache == False and params['use-rr-cache'] is True:
            self._reset_rr_cache(rr_cache_params)

        return True


    def _upload_branch(self, branch_name, upload_options):
        """
        Upload the given branch to a remote patch.
        supported upload modes are force-push, push and refs-for (for Gerrit).
        :param branch_name: Name of the local branch.
        :param upload_options: Dict with upload related params.
        url - Name of the git remote.
        branch - Remote branch of git repo.
        :return: Nothing.
        """
        self.logger.info(format_h1("Uploading %s", tab=2) % branch_name)

        if upload_options['mode'] == 'force-push':
            self._git("push", "-f", upload_options['url'], branch_name + ":" + upload_options['branch'])
        elif upload_options['mode'] == 'push':
            self._git("push", upload_options['url'], branch_name + ":" + upload_options['branch'])
        elif upload_options['mode'] == 'refs-for':
            self._git("push", upload_options['url'], branch_name + ":refs/for/" + upload_options['branch'])

    def _create_branch(self, repo):
        """
        Merge the branches given in source-list and create list of output branches as specificed by dest-list option.
        :param repo: Dict with kernel repo options. Check "repo-params" section in kernel integration schema file for
        more details.
        :return: Nothing
        """
        self.logger.info(format_h1("Create %s repo", tab=2) % repo['repo-name'])

        merge_list = []
        status = True

        # Get source branches
        for srepo in repo['source-list']:
            if srepo['skip'] is True:
                continue
            if srepo['use-local'] is True:
                if self._is_valid_local_branch(srepo['branch']) is False:
                    raise Exception("Dependent repo %s does not exits" % srepo['branch'])
                merge_list.append(('', srepo['branch']))
            else:
                merge_list.append((srepo['url'], srepo['branch']))

        # Create destination branches
        for dest_repo in repo['dest-list']:

            self._git("branch", "-D", dest_repo['local-branch'], silent=True)
            self._git("checkout", repo['repo-head'], "-b", dest_repo['local-branch'])

            if len(merge_list) > 0:
                self._merge_branches(dest_repo['merge-mode'], merge_list,
                                     dest_repo['local-branch'],
                                     dest_repo['merge-options'])

            if dest_repo['test-branch'] is True:
                test_options = dest_repo['test-options']
                status = self._test_branch(dest_repo['local-branch'], test_options)
                if status is False:
                    self.logger.error("Testing %s branch failed" % dest_repo['local-branch'])
                    break

        # Compare destination branches
        if status is True:
            if len(repo['dest-list']) > 1:
                base_repo = repo['dest-list'][0]
                for dest_repo in repo['dest-list']:
                    ret, out, err = self.git('diff', base_repo, dest_repo)
                    if ret != 0:
                        status = False
                        break
                    else:
                        if len(out) > 0:
                            status = False
                            self.logger.error("Destination branche %s!=%s" %
                                              (base_repo['local-branch'], dest_repo['local-branch']))
                            break
        else:
            self.logger.warn("Skipping destination branch comparison")

        # Upload the destination branches
        if status is True:
            for dest_repo in repo['dest-list']:
                if dest_repo['upload-copy'] is True:
                    upload_options = dest_repo['upload-options']
                    self._upload_branch(dest_repo['local-branch'], upload_options)

                if dest_repo['generate-output'] is True:
                    output_options = dest_repo['output-options']
                    self._generate_output(repo['repo-head'], dest_repo['local-branch'], output_options)
        else:
            self.logger.warn("Skipping destination branch upload")

    def _get_repo_by_name(self, name):
        """
        Get repo Dict from "repos" list in given Json config file.
        :param name: Name of the repo
        :return: repo Dict reference or None if not valid repo found.
        """
        for repo in self.repos:
            if repo['repo-name'] ==  name:
                return repo

        return None

    def _create_branches(self, repo_list=[]):
        """
        For every repo in repo_list, parse and perform kernel integration as defined by repo options.
        :param repo_list: List of repos
        :return: None
        """
        for name in repo_list:
            repo = self._get_repo_by_name(name)
            if repo == None:
                self.logger.error("Repo %s does not exist\n" % name)
                continue
            else:
                self._create_branch(repo)

    def gen_dep_branches(self, kint_branch):
        """
        Generate dependent repo's for given repo.
        :param kint_branch: Name of the repo.
        :return: None
        """
        for repo in self.kint_repos:
            if repo['kint-repo'] == kint_branch:
                self._create_branches(repo['dep-repos'])

    def gen_kint_repos(self, kint_branch=None, skip_dep=False):
        """
        Generate kernel and its depndent branches.
        :param kint_branch: Name of the kernel branch.
        :param skip_dep: Skip creating dependent branches.
        :return: None
        """
        for repo in self.kint_repos:
            if kint_branch is not None and repo['kint-repo'] != kint_branch:
                continue
            if skip_dep is False:
                self._create_branches(repo['dep-repos'])
            self._create_branches([repo['kint-repo']])

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

def setup_logging(default_path, default_level=logging.INFO, env_key='LOG_CFG'):
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

    return logging.getLogger(__name__)

def add_cli_options(parser):

    parser.add_argument('-d', '--repo-dir', action='store', dest='repo_dir',
                        type=lambda x: is_valid_dir(parser, x),
                        default=os.getcwd(),
                        help='Kerenl repo directory')
    parser.add_argument('--skip-repo-clean', action='store_true', dest='skip_repo_clean',
                        default=False,
                        help='Skip cleaning the the repo')
    parser.add_argument('--skip-dep', action='store_true', dest='skip_dep',
                        default=False,
                        help='skip creating dependent repos')
    parser.add_argument('--skip-rrcache', action='store_true', dest='skip_rr_cache',
                        default=False,
                        help='skip using git rerere cache')
    parser.add_argument('-r', '--kint-repo', action='store', dest='kint_repo_name',
                        default=None,
                        help='Integrate specific repo')
    parser.add_argument('-s', '--schema-file', action='store', dest='config_schema',
                        default=os.path.join(os.getcwd(), 'kint-configs', 'kint-schema.json'),
                        help='Kernel Integration schema file')
    parser.add_argument('--kernel-head', action='store', dest='kernel_tag',
                        default='',
                        help='SHA ID or tag of kernel HEAD')

    parser.add_argument('config', action='store', help='staging config')

if __name__ == "__main__":

    logger = setup_logging(os.path.join(os.getcwd(), 'kint-configs', 'log-config.yaml'))

    parser = argparse.ArgumentParser(description='Script used for dev-bkc/LTS Kerenl Integration')

    add_cli_options(parser)

    args = parser.parse_args()

    obj = KernelInteg(os.path.abspath(args.config), os.path.abspath(args.config_schema),
                      args.kernel_tag, args.repo_dir,
                      skip_rr_cache=args.skip_rr_cache, logger=logger)

    if args.skip_repo_clean is False:
        obj.clean_repo()

    obj.gen_kint_repos(args.kint_repo_name, args.skip_dep)
