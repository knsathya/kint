import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from json_parser import JSONParser
import logging
import os

class Email(object):

    def _smtp_setup(self):
        self.smtp_obj = smtplib.SMTP(host=self.smtp_server, port=self.smtp_port)

        if self.auth is not None and self.auth == 'TLS':
            self.smtp_obj.starttls()

        if self.username is not None and self.password is not None:
            self.smtp_obj.login(self.username, self.password)

        self.logger.debug("SMTP Server Open():%s port:%d\n", self.smtp_server, self.smtp_port)

    def _smtp_close(self):
        self.smtp_obj.quit()
        self.logger.debug("SMTP Server Close()\n")

    def __init__(self, smtp_server=None, smtp_port=0, auth='TLS', username=None, password=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.auth = auth
        self.username = username
        self.password = password
        self.json = None
        self.cfg = None
        self.smtp_obj = None

    def parse_json(self, cfg, schema):
        set_def = lambda x, y: self.cfg[x] if self.cfg[x] != "" else y
        self.json = JSONParser(os.path.abspath(schema), os.path.abspath(cfg),
                               extend_defaults=True, logger=self.logger)
        self.cfg = self.json.get_cfg()
        self.logger.debug(self.json.print_cfg())

        self._from = set_def('from', None)
        self._to = set_def('to', None)
        self._cc = self.cfg['cc']
        self._bcc = self.cfg['bcc']

        self.smtp_server= self.cfg['smtp-server']
        self.smtp_port = self.cfg['smtp-port']
        self.auth = set_def('smtp-authentication', None)
        self.username = set_def('smtp-username', None)
        self.password = set_def('smtp-password', None)

    def set_header(self, _from, _to, _cc='', _bcc=''):
        set_val = lambda x, y: x if x is not None and x != '' else getattr(self, y)

        #update if the field value is vaild
        self._from = set_val(_from, '_from')
        self._to = set_val(_to, '_to')
        self._cc = _cc
        self._bcc = _bcc

    def send_email(self, _from=None, _to=None, _cc='', _bcc='', subject='', content=''):

        set_val = lambda x, y: getattr(self, y) if x is None or x == '' else x

        _from = set_val(_from, '_from')
        _to = set_val(_to, '_to')
        _cc = set_val(_cc, '_cc')
        _bcc = set_val(_bcc, '_bcc')

        if _from is None or _from == '':
            self.logger.warn("Invalid from address")
            return

        if (_to is None or _to == '') and (self._to is None or self._to == ''):
            self.logger.warn("Invalid to address")
            return

        self.logger.info("From: %s\nTo: %s\nCC: %s\nBCC: %s\nSubject: %s\n",
                         _from, _to, _cc, _bcc, subject)

        self._smtp_setup()

        rcpt = map(lambda it: it.strip(), _cc.split(",") + _bcc.split(",") + [_to])

        msg = MIMEMultipart('alternative')
        msg['From'] = _from
        msg['Subject'] = subject
        msg['To'] = _to
        msg['Cc'] = _cc
        msg['Bcc'] = _bcc
        msg.attach(MIMEText(content))

        self.smtp_obj.sendmail(_from, rcpt, msg.as_string())

        self._smtp_close()


if __name__ == '__main__':

    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(message)s')
    logger.setLevel(logging.DEBUG)

    obj = Email(logger=logger)
    obj.parse_json('../config/email-sample.json', '../config/email-schema.json')
    obj.send_email(subject='testing email lib', content='Hello')


