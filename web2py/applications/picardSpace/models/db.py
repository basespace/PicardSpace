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

## create all tables needed by auth if not custom tables
auth.define_tables()

## configure email
mail=auth.settings.mailer
mail.settings.server = 'logging' or 'smtp.gmail.com:587'
mail.settings.sender = 'you@gmail.com'
mail.settings.login = 'username:password'

## configure auth policy
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

## if you need to use OpenID, Facebook, MySpace, Twitter, Linkedin, etc.
## register with janrain.com, write your domain:api_key in private/janrain.key
from gluon.contrib.login_methods.rpx_account import use_janrain
use_janrain(auth,filename='private/janrain.key')

#########################################################################
## Define your tables below (or better in another model file) for example
##
## >>> db.define_table('mytable',Field('myfield','string'))
##
## Fields can be 'string','text','password','integer','double','boolean'
##       'date','time','datetime','blob','upload', 'reference TABLENAME'
## There is an implicit 'id integer autoincrement' field
## Consult manual for more options, validators, etc.
##
## More API examples for controllers:
##
## >>> db.mytable.insert(myfield='value')
## >>> rows=db(db.mytable.myfield=='value').select(db.mytable.ALL)
## >>> for row in rows: print row.id, row.myfield
#########################################################################


# TODO move to separate model?
#import urllib2
from urllib2 import Request, urlopen, URLError, HTTPError
from urlparse import urlparse
import os.path
from subprocess import Popen, PIPE

db.define_table('analysis',
    Field('action_id'),
    Field('access_token'),
    Field('analysis_name'), # of original BS analysis
    Field('analysis_num'),
    Field('project_num'))

db.define_table('bs_file',
    Field('analysis_id', db.analysis),
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
    
    
class AnalysisInputFile:
    """
    Class to download, analyze, and write-back results of a single file    
    """
    def __init__(self, bs_file_id):
        """
        """
        self.bs_file_id = bs_file_id
        
    
    def download_and_analyze(self):
        """
        Download file contents from BaseSpace and queue the file for analysis
        """        
        # get file and analysis info from database
        file_row = db(db.bs_file.id==self.bs_file_id).select().first()
        als_row = db(db.analysis.id==file_row.analysis_id).select().first()

        # set local_path location and url for downloading
        local_path="applications/picardSpace/private/downloads/" + als_row.action_id + "/" + file_row.file_name
        url='http://api.cloud-endor.illumina.com/v1pre2/files/' + file_row.file_num + '/content'
        access_token=als_row.access_token

        # download file, and if successful queue the file for analysis
        if (self._download(url, access_token, local_path)):
            file_row.update_record(local_path=local_path)
            db.commit()
            db.analysis_queue.insert(status='pending', bs_file_id=self.bs_file_id)
            return(True)
        else:
            return(False)
    

    def _download(self, url, access_token, local_path):
        """
        Download a file from BaseSpace
        """    
        full_url = url + "?access_token=" + access_token    
        req = Request(full_url)
        try:
            resp = urlopen(req)
        except URLerror, e:
            message = e.reason            
            # TODO how to handle errors? add msg to db?
            return None
        
        aws_url = resp.geturl()    
        hdr = resp.info()    
        content = resp.read()
            
        # create local_path dir if it doesn't exist   
        local_dir = os.path.dirname(local_path)     
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        
        # write downloaded data to new file
        try:
            f = open(local_path, "w")
        except IOError as e:
            # TODO how to record error msg for user?
            msg = "I/O error({0}): {1}".format(e.errno, e.strerr)
            return(False)
        else:
            f.write(content)
            f.close()
            return(True)


class AnalysisFeedback:
    """
    Records status and error messages of an Analysis
    """
    def __init__(self, status, message):
        """
        """
        self.status = status # TODO allow only 'complete', 'error', ?
        self.message = message


class Analysis:
    """
    Class to run an Analysis and write-back file results to BaseSpace
    """
    def __init__(self, bs_file_id):
        """
        """
        self.bs_file_id = bs_file_id
        self.output_files = []


    def run_analysis_and_writeback(self):
        """
        Run picard analysis and writeback output files to BaseSpace
        """        
        # get file and analysis info from database
        file_row = db(db.bs_file.id==self.bs_file_id).select().first()
        als_row = db(db.analysis.id==file_row.analysis_id).select().first()
        
        local_path = file_row.local_path
        project_num = als_row.project_num
        orig_analysis_name = als_row.analysis_name
        access_token = als_row.access_token
        
        # run picard
        retval = self._run_picard(local_path=local_path)
        if(retval):
            status="complete"
            message=""
        else:
            status="error"
            message="Picard analysis failed -- see stderr.txt file for more information."
       
        # create new Analysis in BaseSpace for writing back analysis output files
        # TODO allow user to name analysis?
        new_analysis_name = "test writeback"
        ca = self._create_analysis(access_token=access_token,
            project_num=project_num, analysis_name=new_analysis_name)
        
        # write back picard output files
        #if (ca):
        
        if(not ca):
            status="error"
            message+=" Creating new Analysis in BaseSpace failed."
            
        return AnalysisFeedback(status, message)

        
    def _run_picard(self, local_path):    
        """
        Run picard's CollectAlignmentSummaryMetics on a BAM file       
        """                
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


    def _create_analysis(self, access_token, project_num, analysis_name):
        """
        """
        # create a new analysis in a BaseSpace project
        url = 'https://api.cloud-endor.illumina.com/v1pre2/projects/' + project_num + 'analyses'               
        args = 'Name=' + analysis_name +', Description=' + project_num
        headers = {}
        headers['x-access-token'] = access_token
        req = Request(url,args, headers)
        try:
            resp = urlopen(req)
        except HTTPError, e:
            # TODO where to store and display these errors?
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            return(False)
        except URLError, e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            return(False)
        else:
            # server responsed with JSON with details of new analysis
            #resp_url = resp.geturl()    
            #resp_hdr = resp.info()
            resp_data = json.loads(resp.read())
            return(True)
