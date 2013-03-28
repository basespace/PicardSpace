#!/usr/bin/env python
# coding: utf8
from gluon import *
import os.path
from subprocess import Popen, PIPE
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import shutil


class UnrecognizedProductException(Exception):
    def __init__(self, value):
        self.parameter = 'The following product name was not recognized: ' + str(value)
    def __str__(self):
        return repr(self.parameter)


class File(object):
    """
    A File in BaseSpace
    """
    def __init__(self, file_name, local_path, file_num=None, bs_file_id=None, app_result_id=None):              
        self.file_name = file_name
        self.local_path = local_path
        self.file_num = file_num        
        self.bs_file_id = bs_file_id
        self.app_result_id = app_result_id

    def download_file(self, file_num, local_dir, app_session_id):
        """
        Download a file from BaseSpace into the provided directory (created if doesn't exist)
        """
        db = current.db
        # get access token for app session's user (can't use current user since accessing from 'cron' script)        
        ssn_row = db(db.app_session.id==app_session_id).select().first()
        user_row = db(db.auth_user.id==ssn_row.user_id).select().first()                        
                        
        # get file info from BaseSpace
        app = db(db.app_data.id > 0).select().first()
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, ssn_row.app_session_num, user_row.access_token)
        f = bs_api.getFileById(file_num)
                        
        # create local_path dir if it doesn't exist   
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)

        # write downloaded data to new file
        f.downloadFile(bs_api,local_dir)                        
        return(os.path.join(local_dir, f.Name))
        
    
class AnalysisInputFile(File):
    """
    Class to download, analyze, and write-back results of a single file    
    """
    def download_and_queue_analysis(self):
        """
        Download file contents from BaseSpace and queue the file for analysis
        """           
        db = current.db  
        
        # get input file and output app result info from database        
        ar_row = db(db.output_app_result.input_file_id==self.bs_file_id).select().first()
        ssn_row = db(db.app_session.id==ar_row.app_session_id).select().first()
        
        # update app session status
        ssn_row.update_record(status="downloading")
        db.commit()
        
        # set local_path location and url for downloading
        local_dir = os.path.join(current.request.folder, "private", "downloads", "inputs", str(ssn_row.app_session_num))

        # download file from BaseSpace
        try:
            local_file = self.download_file(file_num=self.file_num, local_dir=local_dir, app_session_id=ssn_row.id)
        except Exception as e:
            print "Error downloading file from BaseSpace: {0}".format(str(e)) # won't reach user

            # update download queue and AppSession status in db            
            ssn_row.update_record(status='aborted', message=str(e))
            db.commit()
        else:
            # update file's local path
            file_row = db(db.input_file.id==self.bs_file_id).select().first()     
            file_row.update_record(local_path=local_file)
            db.commit()               
        
            # add file to analysis queue                        
            #q.enqueue_call(func=analyze_bs_file, 
            #       args=(self.bs_file_id,),
            #       timeout=86400) # seconds
            current.scheduler.queue_task(analyze_bs_file, 
                                 pvars = {'input_file_id':self.bs_file_id}, 
                                 timeout = 86400) # seconds

            # update app_session status to 'download complete, in analysis queue'
            ssn_row.update_record(status="queued for analysis", message="download complete")
            db.commit()


class AppResult(object):
    """
    An App Result in BaseSpace
    """
    def __init__(self, app_result_id, app_session_id, project_num, app_result_name, app_result_num):
        self.app_result_id = app_result_id
        self.app_session_id = app_session_id
        self.project_num = project_num
        self.app_result_name = app_result_name
        self.app_result_num = app_result_num                    
        
        self.output_files = []           
            

    def run_analysis_and_writeback(self, input_file):
        """
        Run picard on the provided file and writeback output files to BaseSpace, updating statuses as we go
        """                                    
        # update db and BaseSpace App Session with status
        self.update_status('running', 'picard is running', 'running')
                
        # run picard                        
        if self._run_picard(input_file):
            message = 'analysis successful; results not yet written back to BaseSpace'
            analysis_success = True            
        else:
            message = 'analysis failed - see stderr.txt; results not yet written back to BaseSpace'
            analysis_success = False        
        self.update_status("writing back", message)
       
        # writeback output files            
        self._writeback_app_result_files()
        message = "analysis and write-back successful"
        if not analysis_success:        
            message = "analysis failed - see stderr.txt; writeback successful"        
        self.update_status('deleting local files', message)
                
        # delete local files                        
        shutil.rmtree(os.path.dirname(input_file.local_path))        
        message += "; deleted local files"

        # update session status
        status = 'complete'
        if not analysis_success:                    
            status = 'aborted'        
        self.update_status(status, message, status)
            
            
    def status_message(self):
        """
        Return the current status message of the App Session
        """
        db = current.db
        ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        return ssn_row.message


    def update_status(self, local_status, message, bs_ssn_status=None):
        """
        Update db with provided status and detailed message, and update BaseSpace App Session status if provided
        """
        db = current.db
        # update status in local db
        self.status=local_status
        self.message=message        
        ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        ssn_row.update_record(status=self.status, message=self.message)
        db.commit()
        
        # optionally update status of AppSession in BaseSpace -- limited to 128 chars
        if bs_ssn_status:
            # get BaseSpace API
            ssn_row = db(db.app_session.id==self.app_session_id).select().first()
            user_row = db(db.auth_user.id==ssn_row.user_id).select().first()        
            app = db(db.app_data.id > 0).select().first()
            
            # handle exceptions in caller
            bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, ssn_row.app_session_num, user_row.access_token)
            app_result = bs_api.getAppResultById(self.app_result_num)
            app_ssn = app_result.AppSession            
            app_ssn.setStatus(bs_api, bs_ssn_status, message[:128])                    


        
    def _run_picard(self, input_file):    
        """
        Run picard's CollectAlignmentSummaryMetics on a BAM file       
        """                
        input_path = input_file.local_path
        db = current.db                
        app = db(db.app_data.id > 0).select().first()

        # assemble picard command and run it
        (dirname, file_name) = os.path.split(input_path)        
        aln_met_name = file_name + current.aln_metrics_ext
        output_path = os.path.join(dirname, aln_met_name)
        
        command = ["java", "-jar", 
            os.path.join(current.request.folder, app.picard_exe),
            "INPUT=" + input_path, 
            "OUTPUT=" + output_path, 
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        p = Popen(command, stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()        
    
        # add output file to writeback list, if output file has non-zero size
        if (os.path.exists(output_path) and os.path.getsize(output_path)):           
            f = File(app_result_id=self.app_result_id,
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
        # but don't upload empty files since API currently chokes on these
        if os.path.getsize(stdout_path):
            f_stdout = File(app_result_id=self.app_result_id,
                file_name=stdout_name,
                local_path=stdout_path)        
            self.output_files.append(f_stdout)
            
        if os.path.getsize(stderr_path):                    
            f_stderr = File(app_result_id=self.app_result_id,
                file_name=stderr_name,
                local_path=stderr_path)                                
            self.output_files.append(f_stderr)
            
        # return true if picard return code was successful
        # note: not handling returncode=None, which means process may still be running
        if (p.returncode == 0):
            return(True)
        else:
            return(False)    


    def _writeback_app_result_files(self):
        """
        Writeback all files in output_files list, and create corresponding entries in the local db
        """
        db = current.db
        # get BaseSpace API
        ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        user_row = db(db.auth_user.id==ssn_row.user_id).select().first() 
        app = db(db.app_data.id > 0).select().first()       
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, ssn_row.app_session_num, user_row.access_token)
        app_result = bs_api.getAppResultById(self.app_result_num)
        
        # upload files to BaseSpace
        for f in self.output_files:        

            # currently not using a dir name to write to
            bs_file = app_result.uploadFile(bs_api, f.local_path, f.file_name, '', 'text/plain')
                
            # add file to local db
            bs_file_id = db.output_file.insert(
                    app_result_id=f.app_result_id,
                    file_num=bs_file.Id, 
                    file_name=f.file_name, 
                    local_path=f.local_path)                                   
            db.commit()


class ProductPurchase(object):
    """
    A product that a user may purchase
    """
    def __init__(self, prod_name):
        """
        Initialize product with price and num from db
        """              
        db=current.db        
        prod_row = db(db.product.name==prod_name).select().first()
        if not prod_row:
            raise UnrecognizedProductException(prod_name)
        self.prod_name=prod_name
        self.prod_id=prod_row.id
        self.prod_price=prod_row.price
        self.prod_num=prod_row.num
        self.file_num=None
        self.amount=None
        self.prod_quantity=None

    def calc_quantity(self, file_num, access_token):
        """
        Calculates quantity of product needed to purchase from analyzing the provided file
        """
        self.file_num=file_num
        if(self.prod_name == current.product_names['AlignmentQC']):
            db=current.db     
                
            app = db(db.app_data.id > 0).select().first()                                    
            bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, "", access_token)                
            input_file = bs_api.getFileById(file_num)    
        
            if input_file.Size < 100000000: # <100 MB
                self.prod_quantity = 1
            elif input_file.Size < 1000000000: # <1 GB
                self.prod_quantity = 5
            else:                           # >1 GB
                self.prod_quantity = 10       
        else:
            raise UnrecognizedProductException(self.prod_name)


def readable_bytes(size,precision=2):
    """
    Utility function to display number of bytes in a human-readable form
    """
    suffixes=['B','KB','MB','GB','TB']
    suffixIndex = 0
    while size > 1024:
        suffixIndex += 1 #increment the index of the suffix
        size = size/1024.0 #apply the division
    return "%.*f %s"%(precision,size,suffixes[suffixIndex])
    

def get_auth_code_util(scope):
    """
    Initiate OAuth2 to get auth code for the given scope, returns url to redirect to so user can confirm scope via oauth2 dialog
    """
    if not scope:
        scope = ""
    app = current.db(current.db.app_data.id > 0).select().first()
    bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, current.session.app_session_num)
    
    url = bs_api.getWebVerificationCode(scope,app.redirect_uri)
    return url

        
def get_access_token_util(auth_code):
    """
    Given an auth code, retrieve and return the access token from BaseSpace
    """            
    app = current.db(current.db.app_data.id > 0).select().first()    
    bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,current.session.app_session_num)
    
    bs_api.updatePrivileges(auth_code)      
    access_token =  bs_api.getAccessToken()   
    
    # set token in session var
    current.session.token = access_token                  
    return access_token


def download_bs_file(input_file_id):
    """
    Downloads file from BaseSpace -- called from queue
    """
    db = current.db

    # refresh database connection -- needed for mysql RDS
    db.commit()

    # get queued file from db
    f_row = db(db.input_file.id==input_file_id).select().first()
    ar_row = db(db.output_app_result.input_file_id==f_row.id).select().first()
    ssn_row = db(db.app_session.id==ar_row.app_session_id).select().first()

    # create a File object
    als_file = AnalysisInputFile(
        app_result_id=f_row.app_result_id,
        bs_file_id=f_row.id,
        file_num=f_row.file_num,
        file_name=f_row.file_name,
        local_path=f_row.local_path)

    # download the file from BaseSpace
    try:
        als_file.download_and_queue_analysis()
    except Exception as e:            
        print "Error: {0}".format(str(e))

        # update AppSession status in db        
        ssn_row.update_record(status='aborted', message=str(e))            
        db.commit()
        # raise exception so queue will record exception and mark job as failed
        raise
    
    # sanity commit to db for web2py Scheduler
    db.commit()


def analyze_bs_file(input_file_id):
    """
    Analyzes file from BaseSpace -- called from queue
    """
    db = current.db

    # refresh database connection -- needed for mysql RDS
    db.commit()

    # get queued app result from db
    f_row = db(db.input_file.id==input_file_id).select().first()
    ar_row = db(db.output_app_result.input_file_id==f_row.id).select().first()

    input_file = AnalysisInputFile(
        app_result_id=f_row.app_result_id,
        file_num=f_row.file_num,
        file_name=f_row.file_name,
        local_path=f_row.local_path)

    # create AppResult object to analyze downloaded File
    app_result = AppResult(
        app_result_id=ar_row.id,
        app_session_id=ar_row.app_session_id,
        project_num=ar_row.project_num,
        app_result_name=ar_row.app_result_name,
        app_result_num=ar_row.app_result_num)        
        
    # run analysis and writeback results to BaseSpace                        
    message = 'None'
    try:                        
        app_result.run_analysis_and_writeback(input_file) 
                                           
    except Exception as e:                                
        message = str(e)
        if e.message:
            message = message + " - " + e.message
        
        # append error message to existing app ssn status msg (keep context);
        message = app_result.status_message() + "; " + message
        print "Error: {0}".format(message)

        # update AppSession status in db and BaseSpace            
        try:            
            app_result.update_status('aborted', message, 'aborted')
        except Exception as e:
            # print err msg,  but not in db (user won't see it)
            print "Error updating AppSession status: {0} - {1}".format(str(e), e.message) 
        # raise exception so queue will record exception and mark job as failed
        raise    
    # sanity commit to db for web2py Scheduler
    db.commit()


 
