# -*- coding: utf-8 -*-
import os.path    
import sys
from urlparse import urlparse
from ConfigParser import ConfigParser
from gluon import current, HTTP
from gluon.tools import Auth
from gluon.scheduler import Scheduler
from picardSpace import get_auth_code_util, get_access_token_util, analyze_bs_file # needed for scheduler

# get database info, from local file if present
db_info_path = os.path.join(request.folder, 'private', 'ticket_storage.txt')
if os.path.isfile(db_info_path):
    try:
        with open (db_info_path, 'r') as DBF:    
            db = DAL(DBF.readline().strip()) #, fake_migrate_all=True)
    except IOError as e:
        sys.stderr.write("Error opening database info file " + str(e) + "\n")
        sys.exit(-1)
else:
    db=DAL('sqlite://storage.sqlite')
current.db = db

# get settings from local file
settings_path = os.path.join(request.folder, 'private', 'PicardSpaceSettings.txt')
if os.path.isfile(settings_path):
    try:
        config = ConfigParser()
        config.read(settings_path)        
    except IOError as e:
        sys.stderr.write("Error opening PicardSpace settings file " + str(e) + "\n")
        sys.exit(-1)
    current.genomes_path = config.get('PicardSpaceSettings', 'genomes_path')
    current.scratch_path = config.get('PicardSpaceSettings', 'scratch_path')
    current.picard_path = config.get('PicardSpaceSettings', 'picard_path')
else:
    current.genomes_path = os.path.join(request.folder, 'private', 'genomes')
    current.scratch_path = os.path.join(request.folder, 'private', 'downloads')
    current.picard_path = os.path.join(request.folder, 'private', 'picard-tools-1.92')

# instantiate web2py Scheduler
scheduler = Scheduler(db, heartbeat=1) # override heartbeat to check for tasks every 1 sec (instead of 3 secs)
current.scheduler = scheduler

# only use secure cookies (cookie only sent over https), except when using localhost
if not request.is_local:
    session.secure()

# store sessions in the db instead on the file system
session.connect(request, response, db)

## by default give a view/generic.extension to all actions from localhost
## none otherwise. a pattern can be 'controller/function.extension'
response.generic_patterns = ['*'] if request.is_local else []

# define authentication table and setting
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

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

# auto-logout - doesn't seem to be working for unknown reason
auth.settings.expiration = 3600  # seconds


# define global vars
current.debug_ps = False
current.product_names = {'AlignmentQC':'AlignmentQC'}
#current.file_ext = {'mult_metrics_stdout': '.multiple.metrics.stdout.txt',
#                    'mult_metrics_stderr': '.multiple.metrics.stderr.txt',
#                    'aln_txt': '.alignment_summary_metrics.txt', # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
#                    'aln_stdout': '.alignment_metrics.stdout.txt', # not used by CollectMultipleMetrics
#                    'aln_stderr': '.alignment_metrics.stderr.txt', # not used by CollectMultipleMetrics
#                    'old_aln_txt': '.AlignmentMetrics.txt', # for back compat with existing AppResults
#                    'old_aln_stderr': '.stderr.txt', # for back compat with existing AppResults                
#                    'qual_by_cycle_txt': '.quality_by_cycle_metrics.txt', # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
#                    'qual_by_cycle_pdf': '.quality_by_cycle.pdf', # fixed from CollectMultipleMetrics
#                    'qual_by_cycle_png': '.quality_by_cycle.png', # convert pdf to png
#                    'qual_by_cycle_stdout': '.qual_by_cycle.stdout.txt', # not used by CollectMultipleMetrics
#                    'qual_by_cycle_stderr': '.qual_by_cycle.stderr.txt', # not used by CollectMultipleMetrics
#                    'qual_dist_txt': '.quality_distribution_metrics.txt', # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
#                    'qual_dist_pdf': '.quality_distribution.pdf', # fixed from CollectMultipleMetrics
#                    'qual_dist_png': '.quality_distribution.png', # convert pdf to png
#                    'qual_dist_stdout': '.qual_distribution.stdout.txt', # not used by CollectMultipleMetrics
#                    'qual_dist_stderr': '.qual_distribution.stderr.txt', # not used by CollectMultipleMetrics
#                    'gc_bias_txt': '.gc_bias_metrics.txt',
#                    'gc_bias_pdf': '.gc_bias_metrics.pdf',
#                    'gc_bias_png': '.gc_bias_metrics.png', # convert pdf to png
#                    'gc_bias_summary': '.gc_bias_metrics.summary_metrics.txt',
#                    'gc_bias_stdout': '.gc_bias_metrics.stdout.txt',
#                    'gc_bias_stderr': '.gc_bias_metrics.stderr.txt',
#                    'insert_size_txt': '.insert_size_metrics.txt', # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
#                    'insert_size_hist': '.insert_size_histogram.pdf', # fixed from CollectMultipleMetrics
#                    'insert_size_png': '.insert_size_histogram.png', # convert pdf to png
#                    'insert_size_stdout': '.insert_size_metrics.stdout.txt', # not used by CollectMultipleMetrics
#                    'insert_size_stderr': '.insert_size_metrics.stderr.txt', # not used by CollectMultipleMetrics
#                    }        

# file extensions for output files; the first extension in each list is used for newly created files
# NOTE that after the db table is created, changes to this list be made manually in the db
file_exts =[{'name':'mult_metrics_stdout', 'exts': [ '.multiple.metrics.stdout.txt'] },
            {'name':'mult_metrics_stderr', 'exts': ['.multiple.metrics.stderr.txt']},
            {'name':'aln_txt', 'exts': ['.alignment_summary_metrics.txt', '.AlignmentMetrics.txt']}, # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
            {'name':'aln_stdout', 'exts': ['.alignment_metrics.stdout.txt']}, # not used by CollectMultipleMetrics
            {'name':'aln_stderr', 'exts': ['.alignment_metrics.stderr.txt', '.stderr.txt']}, # not used by CollectMultipleMetrics                                    
            {'name':'qual_by_cycle_txt', 'exts': ['.quality_by_cycle_metrics.txt']}, # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
            {'name':'qual_by_cycle_pdf', 'exts': ['.quality_by_cycle.pdf']}, # fixed from CollectMultipleMetrics
            {'name':'qual_by_cycle_png', 'exts': ['.quality_by_cycle.png']}, # convert pdf to png
            {'name':'qual_by_cycle_stdout', 'exts': ['.qual_by_cycle.stdout.txt']}, # not used by CollectMultipleMetrics
            {'name':'qual_by_cycle_stderr', 'exts': ['.qual_by_cycle.stderr.txt']}, # not used by CollectMultipleMetrics
            {'name':'qual_dist_txt', 'exts': ['.quality_distribution_metrics.txt']}, # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
            {'name':'qual_dist_pdf', 'exts': ['.quality_distribution.pdf']}, # fixed from CollectMultipleMetrics
            {'name':'qual_dist_png', 'exts': ['.quality_distribution.png']}, # convert pdf to png
            {'name':'qual_dist_stdout', 'exts': ['.qual_distribution.stdout.txt']}, # not used by CollectMultipleMetrics
            {'name':'qual_dist_stderr', 'exts': ['.qual_distribution.stderr.txt']}, # not used by CollectMultipleMetrics
            {'name':'gc_bias_txt', 'exts': ['.gc_bias_metrics.txt']},
            {'name':'gc_bias_pdf', 'exts': ['.gc_bias_metrics.pdf']},
            {'name':'gc_bias_png', 'exts': ['.gc_bias_metrics.png']}, # convert pdf to png
            {'name':'gc_bias_summary', 'exts': ['.gc_bias_metrics.summary_metrics.txt']},
            {'name':'gc_bias_stdout', 'exts': ['.gc_bias_metrics.stdout.txt']},
            {'name':'gc_bias_stderr', 'exts': ['.gc_bias_metrics.stderr.txt']},
            {'name':'insert_size_txt', 'exts': ['.insert_size_metrics.txt']}, # fixed from CollectMultipleMetrics, '.txt' added by PicardSpace
            {'name':'insert_size_hist', 'exts': ['.insert_size_histogram.pdf']}, # fixed from CollectMultipleMetrics
            {'name':'insert_size_png', 'exts': ['.insert_size_histogram.png']}, # convert pdf to png
            {'name':'insert_size_stdout', 'exts': ['.insert_size_metrics.stdout.txt']}, # not used by CollectMultipleMetrics
            {'name':'insert_size_stderr', 'exts': ['.insert_size_metrics.stderr.txt']}, # not used by CollectMultipleMetrics
            {'name':'timing', 'exts': ['timing.txt']}
           ]        

db.define_table('file_type',
    Field('name'),    
    Field('exts', 'list:string')) # the first list entry is used for newly created files

# populate output_file_type table if not done already
file_type = db(db.file_type.id > 0).select().first()
if not file_type:    
    db.file_type.bulk_insert(file_exts)



# genomes keyed by BaseSpace genome id
#current.genomes = {                   
#   '3': 'Escherichia_coli_K_12_DH10B/NCBI/2008-03-17',
#   '4': 'Homo_sapiens/UCSC/hg19',
#   '5': 'Mus_musculus/UCSC/mm9',
#   '6': 'PhiX/Illumina/RTA',
#   '7': 'Rhodobacter_sphaeroides_2.4.1/NCBI/2005-10-07',                   
#   '12': 'Bacillus_cereus_ATCC_10987/NCBI/2004-02-13' }
#current.unsupported_genomes = {
#   '1': 'Arabidopsis thaliana',
#   '2': 'Bos taurus',                                      
#   '8': 'Rattus norvegicus',
#   '9': 'Saccharomyces cerevisiae',
#   '10': 'Staphylococcus aureus',
#   '11': 'N.A.' }

# define app data - 
# NOTE - on initial install, must configure client_id, client_secret, and redirect_uri (and product(s) in product table)
db.define_table('app_data',
    Field('client_id'),
    Field('client_secret'),    
    Field('baseSpaceUrl', default='https://api.cloud-hoth.illumina.com/'),
    Field('version', default='v1pre3'),
    Field('auth_url', default='https://cloud-hoth.illumina.com/oauth/authorize'),
    Field('token_url', default='https://api.cloud-hoth.illumina.com/v1pre3/oauthv2/token/'),    
    Field('redirect_uri', default='http://localhost:8000/PicardSpace/default/handle_redirect_uri'),
    Field('store_url', default='https://hoth-store.basespace.illumina.com/'),
    Field('google_analytics_id'))

# populate app_data table if not done already
app_data = db(db.app_data.id > 0).select().first()
if not app_data:
    app_data = db.app_data.insert()

# set google analytics id
response.google_analytics_id = None
if app_data.google_analytics_id:    
    response.google_analytics_id = app_data.google_analytics_id

# set logout location to BaseSpace server
p_url = urlparse(app_data.auth_url)
auth.settings.logout_next = p_url.scheme + "://" + p_url.netloc
del app_data, p_url




# define class for web2py login with BaseSpace credentials 
class BaseSpaceAccount(object):
    """
    OAuth2 implementation for BaseSpace
    
    When login() (in gluon/tools.py) is called, get_user() is called first to determine if a user is logged in, 
    and if not then login_url() is called to log the user into BaseSpace via Oauth2.
    
    During Oauth2, an auth code if first requested, which returns control to BaseSpace. 
    BaseSpace redirects to the controller method handle_redirect_uri(), 
    which in turn calls login() again to return here, where the auth code is traded for an access token (in get_user()).
    
    Web2py login records in the db only the first access token ever encountered for a user (in addition to user name, email, and BaseSpace id). 
    Tokens that acquired outside of login, e.g. to browse a Project, are acquired by a separate non-login oauth2 
    and are written to the user table directly in controller methods, which overwrite the previous token.
    
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
        self.auth_url = app.auth_url
        self.token_url = app.token_url
        self.args = None

    def get_user(self):
        """
        Returns info about the user that is currently logged into PicardSpace. 
        If no user is logged in, and we have a new access token from a login attempt, call the BaseSpace API to get info about the current user.
        Otherwise return None.       
        """
        # if a user is already logged in, return user info from db
        if session.auth:
            user_row = db(db.auth_user.id==auth.user_id).select().first()
            
            return dict(first_name = user_row.first_name,
                        email = user_row.email,
                        username = user_row.username,
                        access_token = user_row.access_token)                    
        # if we have a new token, get current user info
        if session.token:
            
            # clear new token
            token = session.token
            session.token = None            
            app_ssn_num = ""
            app = db(db.app_data.id > 0).select().first()
        
            user = None
            try:
                bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, app_ssn_num, token)
                user = bs_api.getUserById("current")
            except:
                raise HTTP(500, "Error when retrieving User information from BaseSpace", Location="None")                
        
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
        # handle errors from BaseSpace during login        
        if request.vars.error:
            raise HTTP(200, "Permission to access BaseSpace data was rejected by the user", Location=None)
                
        # just received auth code from BaseSpace, trade it for an access token
        if request.vars.code:            
            session.token = get_access_token_util(request.vars.code)           
            session.in_login = False
            return
                        
        # don't have auth code yet -- start login Oauth2, record login state for handle_redirect_uri()                                                                                    
        session.in_login = True    
        auth_request_url = get_auth_code_util(scope="")
        raise HTTP(
            307, 
            "You are not authenticated: you are being redirected to the <a href='" + auth_request_url + "'> authentication server</a>",
            Location=auth_request_url)                              


    def login_url(self, next="/"):
        """
        If a user isn't logged (get_user() returned None), then this is the entry point for login Oauth2. 
        This includes calls from '@requires_login' method decorators when a user isn't logged in.
        """            
        self.__oauth_login()
        return next


    def logout_url(self, next="/"):
        """
        Called when user logs out
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
    Field('name'),
    Field('project_num'),               # the BaseSpace project that the app was launched with (redundant with input_app_result project)
    Field('user_id'), db.auth_user,
    Field('date_created'),
    Field('status'),                    
    Field('message'))                   # detail about AppSession status

db.define_table('genome',
    Field('display_name'),
    Field('genome_num'),
    Field('local_path'))

db.define_table('input_app_result',     # newly created AppResult for PicardSpace's output files
#    Field('app_session_id', db.app_session),
    Field('app_result_num'),
    Field('app_result_name'),
    Field('project_num'),               # the Project that contains this app result in BaseSpace
    Field('sample_num'))                # the Sample that has a relationship to this AppResult, if any

db.define_table('input_file',
    Field('app_result_id', db.input_app_result), # the AppResult that contains this File in BaseSpace
    Field('is_paired_end'),
    Field('genome_id', db.genome),
    Field('file_num'),
    Field('file_name'),
    Field('local_path'),
    Field('file_type'), db.file_type)   # currently unused, but needed for shared File class with output files    

db.define_table('output_app_result',    # newly created AppResult for PicardSpace's output files
    Field('app_session_id', db.app_session),
    Field('app_result_num'),
    Field('app_result_name'),
    Field('project_num'),               # the Project that contains this app result in BaseSpace
    Field('sample_num'),                # the Sample that has a relationship to this AppResult, if any
    Field('input_file_id'), db.input_file) # the File that was used as an input to this AppResult, if any (BAM for picardSpace)   

db.define_table('output_file',
    Field('app_result_id', db.output_app_result), # the AppResult that contains this File in BaseSpace
    Field('is_paired_end'),             # currently unused
    Field('genome_id', db.genome),      # currently unused
    Field('file_num'),                  
    Field('file_name'),
    Field('local_path'),
    Field('file_type'), db.file_type)

db.define_table('product',              # products for billing, corresponding to manually created products in BaseSpace dev portal
    Field('name'),
    Field('num'),
    Field('price'))                     # current price (may change over time)

db.define_table('purchase',             # purchase made by user
    Field('purchase_num'),
    Field('app_session_id', db.app_session),
    Field('date_created'),
    Field('amount'),
    Field('amount_of_tax'),
    Field('amount_total'),
    Field('status'),
    Field('refund_status'),             # default is 'NOTREFUNDED', set to 'COMPLETED' when purchase is refunded
    Field('refund_comment'),            # used only (optionally) during refunds
    Field('refund_secret'),
    Field('access_token'),              # the token used to make this purchase, reqd for refunds
    Field('invoice_number'))
    
db.define_table('purchased_product',    # product(s) that were bought in a user purchase 
    Field('purchase_id', db.purchase),
    Field('product_id', db.product),
    Field('quantity'),
    Field('prod_price'),                # price of product for this purchase (product price can change over time)
    Field('tags', 'list:string'))
    
