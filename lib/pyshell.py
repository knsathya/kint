#!/usr/bin/env python

import os
import logging
from subprocess import Popen, PIPE
from threading import Thread
from Queue import Queue, Empty

GIT_COMMAND_PATH='/usr/bin/git'

class PyShell(object):
    def __init__(self, wd=os.getcwd(), stream_stdout=False, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.wd = wd
        self.stream_stdout = stream_stdout
        self.curr_cmd = None
        self.cmd_out = ''
        self.cmd_err = ''
        self.cmd_ret = 0
        self.dry_run = False

    def dryrun(self, status=False):
        self.dry_run = status

    def _cmd(self, args=[], wd=None, out_log=False, dry_run=False, shell=False):
        output = list()
        error = list()
        wd = wd if wd is not None else self.wd

        #self.logger.info(args)
        #self.logger.info('wd=%s, out_log=%s, dry_run=%s, shell=%s' % (wd, out_log, dry_run, shell))
        self.logger.debug("Executing " + ' '.join(list(args)))

        if len(args) < 0:
            return -1, '', 'Argument invalid error'

        if dry_run or self.dry_run:
            return 0, '', ''

        self.curr_cmd = args
        self.wd = wd

        io_q = Queue()
        var_q = Queue()

        def stream_watcher(identifier, stream):
            for line in stream:
                io_q.put((identifier, line))
                var_q.put((identifier, line))

            if not stream.closed:
                stream.close()

        process = Popen(list(args), stdout=PIPE, stderr=PIPE, cwd=wd, shell=shell)

        def printer():
            while True:
                try:
                    # Block for 1 second.
                    item = io_q.get(True, 1)
                except Empty:
                    # No output in either streams for a second. Are we done?
                    if process.poll() is not None:
                        break
                else:
                    identifier, line = item
                    print identifier + ':', line
                    if out_log is True:
                        self.logger.info(identifier + ': ' + line)

        def parse_output():
            while True:
                try:
                    # Block for 1 second.
                    item = var_q.get(False)
                except Empty:
                    # No output in either streams for a second. Are we done?
                    if process.poll() is not None:
                        break
                else:
                    identifier, line = item

                    if identifier == "STDERR":
                        error.append(line)
                    elif identifier == "STDOUT":
                        output.append(line)

        if self.stream_stdout is True:
            Thread(target=stream_watcher, name='stdout-watcher', args=('STDOUT', process.stdout)).start()
            Thread(target=stream_watcher, name='stderr-watcher', args=('STDERR', process.stderr)).start()
            Thread(target=printer, name='printer').start()
            parse_output()
        else:
            _output, _error = process.communicate()
            output = [_output]
            error = [_error]

            if len(_output) > 0 and out_log is True:
                self.logger.debug("STDOUT: " + _output)
            if len(_error) > 0 and out_log is True:
                self.logger.error("STDERR: " + _error)

        self.cmd_out = ''.join(output)
        self.cmd_err = ''.join(error)
        self.cmd_ret = process.returncode

        return self.cmd_ret, self.cmd_out, self.cmd_err

    def cmd(self, *args, **kwargs):
        return self._cmd(args=list(args), wd=kwargs.get('wd', self.wd),
                         out_log=kwargs.get('out_log', False),
                         dry_run=kwargs.get('dry_run', False),
                         shell=kwargs.get('shell', False))

class GitShell(PyShell):
    def cmd(self, *args, **kwargs):
        return super(GitShell, self).cmd(GIT_COMMAND_PATH, *args, **kwargs)

    def valid(self,  **kwargs):
        return True if os.path.exists(os.path.join(kwargs.get('wd', self.wd), '.git')) else False

    def init(self, **kwargs):
        if not self.valid(**kwargs):
            self.cmd('init', '.', **kwargs)

        return True, '', ''

    def add_remote(self, name, url, override=False, **kwargs):
        if override is True:
            self.cmd('remote', 'remove', name, **kwargs)
        self.cmd('remote', 'add', name, url, **kwargs)

        return True, '', ''

    def push(self, lbranch, remote, rbranch, force=False, use_refs=False, **kwargs):
        if use_refs is True:
            rbranch = 'refs/for/' + rbranch
        if force is True:
            return self.cmd('push','-f', remote, lbranch + ':' + rbranch, ** kwargs)
        else:
            return self.cmd('push', remote, lbranch + ':' + rbranch, **kwargs)

    def current_branch(self, **kwargs):
        cmd_str = GIT_COMMAND_PATH + " branch | awk -v FS=' ' '/\*/{print $NF}' | sed 's|[()]||g'"
        return super(GitShell, self).cmd(cmd_str, shell=True, **kwargs)[1].strip()

    def base_sha(self, **kwargs):
        cmd_str = GIT_COMMAND_PATH + " log --oneline | tail -1 | cut -d' ' -f1"
        ret, out, err = super(GitShell, self).cmd(cmd_str, shell=True, **kwargs)
        if ret != 0:
            return None

        return out.strip()

    def head_sha(self, **kwargs):
        cmd_str = GIT_COMMAND_PATH + " log --oneline | head -1 | cut -d' ' -f1"
        ret, out, err = super(GitShell, self).cmd(cmd_str, shell=True, **kwargs)
        if ret != 0:
            return None

        return out.strip()

if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.DEBUG)

    #sh = PyShell(wd='/home/sathya/pkroot/tmp', logger=logger)
    #sh = PyShell(wd='/home/sathya/pkroot/tmp', logger=logger)
    #cmd = ['/usr/bin/git', 'merge', '--no-ff', '--log', 'coe-tracker' 'dev/staging/camera']
    #cmd = ['/usr/bin/make', '-j32', 'ARCH=arm64',
           #'O=/mnt/disk2/CodeBase/pkroot/tmp/out/arm64/allnoconfig',
           #'-C', '/mnt/disk2/CodeBase/pkroot/tmp', 'CROSS_COMPILE=aarch64-linux-gnu-']
    #git = GitShell(wd='/home/sathya/CodeBase/linux/kernel/linux-current')
    #git.add_remote('origin1', 'https://github.com/knsathya/linux.git')
    #logger.info(git.current_branch())
    #cmd = ['show']
    #logger.info(sh.send_cmd(args=cmd))

