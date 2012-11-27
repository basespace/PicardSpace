# -*- coding: utf-8 -*-

db = DAL('sqlite://storage.sqlite')
from gluon import current
current.db = db

## by default give a view/generic.extension to all actions from localhost
## none otherwise. a pattern can be 'controller/function.extension'
response.generic_patterns = ['*'] if request.is_local else []
## (optional) optimize handling of static files
# response.optimize_css = 'concat,minify,inline'
# response.optimize_js = 'concat,minify,inline'

#########################################################################
## Here is sample code if you need for
## - email capabilities
## - authentication (registration, login, logout, ... )
## - authorization (role based authorization)
## - services (xml, csv, json, xmlrpc, jsonrpc, amf, rss)
## - old style crud actions
## (more options discussed in gluon/tools.py)
#########################################################################

from gluon.tools import Auth
auth = Auth(db)

auth_table = db.define_table(
           auth.settings.table_user_name,
           Field('first_name', length=128, default=""), # 'first_name' needed for name display in UI
           Field('email', length=128, default=""),
           Field('username', length=128, default=""),   # reqd by web2py
           #Field('password', 'password', length=256, readable=False, label='Password'),
           Field('access_token', length=128, default=""),
           Field('registration_key', length=512, default= "", writable=False, readable=False),
           #Field('reset_password_key', length=512, default= "", writable=False, readable=False),
           Field('registration_id', length=512, default= "", writable=False, readable=False)) # needed by web2py

auth_table.username.requires = IS_NOT_IN_DB(db, auth_table.username)

## create all tables needed by auth if not custom tables
auth.define_tables()

# disable auth actions not wanted
auth.settings.actions_disabled.append('register')
auth.settings.actions_disabled.append('profile')
auth.settings.actions_disabled.append('change_password')
auth.settings.actions_disabled.append('verify_email')
auth.settings.actions_disabled.append('retrieve_username')
auth.settings.actions_disabled.append('request_reset_password')
auth.settings.actions_disabled.append('impersonate')
auth.settings.actions_disabled.append('groups')

# set page that user sees after logging in
auth.settings.login_next = URL('user_now_logged_in')

#auth.settings.on_failed_authorization = URL('index')
#auth.settings.on_failed_authentication = URL('index')

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True


# cloud-endor, user basespaceuser1, app aTest-1
#client_id     = 'f4e812672009413d809b7caa31aae9b4'
#client_secret = 'a23bee7515a54142937d9eb56b7d6659'
#baseSpaceUrl  = 'https://api.cloud-endor.illumina.com/'
#version       = 'v1pre3'
#auth_url      = 'https://cloud-endor.illumina.com/oauth/authorize'    
#token_url     =

# define app data - NOTE if changing any defaults, must manually deleted existing db entry
# basespace.com, user basespaceuser1, app picardSpace
db.define_table('app_data',
    Field('client_id', default='771bb853e8a84daaa79c6ce0bcb2f8e5'),
    Field('client_secret', default='af244c8c6a674e3fb6e5280605512393'),
    Field('baseSpaceUrl', default='https://api.basespace.illumina.com/'),
    Field('version', default='v1pre3'),
    Field('auth_url', default='https://basespace.illumina.com/oauth/authorize'),
    Field('token_url', default='https://api.basespace.illumina.com/v1pre3/oauthv2/token/'),
    Field('picard_exe', default='private/picard-tools-1.74/CollectAlignmentSummaryMetrics.jar'))

# create an instance of app_data table if not present
app_data = db(db.app_data.id > 0).select().first()
if not app_data:
    app_data = db.app_data.insert()



import json
from urllib import urlencode

class BaseSpaceAccount(object):
    """
    OAuth2 implementation for BaseSpace
    """
    def __init__(self):
        app = db(db.app_data.id > 0).select().first()

        self.globals = globals()
        self.client_id = app.client_id
        self.client_secret = app.client_secret
        self.request = self.globals['request']
        self.session = self.globals['session']
        self.auth_url = app.auth_url
        self.token_url = app.token_url
        self.args = None

    def get_user(self):
        """
        Returns the user using the BaseSpace API            
        """
        if not self.accessToken():
            return None

        # TODO update when app session num is optional parameter
        app = db(db.app_data.id > 0).select().first()
        self.bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,"", self.accessToken())
        
        user = None
        try:
            user = self.bs_api.getUserById("current")
        except:
            self.session.token = None
            self.bs_api = None

        if user:
            return dict(first_name = user.Name,
                        email = user.Email,
                        username = user.Id,
                        access_token = self.accessToken())


    def __build_url_opener(self, uri):
        """Build the url opener for managing HTTP Basic Athentication"""
        # Create an OpenerDirector with support for Basic HTTP Authentication...
        auth_handler = urllib2.HTTPBasicAuthHandler()
        auth_handler.add_password(None,
                                  uri,
                                  self.client_id,
                                  self.client_secret)
        opener = urllib2.build_opener(auth_handler)
        return opener


    def accessToken(self):
        """Return the access token generated by the authenticating server.

        If token is already in the session that one will be used.
        Otherwise the token is fetched from the auth server.

        """
        if self.session.token and self.session.token.has_key('expires'):
            expires = self.session.token['expires']
            # reuse token until expiration
            if expires == 0 or expires > time.time():
                        return self.session.token['access_token']
        if self.session.code:
            data = dict(client_id=self.client_id,
                        client_secret=self.client_secret,
                        redirect_uri=self.session.redirect_uri,
                        response_type='token', code=self.session.code,
                        grant_type='authorization_code')
                        # BaseSpace mod: added grant_type


            if self.args:
                data.update(self.args)
            open_url = None
            opener = self.__build_url_opener(self.token_url)
            try:
                open_url = opener.open(self.token_url, urlencode(data))
            except urllib2.HTTPError, e:
                raise Exception(e.read())
            finally:
                del self.session.code # throw it away

            if open_url:
                try:
                    # BaseSpace mod: BS uses json, old code used query str
                    tokendata = json.loads(open_url.read())
                    self.session.token = tokendata
                    #test2 = open_url.read()
                    #tokendata = cgi.parse_qs(open_url.read())
                    #self.session.token = dict([(k,v[-1]) for k,v in tokendata.items()])

                    # set expiration absolute time try to avoid broken
                    # implementations where "expires_in" becomes "expires"
                    if self.session.token.has_key('expires_in'):
                        exps = 'expires_in'
                    else:
                        exps = 'expires'
                    # BaseSpace mod: editing expires since BaseSpace doesn't return this
                    #self.session.token['expires'] = int(self.session.token[exps]) + \
                        #time.time()
                    self.session.token['expires'] = 0


                finally:
                    opener.close()
                return self.session.token['access_token']

        self.session.token = None
        return None


    def __oauth_login(self, next):
        '''This method redirects the user to the authenticating form
        on authentication server if the authentication code
        and the authentication token are not available to the
        application yet.

        Once the authentication code has been received this method is
        called to set the access token into the session by calling
        accessToken()
        '''
        if not self.accessToken():
            # TODO handle 'canceled' login from oauth2
            if self.request.vars.error:
                HTTP = self.globals['HTTP']
                raise HTTP(200,
                           "Permission to access BaseSpace data was rejected by the user",
                           Location=None)
            elif not self.request.vars.code:
                self.session.redirect_uri=self.__redirect_uri(next)
                data = dict(redirect_uri=self.session.redirect_uri,
                                  response_type='code',
                                  client_id=self.client_id)
                # BaseSpace mod: adding scope for project browse in addtn to login
                if self.session.scope:
                    data['scope'] = self.session.scope

                if self.args:
                    data.update(self.args)
                auth_request_url = self.auth_url + "?" +urlencode(data)
                HTTP = self.globals['HTTP']
                raise HTTP(307,
                           "You are not authenticated: you are being redirected to the <a href='" + auth_request_url + "'> authentication server</a>",
                           Location=auth_request_url)
            else:
                self.session.code = self.request.vars.code
                self.accessToken()
                return self.session.code
        return None


    ### methods below here not modified for BaseSpace

    def __redirect_uri(self, next=None):
        """Build the uri used by the authenticating server to redirect
        the client back to the page originating the auth request.
        Appends the _next action to the generated url so the flows continues.
        """

        r = self.request
        http_host=r.env.http_x_forwarded_for
        if not http_host: http_host=r.env.http_host

        url_scheme = r.env.wsgi_url_scheme
        if next:
            path_info = next
        else:
            path_info = r.env.path_info
        uri = '%s://%s%s' %(url_scheme, http_host, path_info)
        if r.get_vars and not next:
            uri += '?' + urlencode(r.get_vars)
        return uri


    def login_url(self, next="/"):
        self.__oauth_login(next)
        return next

    def logout_url(self, next="/"):
        del self.session.token
        return next


auth.settings.login_form=BaseSpaceAccount()



db.define_table('app_session',
    Field('app_session_num'),
    Field('project_num'),          # the BaseSpace project to write-back results
    Field('user_id'), db.auth_user,
    Field('date_created')) 

db.define_table('app_result',      # newly created AppResult for PicardSpace's output files
    Field('app_session_id', db.app_session),
    Field('app_result_name'),
    Field('app_result_num'),
    Field('project_num'),         # the project that contains this app result in BaseSpace
    Field('sample_num'),
    Field('status'),
    Field('message'))

db.define_table('bs_file',
    Field('app_result_id', db.app_result),
    Field('file_num'),
    Field('file_name'),
    Field('local_path'),
    Field('io_type'))   # 'input' or 'output' from an appResult

db.define_table('download_queue',
    Field('status'),
    Field('app_result_id', db.app_result))
        
db.define_table('analysis_queue',
    Field('status'),
    Field('message'),
    Field('app_result_id', db.app_result))
