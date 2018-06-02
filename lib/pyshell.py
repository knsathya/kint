#!/usr/bin/env python

import os
import logging
from subprocess import Popen, PIPE
from threading import Thread
from Queue import Queue, Empty

GIT_COMMAND_PATH='/usr/bin/git'

class Command(object):
    def __init__(self, cmd=[], wd=None):
        self.cmd = cmd
        self.wd = wd
        self.out = ''
        self.err = ''
        self.ret = 0

    def curr_cmd(self):
        return self.cmd

    def err_code(self):
        return self.ret

    def cmd_out(self):
        return self.out

    def cmd_err(self):
        return self.err

class PyShell(object):
    def __init__(self, wd=os.getcwd(),  stream_stdout=False, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.wd = wd
        self.stream_stdout = stream_stdout
        self.curr_cmd = Command(wd=wd)

    def send_cmd(self, args=[], wd=None, out_log=False):
        output = list()
        error = list()
        wd = wd if wd is not None else self.wd

        self.logger.info("Executing " + ' '.join(list(args)))

        if len(args) < 0:
            return

        self.curr_cmd.cmd = args
        self.curr_cmd.wd = wd

        io_q = Queue()
        var_q = Queue()

        def stream_watcher(identifier, stream):
            for line in stream:
                io_q.put((identifier, line))
                var_q.put((identifier, line))

            if not stream.closed:
                stream.close()

        process = Popen(list(args), stdout=PIPE, stderr=PIPE, cwd=wd)

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

        self.curr_cmd.out = ''.join(output)
        self.curr_cmd.err = ''.join(error)
        self.curr_cmd.ret = process.returncode

        return self.curr_cmd.ret, self.curr_cmd.out, self.curr_cmd.err

class GitShell(PyShell):
    def send_cmd(self, args=[], wd=None):
        git_args = [GIT_COMMAND_PATH] +  args
        return super(GitShell, self).send_cmd(args=git_args, wd=wd)


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.INFO)

    #sh = PyShell(wd='/home/sathya/pkroot/tmp', logger=logger)
    sh = PyShell(wd='/home/sathya/pkroot/tmp', logger=logger)
    #cmd = ['/usr/bin/git', 'merge', '--no-ff', '--log', 'coe-tracker' 'dev/staging/camera']
    cmd = ['/usr/bin/make', '-j32', 'ARCH=arm64',
           'O=/mnt/disk2/CodeBase/pkroot/tmp/out/arm64/allnoconfig',
           '-C', '/mnt/disk2/CodeBase/pkroot/tmp', 'CROSS_COMPILE=aarch64-linux-gnu-']
    #cmd = ['show']
    logger.info(sh.send_cmd(args=cmd))

