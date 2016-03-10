from __future__ import absolute_import
import os
from lxml import html
import urllib2
import uuid
import shutil

from flask import render_template
from flask import request
from flask import flash
import flask_admin

from .autologin import AutoLogin
from .forms import LoginForm
from .app import app, db, server_path
from .login_keychain import KeychainItemAdmin, KeychainItem


# Add the admin
admin = flask_admin.Admin(app, template_mode='bootstrap3')
admin.add_view(KeychainItemAdmin(KeychainItem, db.session))


def flash_errors(form):
    """
    Method for displaying flash messages with form errors.
    Pass the form as a parameter.
    """
    for field, errors in form.errors.items():
        for error in errors:
            flash(
                u"Error in the %s field - %s" % (
                    getattr(form, field).label.text, error),
                'danger'
            )


def delete_directory_files(directory_path):
    """
    Method for deleting temporary html files created by
    show in browser process.
    """
    for file_object in os.listdir(directory_path):
        file_object_path = os.path.join(directory_path, file_object)
        if os.path.isfile(file_object_path):
            os.unlink(file_object_path)
        else:
            shutil.rmtree(file_object_path)


def download_page(url, cookie_jar):
    """
    Request page using authenticated cookies (cookiejar).
    Download html source and save in browser directory, to
    be used by in show_in_browser().
    """
    user_agent = (
            'Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Ubuntu Chromium/43.0.2357.130 '
            'Chrome/43.0.2357.130 Safari/537.36'
    )
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,'
        'application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en',
    }
    browser_dir = os.path.join(server_path, 'static/browser')
    delete_directory_files(browser_dir)
    filename = '{}.html'.format(uuid.uuid4())
    filepath = os.path.join(browser_dir, filename)
    opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookie_jar))
    req = urllib2.Request(url, headers=headers)
    try:
        response = opener.open(req, timeout=10)
    except urllib2.URLError as e:
        return e
    except ValueError as e:
        return ('error', e)
    html_source = response.read()
    doc = html.document_fromstring(html_source)

    f = open(filepath, 'w+')
    f.write(html.tostring(doc))
    f.close()
    return ('ok', filename)


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main app route.
    Hosts form used for testing autologin.
    User can submit credentials and URL,
    authenticated cookies returned.
    Also makes a request using extracted cookies,
    saves the source and allows you to view in browser.
    Useful for checking whether login was successful.
    """
    form = LoginForm(request.form)
    auto_login = AutoLogin()
    login_cookies = None
    login_links = None
    filename = None
    # Process form submission
    if request.method == 'POST' and form.validate():
        msg = 'Login requested for '
        msg += '{} '.format(form.url.data)
        msg += 'with username={} and '.format(form.username.data)
        msg += 'password={}'.format(form.password.data)
        # Grab html for login page
        html_source = auto_login.get_html(form.url.data)
        # Attempt login
        login_cookie_jar = auto_login.auth_cookies_from_html(
            html_source=html_source,
            username=form.username.data,
            password=form.password.data,
            base_url=form.url.data
        )
        # If we've extracted some cookies,
        # use them to request a page and download html source
        # for viewing in browser,
        if login_cookie_jar is not None:
            download = download_page(form.url.data, auto_login.cookie_jar)
            login_cookies = login_cookie_jar.__dict__
            if download[0] != 'ok':
                flash(download, 'danger')
            else:
                flash(msg, 'success')
                filename = download[1]
        else:
            flash('No login form found', 'danger')
            login_links = auto_login.extract_login_links(html_source)
            if len(login_links) > 0:
                flash('{} login links found'.format(len(login_links)), 'success')
            else:
                flash('No login links found', 'danger')
    else:
        flash_errors(form)
    return render_template(
        'index.html',
        form=form,
        login_cookies=login_cookies,
        login_links=login_links,
        filename=filename
    )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    db.create_all()
    app.run(args.host, args.port, debug=args.debug, threaded=True)
