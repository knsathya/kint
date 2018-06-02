import subprocess
import smtplib
from email.mime.multipart import MIMEMultipart
from email.MIMEText import MIMEText
import tempfile

GIT_CMD='/usr/bin/git'

set_val = lambda val, def_val: def_val if val is None else val

def exec_cmd(args):
    pipes = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    std_out, std_err = pipes.communicate()
    if pipes.returncode != 0:
        err_msg = "%s. Code: %s" % (std_err.strip(), pipes.returncode)

    return std_out

def send_email(From, to='', cc='', bcc='', subject='', content='',
               smtp_server='localhost', smtp_port=0, smtp_auth=None, username=None, password=None):

    server = smtplib.SMTP(smtp_server, smtp_port)
    if smtp_auth is not None:
        if smtp_auth == "tls":
            server.starttls()
        if username is not None:
            server.login(username, password)

    rcpt = map(lambda it: it.strip(), cc.split(",") + bcc.split(",") + [to])

    msg = MIMEMultipart('alternative')
    msg['From'] = From
    msg['Subject'] = subject
    msg['To'] = to
    msg['Cc'] = cc
    msg['Bcc'] = bcc
    msg.attach(MIMEText(content))

    server.sendmail(From, rcpt, msg.as_string())
    server.quit()


def git_send_email(From=None, to_list=None, cc_list=None, reply_to=None, subject=None, content=None,
                   annotate=False, confirm=False):

    _from = set_val(From, exec_cmd([GIT_CMD, 'config', 'user.email']))
    _to = set_val(to_list, _from)
    _cc = set_val(cc_list, '')

    sub_list = ['Subject:']
    sub_list += [set_val(subject, 'test subject')]
    _subject = ' '.join(sub_list) + '\n'

    _content = set_val(content, 'test content') + '\n'

    send_cmd = [GIT_CMD, "send-email", "--no-thread"]

    add_option = lambda x, y: send_cmd.append( x + "=" + y)

    smtp_server = exec_cmd([GIT_CMD, 'config', 'sendemail.smtpserver'])
    add_option("--smtp-server", smtp_server.strip())
    add_option("--from", _from)

    for to in _to.split(','):
        if to != '':
            add_option("--to", to)

    for cc in _cc.split(','):
        if cc != '':
            add_option("--cc", cc)

    if reply_to is not None:
        if reply_to != '':
            add_option("--in-reply-to", reply_to)

    if confirm is True:
        add_option("--confirm", "always")

    if annotate is True:
        send_cmd.append("--annotate")

    temp = tempfile.NamedTemporaryFile(mode='w+t')
    temp.writelines([_subject, '\n', _content,])
    temp.seek(0)

    send_cmd.append(temp.name)

    subprocess.check_call(send_cmd)

    temp.close()

    #return subprocess.check_call(send_cmd)




if __name__ == "__main__":

    '''
    send_email("sathyanarayanan.kuppuswamy@intel.com", "sathyanarayanan.kuppuswamy@intel.com",
               "sathyanarayanan.kuppuswamy@linux.intel.com, sathyaosid@gmail.com",
               subject='Test Subject',
               content='Test Content',
               smtp_server='smtp.intel.com')
    '''
    git_send_email(confirm=True)