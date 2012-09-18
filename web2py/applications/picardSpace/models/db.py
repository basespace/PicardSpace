# -*- coding: utf-8 -*-

## if SSL/HTTPS is properly configured and you want all HTTP requests to
## be redirected to HTTPS, uncomment the line below:
# request.requires_https()

db = DAL('sqlite://storage.sqlite')

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



# TODO move tables to separate model?
import os.path
from subprocess import Popen, PIPE
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI


db.define_table('app_session',
    Field('app_session_num'),
    Field('project_num'),          # the BaseSpace project to write-back results
    Field('orig_app_result_num'),    # the old BaseSpace App Result that contained the file to be analyzed
    # TODO move file_num to app_result?
    Field('file_num'),             # the BaseSpace file that was analyzed
    # TODO delete below entry?
    Field('new_app_result_id'),     # the newly created App Result
    Field('user_id'), db.auth_user) 

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
    


class File:
    """
    A File in BaseSpace
    """
    def __init__(self, app_session_id, file_name, local_path, file_num=None, bs_file_id=None, app_result_id=None):              
        self.app_session_id = app_session_id
        self.file_name = file_name
        self.local_path = local_path
        self.file_num = file_num        
        self.bs_file_id = bs_file_id
        self.app_result_id = app_result_id   # used for inputs to app results

    def download_file(self, file_num, local_dir):
        """
        Download a file from BaseSpace inot the provided directory (created if doesn't exist)
        """     
        # get access token for app session's user (can't use current user since accessing from cron script)
        app_ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        user_row = db(db.auth_user.id==app_ssn_row.user_id).select().first()                        
                        
        # get file info from BaseSpace
        bs_api = BaseSpaceAPI(client_id, client_secret, baseSpaceUrl, version, app_ssn_row.app_session_num, user_row.access_token)
        f = bs_api.getFileById(file_num)
                        
        # create local_path dir if it doesn't exist   
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # write downloaded data to new file
        f.downloadFile(bs_api,local_dir)
        return(local_dir + f.Name)
        
    
class AnalysisInputFile(File):
    """
    Class to download, analyze, and write-back results of a single file    
    """
    def download_and_analyze(self):
        """
        Download file contents from BaseSpace and queue the file for analysis
        """             
        # get file and analysis info from database        
        app_ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        
        # set local_path location and url for downloading
        # TODO remove hard-coded path
        local_dir="applications/picardSpace/private/downloads/inputs/" + app_ssn_row.app_session_num + "/"        

        # download file from BaseSpace
        try:
            local_file = self.download_file(file_num=self.file_num, local_dir=local_dir)
        except IOError as e:
            return(False)

        # update file's local path
        file_row = db(db.bs_file.id==self.bs_file_id).select().first()     
        file_row.update_record(local_path=local_file)
        db.commit()
        
        # add file to analysis queue
        db.analysis_queue.insert(status='pending', app_result_id=self.app_result_id)
        return(True)
     

class AnalysisFeedback:
    """
    Records status and error messages of an Analysis
    """
    def __init__(self, status, message):               
        self.status = status # TODO allow only 'complete', 'error', ?
        self.message = message


class AppResult:
    """
    An App Result in BaseSpace
    """
    def __init__(self, app_result_id, app_session_id, project_num, app_result_name, description, app_result_num, status="new", message=""):
        self.app_result_id = app_result_id 
        self.app_session_id = app_session_id
        self.project_num = project_num
        self.app_result_name = app_result_name
        self.app_result_num = app_result_num
        self.description = description
        self.status = status
        self.message = message
        
        self.output_files = []           


    def run_analysis_and_writeback(self, input_file):
        """
        Run picard on the provided file and writeback output files to BaseSpace, updating statuses as we go
        """                                    
        # update db and BaseSpace App Session with status
        self._update_status('running', 'picard is running', 'Running')
                
        # run picard
        message = "analysis successful"
        try:
            if not (self._run_picard(input_file=input_file)):
                message = "analysis failed"
        except IOError as e:
            message = "Error in local file I/O (error number {0}): {1}".format(e.errno, e)
            self._update_status('analysis error', message, 'Error')
        except:        
            message = "Picard analysis failed -- see stderr.txt file for more information."
            self._update_status('analysis error', message, 'Error')
        else:
            self._update_status("writing back", message)
       
            # writeback output files
            try:
                self._writeback_app_result_files()
            except Exception as e:
                message += "; writeback error: {0}".format(str(e))
                self._update_status('analysis successful, writeback error', message, 'Error')
            else:
                message += "; write-back successful"
                self._update_status('complete', message, 'Complete')
            
        return AnalysisFeedback(self.status, message)


    def _update_status(self, local_status, message, bs_ssn_status=None):
        """
        Update db with provided status and detailed message, and update BaseSpace App Session status if provided
        """
        # update status in local db
        self.status=local_status
        self.message=message
        ar_row = db(db.app_result.id==self.app_result_id).select().first()
        ar_row.update_record(status=self.status, message=self.message)
        db.commit()
        
        # optionally update status of AppSession in BaseSpace
        if bs_ssn_status:
            # get BaseSpace API
            app_ssn_row = db(db.app_session.id==self.app_session_id).select().first()
            user_row = db(db.auth_user.id==app_ssn_row.user_id).select().first()        
            bs_api = BaseSpaceAPI(client_id, client_secret, baseSpaceUrl, version, app_ssn_row.app_session_num, user_row.access_token)
            app_result = bs_api.getAppResultById(self.app_result_num)
            app_ssn = app_result.AppSession 
            app_ssn.setStatus(bs_api, bs_ssn_status, message)   

        
    def _run_picard(self, input_file):    
        """
        Run picard's CollectAlignmentSummaryMetics on a BAM file       
        """                
        input_path = input_file.local_path
        
        # assemble picard command and run it
        (dirname, file_name) = os.path.split(input_path)
        aln_met_name = file_name + ".AlignmentMetrics.txt"
        output_path = os.path.join(dirname, aln_met_name)
        
        #output_file = local_path + ".alignment_metrics.txt"
        command = ["java", "-jar", 
            "applications/picardSpace/private/picard-tools-1.74/CollectAlignmentSummaryMetrics.jar", 
            "INPUT=" + input_path, 
            "OUTPUT=" + output_path, 
            #"REFERENCE_SEQUENCE=applications/picardSpace/private/genome.fa",
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        p = Popen(command, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        
        # add output file to writeback list
        if (os.path.exists(output_path)):           
            f = File(app_session_id=self.app_session_id,
                app_result_id=self.app_result_id,
                file_name=aln_met_name,
                local_path=output_path)
            self.output_files.append(f)
        
        # write stdout and stderr to files for troubleshooting
        stdout_name = file_name + ".stdout.txt"
        stderr_name = file_name + ".stderr.txt"
        stdout_path = os.path.join(dirname, stdout_name)
        stderr_path = os.path.join(dirname, stderr_name)
        F_STDOUT = open( stdout_path, "w")
        F_STDERR = open( stderr_path, "w")
        F_STDOUT.write(stdout)
        F_STDERR.write(stderr)                
        F_STDOUT.close()
        F_STDERR.close()
        
        # add stdout and stderr to write-back queue
        f_stdout = File(app_session_id=self.app_session_id,
                app_result_id=self.app_result_id,
                file_name=stdout_name,
                local_path=stdout_path)        
        f_stderr = File(app_session_id=self.app_session_id,
                app_result_id=self.app_result_id,
                file_name=stderr_name,
                local_path=stderr_path)        
        # TODO API choking with 400 code when uploading empty file -- how to handle this?
        #self.output_files.append(f_stdout)
        # TODO instead of writing stderr file to BS, use error mechanism as described in API?
        self.output_files.append(f_stderr)
        
        # return true if picard return code was successful
        # TODO handle returncode=None, which means process is still running
        if (p.returncode == 0):
            return(True)
        else:
            return(False)    


    def _writeback_app_result_files(self):
        """
        Writeback all files in output_files list, and create corresponding entries in the local db
        """
        # get BaseSpace API
        app_ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        user_row = db(db.auth_user.id==app_ssn_row.user_id).select().first()        
        bs_api = BaseSpaceAPI(client_id, client_secret, baseSpaceUrl, version, app_ssn_row.app_session_num, user_row.access_token)
        app_result = bs_api.getAppResultById(self.app_result_num)
        
        # upload files to BaseSpace
        for f in self.output_files:

            # TODO add dir name to write to?
            bs_file = app_result.uploadFile(bs_api, f.local_path, f.file_name, '', 'text/plain')
                
            # add file to local db
            bs_file_id = db.bs_file.insert(app_session_id=f.app_session_id,
                    app_result_id=f.app_result_id,
                    file_num=bs_file.Id, 
                    file_name=f.file_name, 
                    local_path=f.local_path, 
                    io_type="output")               
            db.commit()
