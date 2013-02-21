# -*- coding: utf-8 -*-

db = DAL('sqlite://storage.sqlite')
from gluon import current
current.db = db

# only use secure cookies (cookie only sent over https), except when using localhost
if not request.is_local:
    session.secure()

# store sessions in the db instead on the file system
session.connect(request, response, db)

## by default give a view/generic.extension to all actions from localhost
## none otherwise. a pattern can be 'controller/function.extension'
response.generic_patterns = ['*'] if request.is_local else []

# define authentication table and setting
from gluon.tools import Auth
auth = Auth(db)

auth_table = db.define_table(
           auth.settings.table_user_name,
           Field('first_name', length=128, default=""),                                             # needed for name display in UI - contains BaseSpace full user name
           Field('email', length=128, default=""),                                                  # contains BaseSpace user email
           Field('username', length=128, default=""),                                               # reqd by web2py - contains BaseSpace user id (use this field instead of registration id)
           Field('access_token', length=128, default=""),
           Field('registration_key', length=512, default= "", writable=False, readable=False),      # not currently used
           Field('registration_id', length=512, default= "", writable=False, readable=False))       # used by web2py - also contains BaseSpace user id (use 'username' instead of registration id)

auth_table.username.requires = IS_NOT_IN_DB(db, auth_table.username)

# create all tables needed by auth if not custom tables
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

# set page that user sees after logging in, out
auth.settings.login_next = URL('user_now_logged_in')
auth.settings.logout_next = 'http://basespace.illumina.com'

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

# auto-logout - doesn't seem to be working for unknown reason
auth.settings.expiration = 3600  # seconds


# define global vars
current.aln_metrics_ext = ".AlignmentMetrics.txt"

# define app data - NOTE if changing any defaults, must manually deleted existing db entry
db.define_table('app_data',
    #Field('client_id', default='771bb853e8a84daaa79c6ce0bcb2f8e5'),                              # basespace.com, user basespaceuser1, app picardSpace
    #Field('client_secret', default='af244c8c6a674e3fb6e5280605512393'),
    #Field('baseSpaceUrl', default='https://api.basespace.illumina.com/'),
    #Field('version', default='v1pre3'),
    #Field('auth_url', default='https://basespace.illumina.com/oauth/authorize'),
    #Field('token_url', default='https://api.basespace.illumina.com/v1pre3/oauthv2/token/'),
    Field('client_id', default='9aec318fb4f7467fbfe2f88c9a3632aa'),                               # portal hoth
    Field('client_secret', default='4fee19aca5fd49e98fa60693d9fbb6ae'),                           # portal hoth    
    Field('baseSpaceUrl', default='https://api.cloud-hoth.illumina.com/'),                        # portal hoth
    Field('version', default='v1pre3'),
    Field('auth_url', default='https://cloud-hoth.illumina.com/oauth/authorize'),                 # portal hoth
    Field('token_url', default='https://api.cloud-hoth.illumina.com/v1pre3/oauthv2/token/'),      # portal hoth    
    Field('redirect_uri', default=''),
    Field('redis_host', default='localhost'),
    Field('redis_port', default=6379),
    Field('picard_exe', default='private/picard-tools-1.74/CollectAlignmentSummaryMetrics.jar'))

# create an instance of app_data table if not present
app_data = db(db.app_data.id > 0).select().first()
if not app_data:
    app_data = db.app_data.insert()


# define class for web2py login with BaseSpace credentials 
from picardSpace import get_auth_code_util, get_access_token_util

class BaseSpaceAccount(object):
    """
    OAuth2 implementation for BaseSpace
    
    When login() (in gluon/tools.py) is called, get_user() is called first to determine if a user is logged in, 
    and if not then login_url() is called to log the user into BaseSpace via Oauth2.
    
    During Oauth2, an auth code if first requested, which returns control to BaseSpace. 
    BaseSpace redirects to the redirect_uri, which is handled by a controller method, 
    which in turn calls login() again to return here, where the auth code is traded for an access token (in get_user()).
    
    Web2py login only records in the db the first access token ever encountered for a user (in addition to user name, email, and BaseSpace id). 
    Tokens that acquired outside of login, e.g. to browse a Project, are written to the user table directly and overwrite the previous token.
    
    Login() is called by the following cases:
    1. User launches from BaseSpace
    2. User logs in with 'login' button on index page (outside BaseSpace)
    3. Decorators - the controller method decorators @requires_login calls login when a user isn't logged when the method is called    
    
    Note that there is a 2nd non-login method of launching Oauth2 that is implemented in controller methods.
    """
    def __init__(self):
        app = db(db.app_data.id > 0).select().first()

        self.globals = globals()
        self.client_id = app.client_id
        self.client_secret = app.client_secret
        #self.request = self.globals['request']
        #self.session = self.globals['session']
        self.auth_url = app.auth_url
        self.token_url = app.token_url
        self.args = None
        #session.token = None

    def get_user(self):
        """
        Returns info about the user that is currently logged into PicardSpace. 
        If no user is logged in, and we have a new access token from a login attempt, call the BaseSpace API to get info about the current user.
        Otherwise return None.       
        """
        # if a user is already logged in, return user info from db
        if current.session.auth:
            user_row = db(db.auth_user.id==auth.user_id).select().first()
            
            return dict(first_name = user_row.first_name,
                        email = user_row.email,
                        username = user_row.username,
                        access_token = user_row.access_token)
                    
        # if we have a new token, get current user info
        if session.token:
            token = session.token
            
            # clear new token
            session.token = None
            
            app_ssn_num = ""
            app = db(db.app_data.id > 0).select().first()
            bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, app_ssn_num, token)
        
            user = None
            #try:
            user = bs_api.getUserById("current")
            #except:
                # TODO how to handle this error? need to handle here since get_user isn't wrapped with try except in web2py login(); redirect to error page? can't just return None since this will end in redirect loop (endless login attempts)
                #session.token = None            
        
            if user:
                return dict(first_name = user.Name,
                        email = user.Email,
                        username = user.Id,
                        access_token = token)

        # user isn't logged in, return None        
        return None
        

    def __oauth_login(self):
        '''
        If we just received an auth_code from BaseSpace, exchange this for an access token.
        (Since web2py won't update the token for an existing user, 
        set the token in a session var and once login is complete we'll store the token in the user table in the db.)
        
        Otherwise, start Oauth2 by requesting an auth code from BaseSpace.
        (BaseSpace will redirect to the redirect_uri, handled in our controller, 
        which will again call login() and we'll end up in this method again to handle the auth code)                                                        
        '''        
        # set redirect_uri if it isn't set yet (only done on very first login)
        app = db(db.app_data.id > 0).select().first()
        if not app.redirect_uri:
            if (request.is_local):                
                redirect_uri = URL('handle_redirect_uri', scheme=True, host=True, port=8000)
            else:                
                redirect_uri = URL('handle_redirect_uri', scheme=True, host=True)
            app.update_record(redirect_uri=redirect_uri)
            db.commit()
        
        
        # handle errors from BaseSpace during login        
        if request.vars.error:
            # TODO is this the best way to handle this error?
            HTTP = self.globals['HTTP']            
            raise HTTP(200, "Permission to access BaseSpace data was rejected by the user", Location=None)
                
        # just received auth code from BaseSpace, trade it for an access token
        if request.vars.code:            
            session.token = get_access_token_util(request.vars.code)           
            
            # reset login state vars
            session.login_scope = None
            session.in_login = False
            return
                        
        # start Oauth2 - get an auth code for this login, handles launch from BaseSpace and PicardSpace login button
        # TODO if user is already logged into PicardSpace, check that current BS user matches                                                                                            
        # adding state var so can return to login process from redirect uri 
        session.in_login = True

        # redirect to BaseSpace to get auth code -- will return to redirect_uri
        # TODO how to handle exception here?                                                
        #get_auth_code_util(session.login_scope)
        get_auth_code_util(scope="")                                  


    def login_url(self, next="/"):
        """
        If a user isn't logged in yet (get_user() returned None), then this is the entry point for Oauth2. 
        This is includes call from '@requires_login' method decorators when a user isn't logged in.
        """            
        self.__oauth_login()
        #return next
        return

    def logout_url(self, next="/"):
        """
        """
        session.token = None
        session.auth = None
        return next

# instantiate Oauth2 login form
auth.settings.login_form=BaseSpaceAccount()


# database naming convention:
# 'id's are local database identifiers
# 'num's are BaseSpace identifiers

# define db tables
db.define_table('app_session',
    Field('app_session_num'),
    Field('project_num'),               # the BaseSpace project that the app was launched with (redundant with input_app_result project)
    Field('user_id'), db.auth_user,
    Field('date_created'),
    Field('status'),                    
    Field('message'))                   # detail about AppSession status

db.define_table('input_app_result',     # newly created AppResult for PicardSpace's output files
#    Field('app_session_id', db.app_session),
    Field('app_result_num'),
    Field('app_result_name'),
    Field('project_num'),               # the Project that contains this app result in BaseSpace
    Field('sample_num'))                # the Sample that has a relationship to this AppResult, if any

db.define_table('input_file',
    Field('app_result_id', db.input_app_result), # the AppResult that contains this File in BaseSpace
    Field('file_num'),
    Field('file_name'),
    Field('local_path'))    

db.define_table('output_app_result',    # newly created AppResult for PicardSpace's output files
    Field('app_session_id', db.app_session),
    Field('app_result_num'),
    Field('app_result_name'),
    Field('project_num'),               # the Project that contains this app result in BaseSpace
    Field('sample_num'),                # the Sample that has a relationship to this AppResult, if any
    Field('input_file_id'), db.input_file) # the File that was used as an input to this AppResult, if any (BAM for picardSpace)   


db.define_table('output_file',
    Field('app_result_id', db.output_app_result), # the AppResult that contains this File in BaseSpace
    Field('file_num'),
    Field('file_name'),
    Field('local_path'))

#db.define_table('download_queue',
#    Field('status'),
#    Field('input_file_id', db.input_file))
#        
#db.define_table('analysis_queue',
#    Field('status'),
#    Field('message'),
#    Field('input_file_id', db.input_file))
