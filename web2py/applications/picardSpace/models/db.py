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

from gluon.tools import Auth, Crud, Service, PluginManager, prettydate
auth = Auth(db, hmac_key=Auth.get_or_create_key())
crud, service, plugins = Crud(db), Service(), PluginManager()

auth_table = db.define_table(
           auth.settings.table_user_name,
           Field('first_name', length=128, default=""),
           Field('last_name', length=128, default=""),
           Field('username', length=128, default=""),   #, unique=True),
           #Field('password', 'password', length=256, readable=False, label='Password'),
           Field('access_token', length=128, default=""),
           Field('registration_key', length=128, default= "", writable=False, readable=False))

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


#basespaceuser1 aTest-1 (app)
client_id     = 'f4e812672009413d809b7caa31aae9b4'
client_secret = 'a23bee7515a54142937d9eb56b7d6659'
baseSpaceUrl  = 'https://api.cloud-endor.illumina.com/'
version       = 'v1pre3'

# import OAuth2 account for authentication
from gluon.contrib.login_methods.oauth20_account import OAuthAccount


class BaseSpaceAccount(OAuthAccount):
    """
    OAuth2 implementation for BaseSpace
    """
    auth_url      = 'https://cloud-endor.illumina.com/oauth/authorize'    
    token_url      = baseSpaceUrl + version + '/oauthv2/token/'
    
    def __init__(self):
        OAuthAccount.__init__(self, 
            globals(),   # web2py keyword
            client_id, 
            client_secret,
            self.auth_url,
            self.token_url)            
            #state='user_login')
            
    def get_user(self):
        """
        Returns the user using the BaseSpace API            
        """
        if not self.accessToken():
            return None

        # TODO update when app session num is optional parameter
        self.bs_api = BaseSpaceAPI(client_id,client_secret,baseSpaceUrl,version,"", self.accessToken())
        
        user = None
        try:
            user = self.bs_api.getUserById("current")
        except:
            self.session.token = None
            self.bs_api = None

        if user:
            return dict(first_name = user.Name,
                        last_name = user.Email,
                        username = user.Id)

# TODO subclass accessToken due to diffs in BaseSpace OAuth2 vs web2py's
#    def accessToken(self):
            
auth.settings.login_form=BaseSpaceAccount()



#from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI


db.define_table('app_session',
    Field('app_session_num'),
    Field('project_num'),          # the BaseSpace project to write-back results
    # TODO move file_num to app_result?
    Field('file_num'),             # the BaseSpace file that was analyzed
    Field('user_id'), db.auth_user,
    Field('date_created')) 

db.define_table('app_result',
    Field('app_session_id', db.app_session),
    Field('app_result_name'),
    Field('app_result_num'),
    # TODO should project_num be in both app_session and app_result?
    Field('project_num'),         # the project that contains this app result in BaseSpace
    Field('description'),
    Field('status'),
    Field('message'))

db.define_table('bs_file',
    Field('app_result_id', db.app_result),
    Field('app_session_id', db.app_session), # TODO should this be only on the app_result? Yes
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
