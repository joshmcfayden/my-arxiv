from contextlib import contextmanager

import os
import re
import pickle
import tempfile
import dateutil,dateutil.parser

# global settings
# -----------------------------------------------------------------------------
class Config(object):
    # main paper information repo file
    db_path = 'db.p'
    # intermediate processing folders
    pdf_dir = os.path.join('data', 'pdf')
    txt_dir = os.path.join('data', 'txt')
    thumbs_dir = os.path.join('static', 'thumbs')
    # intermediate pickles
    tfidf_path = 'tfidf.p'
    meta_path = 'tfidf_meta.p'
    sim_path = 'sim_dict.p'
    user_sim_path = 'user_sim.p'
    # sql database file
    db_serve_path = 'db2.p' # an enriched db.p with various preprocessing info
    database_path = 'as.db'
    serve_cache_path = 'serve_cache.p'
    
    beg_for_hosting_money = 1 # do we beg the active users randomly for money? 0 = no.
    banned_path = 'banned.txt' # for twitter users who are banned
    tmp_dir = 'tmp'

# Context managers for atomic writes courtesy of
# http://stackoverflow.com/questions/2333872/atomic-writing-to-file-with-python
@contextmanager
def _tempfile(*args, **kws):
    """ Context for temporary file.

    Will find a free temporary filename upon entering
    and will try to delete the file on leaving

    Parameters
    ----------
    suffix : string
        optional file suffix
    """

    fd, name = tempfile.mkstemp(*args, **kws)
    os.close(fd)
    try:
        yield name
    finally:
        try:
            os.remove(name)
        except OSError as e:
            if e.errno == 2:
                pass
            else:
                raise e


@contextmanager
def open_atomic(filepath, *args, **kwargs):
    """ Open temporary file object that atomically moves to destination upon
    exiting.

    Allows reading and writing to and from the same filename.

    Parameters
    ----------
    filepath : string
        the file path to be opened
    fsync : bool
        whether to force write the file to disk
    kwargs : mixed
        Any valid keyword arguments for :code:`open`
    """
    fsync = kwargs.pop('fsync', False)

    with _tempfile(dir=os.path.dirname(filepath)) as tmppath:
        with open(tmppath, *args, **kwargs) as f:
            yield f
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        os.rename(tmppath, filepath)

def safe_pickle_dump(obj, fname):
    with open_atomic(fname, 'wb') as f:
        pickle.dump(obj, f, -1)


# arxiv utils
# -----------------------------------------------------------------------------

def strip_version(idstr):
    """ identity function if arxiv id has no version, otherwise strips it. """
    parts = idstr.split('v')
    return parts[0]

# "1511.08198v1" is an example of a valid arxiv id that we accept
def isvalidid(pid):
  return re.match('^\d+\.\d+(v\d+)?$', pid)

def print_entry(db,entry,filters=[]):
    # render time information nicely
    timestruct = dateutil.parser.parse(db[entry]['updated'])
    published_time = '%s/%s/%s' % (timestruct.month, timestruct.day, timestruct.year)

    authors=", ".join([author['name'] for author in db[entry]['authors']])
    if 'LHCb collaboration' in authors:
        authors='LHCb collaboration'

    cat=db[entry]["arxiv_primary_category"]["term"]

    text=f"""
----------------------------------------------------------
{db[entry]["title"]}
{entry} [{cat}]
{published_time}
{authors}
{db[entry]['summary']}
"""

    # Add some colour highlighting of category
    print(cat)
    htmlcat=cat
    if cat=="hep-ex":
        htmlcat='<span style="color:darkred;">['+cat+']</span>'
    elif cat=="hep-ph":
        htmlcat='<span style="color:darkgreen;">['+cat+']</span>'
    elif cat=="hep-th":
        htmlcat='<span style="color:darkblue;">['+cat+']</span>'
    else:
        htmlcat='<span style="color:gray;">['+cat+']</span>'

    htmlentry=f'<a href="https://arxiv.org/abs/{entry}">{entry}</a>'

    title=db[entry]["title"]
    
    html=f"""
<hr>
<h3>{db[entry]["title"]}</h3>
{htmlentry}  {htmlcat}  {published_time}<br>
<p><b>{authors}</b></p>
<p style="font-size:0.9em;">{db[entry]['summary']}</p>
<br>
"""

    # Highlight all of title if any filter is matched
    ismatched=False
    for filt in filters:
        if filt in html:
            html=html.replace(filt,f'<span style="color:red;">{filt}</span>')
            title=title.replace(filt,f'<span style="color:red;">{filt}</span>')
            ismatched=True

    if ismatched:
        html=html.replace(title,f'<h3 style="color:red;">{db[entry]["title"]}</h3>')

        
    print(text)
    #print(html)
    
    return text,html,ismatched

def send_email(subject,text,html):

    import smtplib

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    
    # me == my email address
    # you == recipient's email address
    me = "josh.mcfayden@gmail.com"
    you = "mcfayden@cern.ch"
    
    # Create message container - the correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = me
    msg['To'] = you
    

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)

    # Send the message via local SMTP server.
    #s = smtplib.SMTP('smtp.gmail.com',587)
    #s.ehlo()
    #s.starttls()
    s = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    gmail_password='!j0l65MIUyj3'
    s.login(me, gmail_password)

    # sendmail function takes 3 arguments: sender's address, recipient's address
    # and message to send - here it is sent as one string.
    s.sendmail(me, you, msg.as_string())
    s.quit()
