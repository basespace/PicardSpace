# -*- coding: utf-8 -*-

#########################################################################
## This scaffolding model makes your app work on Google App Engine too
## File is released under public domain and you can use without limitations
#########################################################################

## if SSL/HTTPS is properly configured and you want all HTTP requests to
## be redirected to HTTPS, uncomment the line below:
# request.requires_https()

if not request.env.web2py_runtime_gae:
    ## if NOT running on Google App Engine use SQLite or other DB
    db = DAL('sqlite://storage.sqlite')
else:
    ## connect to Google BigTable (optional 'google:datastore://namespace')
    db = DAL('google:datastore')
    ## store sessions and tickets there
    session.connect(request, response, db = db)
    ## or store session in Memcache, Redis, etc.
    ## from gluon.contrib.memdb import MEMDB
    ## from google.appengine.api.memcache import Client
    ## session.connect(request, response, db = MEMDB(Client()))

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
           Field('password', 'password', length=256, readable=False, label='Password'),
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

## configure email
#mail=auth.settings.mailer
#mail.settings.server = 'logging' or 'smtp.gmail.com:587'
#mail.settings.sender = 'you@gmail.com'
#mail.settings.login = 'username:password'

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True


#basespaceuser1 aTest-1 (app)
client_id     = 'f4e812672009413d809b7caa31aae9b4'
client_secret = 'a23bee7515a54142937d9eb56b7d6659'
redirect_uri = 'http://localhost:8000/picardSpace/default/startanalysis'

# import OAuth2 account for authentication
from gluon.contrib.login_methods.oauth20_account import OAuthAccount


class BaseSpaceAccount(OAuthAccount):
    """
    OAuth2 implementation for BaseSpace
    """
    auth_url      = 'https://cloud-endor.illumina.com/oauth/authorize'
    baseSpaceUrl  = 'https://api.cloud-endor.illumina.com/'
    version       = 'v1pre2/'
    token_url      = baseSpaceUrl + version + 'oauthv2/token/'
    
    def __init__(self):
        OAuthAccount.__init__(self, 
            globals(),   # web2py keyword
            client_id, 
            client_secret,
            self.auth_url,
            self.token_url,
            #redirect_uri=redirect_uri,  # redirect uri of the BaseSpace app -- reqd by BaseSpace API
            state='user_login')
            # TODO use scope parameter here?
            
    def get_user(self):
        """
        Returns the user using the BaseSpace API            
        """
        if not self.accessToken():
            return None

        # TODO need to check if myAPI isn't yet defined?
        #if not self.myAPI:
        self.myAPI = BaseSpaceAPI(AccessToken=self.accessToken(),apiServer=self.baseSpaceUrl + self.version)
        
        user = None
        try:
            user = self.myAPI.getUserById("current")
        except:
            self.session.token = None
            self.myAPI = None

        if user:
            return dict(first_name = user.Name,
                        last_name = user.Email,
                        username = user.Id)

# TODO subclass accessToken due to diffs in BaseSpace OAuth2 vs web2py's
#    def accessToken(self):
            
auth.settings.login_form=BaseSpaceAccount()



# TODO move tables to separate model?
#import urllib2
from urllib2 import Request, urlopen, URLError, HTTPError
from urlparse import urlparse
import os.path
from subprocess import Popen, PIPE
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI


#TODO assumes a single file is to be analyzed
db.define_table('app_session',
    Field('app_action_num'),
    Field('project_num'),
    Field('analysis_num'),
    Field('file_num'),
    Field('user_id'), db.auth_user) 

db.define_table('analysis',
    Field('access_token'), # TODO probably need to remove this -- replace with user_id?
    Field('analysis_name'),
    Field('analysis_num'),
    Field('project_num'),
    Field('app_action_num'))

db.define_table('bs_file',
#    Field('analysis_id', db.analysis),
    Field('app_session_id', db.app_session),
    Field('file_num'),
    Field('file_name'),
    Field('local_path'))

db.define_table('download_queue',
    Field('status'),
    Field('bs_file_id', db.bs_file))
    
db.define_table('analysis_queue',
    Field('status'),
    Field('message'),
    Field('bs_file_id', db.bs_file))
    
    
server          = 'https://api.cloud-endor.illumina.com/'
version         = 'v1pre2'
    
class AnalysisInputFile:
    """
    Class to download, analyze, and write-back results of a single file    
    """
    def __init__(self, bs_file_id):                
        self.bs_file_id = bs_file_id
        
    
    def download_and_analyze(self):
        """
        Download file contents from BaseSpace and queue the file for analysis
        """        
        # get file and analysis info from database
        file_row = db(db.bs_file.id==self.bs_file_id).select().first()
        app_ssn_row = db(db.app_session.id==file_row.app_session_id).select().first()
        user_row = db(db.auth_user.id==app_ssn_row.user_id).select().first()

        # set local_path location and url for downloading
        local_path="applications/picardSpace/private/downloads/" + app_ssn_row.app_action_num + "/"        
        access_token=user_row.password
        file_num = file_row.file_num

        # download file, and if successful queue the file for analysis
        local_file = self._download_file(file_num=file_num, access_token=access_token, local_path=local_path)
        if (local_file):            
            file_row.update_record(local_path=local_file)
            db.commit()
            db.analysis_queue.insert(status='pending', bs_file_id=self.bs_file_id)
            return(True)
        else:
            return(False)
    

    def _download_file(self, file_num, access_token, local_path):
        """
        Download a file from BaseSpace
        """            
        # get file info from BaseSpace
        myAPI = BaseSpaceAPI(AccessToken=access_token,apiServer= server + version)
        f = myAPI.getFileById(file_num)
                        
        # create local_path dir if it doesn't exist   
        if not os.path.exists(local_path):
            os.makedirs(local_path)

        # write downloaded data to new file
        # Bug for Morten? - don't require trailing slash on local path
        try:
            f.downloadFile(myAPI,local_path)
        except IOError as e:
            # TODO how to handle this error?
            message = "Error in downloading file from BaseSpace"                        
        return(local_path + f.Name)
        

class AnalysisFeedback:
    """
    Records status and error messages of an Analysis
    """
    def __init__(self, status, message):               
        self.status = status # TODO allow only 'complete', 'error', ?
        self.message = message


class File:
    """
    A File in BaseSpace
    """
    def __init__(self, app_session_id, file_num, file_name, local_path):              
#        self.analysis_id = analysis_id
        self.app_session_id = app_session_id
        self.file_num = file_num
        self.file_name = file_name
        self.local_path = local_path


class Analysis:
    """
    An Analysis in BaseSpace
    """
    def __init__(self, access_token, project_num, analysis_name=None, analysis_num=None, app_action_num=None):
                
        self.access_token = access_token
        self.project_num = project_num
        self.analysis_name = analysis_name
        self.analysis_num = analysis_num
        self.app_action_num = app_action_num
        
        self.output_files = []
        #TODO declare or initialize these here?
        #self.myAPI = ""
        #self.analysis = ""        

    def run_analysis_and_writeback(self, input_file):
        """
        Create an analysis in BaseSpace, run picard on the provided file, and writeback output files to BaseSpace
        """                
        # create new analysis in BaseSpace (for writing-back output files)
        # TODO allow user to name analysis?
        new_analysis_name = "test writeback"
        new_analysis_description = "testing the writeback"
        self._create_analysis(name=new_analysis_name,
            description=new_analysis_description)        
        
        # run picard
        if(self._run_picard(input_file=input_file)):
            status="complete"
            message=""
        else:
            status="error"
            message="Picard analysis failed -- see stderr.txt file for more information."
       
        # write-back analysis output files to BaseSpace
        if(not self._writeback_analysis_files()):
            status="error"
            message+=" Creating new Analysis in BaseSpace failed."
            
        return AnalysisFeedback(status, message)


    def _create_analysis(self, name, description):
        """
        Create a new analysis in BaseSpace with the provided name and description
        """
        self.myAPI = BaseSpaceAPI(AccessToken=self.access_token, apiServer=server + version)
        project = self.myAPI.getProjectById(self.project_num)
        self.analysis = project.createAnalysis(self.myAPI, name, description)

        
    def _run_picard(self, input_file):    
        """
        Run picard's CollectAlignmentSummaryMetics on a BAM file       
        """                
        local_path = input_file.local_path
        
        # assemble picard command and run it
        output_file = local_path + ".alignment_metrics.txt"
        command = ["java", "-jar", 
            "applications/picardSpace/private/picard-tools-1.74/CollectAlignmentSummaryMetrics.jar", 
            "INPUT=" + local_path, 
            "OUTPUT=" + output_file, 
            "REFERENCE_SEQUENCE=applications/picardSpace/private/genome.fa"]
        p = Popen(command, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        
        # add output file to writeback list
        if (os.path.exists(output_file)):
            self.output_files.append(output_file)
        
        # write stdout and stderr to files for troubleshooting
        try:
             stdout_name = local_path + ".stdout.txt"
             stderr_name = local_path + ".stderr.txt"
             F_STDOUT = open( stdout_name, "w")
             F_STDERR = open( stderr_name, "w")
        except IOError as e:
            # TODO how to record error msg for user?
            msg = "I/O error({0}): {1}".format(e.errno, e.strerr)
        else:                            
            F_STDOUT.write(stdout)
            F_STDERR.write(stderr)                
            F_STDOUT.close()
            F_STDERR.close()        
            self.output_files.append(stdout_name)
            self.output_files.append(stderr_name)
        
        # TODO handle returncode=None, which means process is still running
        if (p.returncode == 0):
            return(True)
        else:
            return(False)    


    def _writeback_analysis_files(self):
        """
        Create a new Analysis in the provided Project and writeback all files in the local path to it
        """
        # TODO add correct dir name to write to        
        for f in self.output_files:                               
            self.analysis.uploadFile(self.myAPI, f, os.path.basename(f), '', 'text/plain')

        self.analysis.setStatus(self.myAPI,'completed','Thats all folks')
        
        return(True)
