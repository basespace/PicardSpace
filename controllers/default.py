# -*- coding: utf-8 -*-

import os.path
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import re
from picardSpace import File, readable_bytes
import shutil

def index():
    """
    A user just launched the PicardSpace app
    Retrieve the app session number to identify items that the users selected to analyze
    """
    response.menu = False
    response.title = "PicardSpace"
    response.subtitle = "Home Page"

    # clear existing session vars 
    session.app_session_num = None
    session.project_num = None
    session.scope = None
    session.app_result_name = None
    session.file_num = None
    session.file_name = None

    
    main_msg = 'Welcome to PicardSpace'
    scnd_msg = 'Please log in'
    err_msg  = ''
    
    # record app session number if provided
    if (request.get_vars.appsessionuri):
        appsessionuri = request.get_vars.appsessionuri
        session.app_session_num = os.path.basename(appsessionuri)
         
        # exchange app session num for items the user pre-selected in BaseSpace
        app = db(db.app_data.id > 0).select().first()
        try:
            bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,session.app_session_num)
            app_ssn = bs_api.getAppSession()     
        except Exception as e:
            return dict(main_msg=T(main_msg), scnd_msg=T(scnd_msg), err_msg=T(str(e)))            

        # TODO iterate over all inputs and assemble into master scope string?
        ssn_ref = app_ssn.References[0]
        if (ssn_ref.Type != 'Project'):
            err_msg += "Error - unrecognized reference type " + ssn_ref.Type + ". "
        else:
            # get the project num and access string of pre-selected Project
            ref_content = ssn_ref.Content
            session.project_num = ref_content.Id
            session.scope = ref_content.getAccessStr(scope='read')
            
            # create app_session in db
            app_session_id = db.app_session.insert(app_session_num=session.app_session_num,
                project_num=session.project_num,
                date_created=app_ssn.DateCreated)
                
            # user should already be logged into BaseSpace, so redirect to logged-in screen
            redirect(user_now_logged_in())
        
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(user_now_logged_in())       

    # construct login_url for login link
    # http://localhost:8000/PicardSpace/default/user/login?_next=/PicardSpace/default/user_now_logged_in'    
    if (request.is_local):
        login_url = URL('user', args=['login'], vars=dict(_next=URL('user_now_logged_in')), scheme=True, host=True, port=8000)
    else:
        login_url = URL('user', args=['login'], vars=dict(_next=URL('user_now_logged_in')), scheme=True, host=True)
                                    
    return dict(main_msg=T(main_msg), scnd_msg=T(scnd_msg), err_msg=T(err_msg), login_url=login_url)


@auth.requires_login()
def user_now_logged_in():
    """
    Just determined that the user is logged into picardSpace; if a project context was provided, redirect to choose inputs flow, otherwise redirect to view results page
    """
    # determine if the user pre-selected a sample/app_result/project to analyze
    if (not session.app_session_num):
        redirect(URL('view_results'))
    else:
        # an app session num was provided, update app session with user info
        app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
        app_ssn_row.update_record(user_id=auth.user_id)

        # get and record access_token for pre-selected item (e.g. Project)
        # if user already granted access, no oauth dialog will show
        session.return_url = 'choose_analysis_inputs'
        session.scope = 'read'
        redirect(URL('get_auth_code'))

        return dict(message=T(message))


@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """
    response.menu = False
    
    # if arriving from just-launched analysis, display msg 'just launched'
    app_ssns = []
    err_msg = ""
    message = ""
    if request.get_vars.message:
        message = request.get_vars.message

    # get BaseSpace API
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
    except Exception as e:
        return dict(message=T(message), app_ssns=app_ssns, err_msg=T(str(e)))
    
    # get all app sessions for the current user    
    ssn_rows = db(db.app_session.user_id==auth.user_id).select(orderby=~db.app_session.date_created)
    for ssn_row in ssn_rows:
        rslt_rows = db(db.app_result.app_session_id==ssn_row.id).select()

        # get project name for each AppResult    
        for rslt_row in rslt_rows:          
            try:
                proj = bs_api.getProjectById(rslt_row.project_num)
            except Exception as e:
                return dict(message=T(message), app_ssns=app_ssns, err_msg=T(str(e)))                

            # get sample, and file names for each AppResult    
            #sample_name = "unknown"
            #if (rslt_row.sample_num):
            #    try:
            #        sample = bs_api.getSampleById(rslt_row.sample_num)
            #    except Exception as e:
            #        return dict(message=T(message), app_ssns=app_ssns, err_msg=T(str(e)))                
            #    sample_name = sample.Name
            
            ## getting input BAM file here (restricted to single input file)
            #file_row = db((db.bs_file.app_result_id==rslt_row.id) & (db.bs_file.io_type=='input')).select().first()
            #try:
            #    bs_file = bs_api.getFileById(file_row.file_num)
            #except Exception as e:
            #    return dict(message=T(message), app_ssns=app_ssns, err_msg=T(str(e)))                

            app_ssns.append( { 'app_result_name':rslt_row.app_result_name, 'project_name':proj.Name, 'status':rslt_row.status, 'app_session_id':ssn_row.id, 'notes':rslt_row.message, 'date_created':ssn_row.date_created } )
            #    'sample_name':sample_name, 'file_name':bs_file.Name,                 
        
    return dict(message=T(message), app_ssns=app_ssns, err_msg=T(err_msg))

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display picard's output from CollectAlignmentMetrics
    """
    response.menu = False
    app_session_id = request.get_vars.app_session_id
    
    # set var defaults
    hdr = ""
    aln_tbl = []
    tps_aln_tbl = [["data not available"]]
    file_name = "unknown"
    
    # get AppResult from db
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    ar_row = db(db.app_result.app_session_id==app_session_id).select().first()        
    app = db(db.app_data.id > 0).select().first()    
    input_file_row = db((db.bs_file.app_result_id==ar_row.id) & (db.bs_file.io_type=='input')).select().first()
    
    # get Sample and Project from BaseSpace
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, ssn_row.app_session_num, user_row.access_token)        
        sample = bs_api.getSampleById(ar_row.sample_num)        
        project = bs_api.getProjectById(ar_row.project_num)
    except Exception as e:    
        return(dict(aln_tbl=tps_aln_tbl, hdr=hdr, sample_name="", file_name="", app_result_name="", project_name="", err_msg=T(str(e))))

    # get output file info from db
    f_row = db((db.bs_file.app_result_id==ar_row.id)
        & (db.bs_file.io_type=='output')).select().first()
        # TODO select only AlignmentMetrics file, remove first()

    if f_row:        
        # create file object
        f = File(app_result_id=f_row.app_result_id,
                file_name=f_row.file_name,
                local_path=None,
                file_num=f_row.file_num)
        
        # download file from BaseSpace
        local_dir=os.path.join(request.folder, "private", "downloads", "viewing", str(ssn_row.app_session_num))         
        try:
            local_path = f.download_file(f_row.file_num, local_dir)
        except Exception as e:
            return(dict(aln_tbl=tps_aln_tbl, hdr=hdr, sample_name=sample.Name, file_name=input_file_row.file_name, app_result_name=ar_row.app_result_name, project_name=project.Name, err_msg=T(str(e))))
        
        # read local file into array (for display in view)
        with open( local_path, "r") as ALN_QC:

            # get picard output header - collect lines finding line starting with 'CATEGORY'
            line = ALN_QC.readline()
            while not re.match("CATEGORY", line):
                hdr += line
                line = ALN_QC.readline()

            # get picard metric data (and table headings)
            aln_tbl.append(line.rstrip().split("\t"))
            for line in ALN_QC:
                if line.rstrip():
                    aln_tbl.append(line.rstrip().split("\t"))
            ALN_QC.close()

            # transpose list (for viewing - so it is long instead of wide)(now its a tuple)
            tps_aln_tbl = zip(*aln_tbl)
            
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(local_path))            
        except Exception as e:
            return(dict(aln_tbl=tps_aln_tbl, hdr=hdr, sample_name=sample.Name, file_name=input_file_row.file_name, app_result_name=ar_row.app_result_name, project_name=project.Name, err_msg=T(str(e))))

    # TODO check that user is correct (could jump to this page as another user)
    return(dict(aln_tbl=tps_aln_tbl, hdr=hdr, sample_name=sample.Name, file_name=input_file_row.file_name, app_result_name=ar_row.app_result_name, project_name=project.Name, err_msg=""))
            

@auth.requires_login()
def choose_analysis_inputs():
    """
    Offers the user choice of files to analyze
    """
    response.menu = False

    # get project context that user launched from BaseSpace
    app_session_num = session.app_session_num
    project_num = session.project_num

    # get name of project from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
        proj = bs_api.getProjectById(session.project_num)
    except Exception as e:
        return dict(project_name="", file_info="", err_msg=str(e))        
    project_name = proj.Name    

    # get all App Results for current Project
    file_info = []    
    try:                        
        app_results = proj.getAppResults(bs_api)  # to limit to 10 result, add: myQp={'Limit':10}        
        app_results = proj.getAppResults(bs_api, myQp={'Limit':3})
    
    except Exception as e:
        return dict(project_name=project_name, file_info="", err_msg=str(e))        
    
    # get Files for each AppResult    
    for result in app_results:       
       try:
           bs_files = result.getFiles(bs_api, myQp={'Extensions':'bam', 'Limit':100})
       except Exception as e:
           return dict(project_name=project_name, file_info="", err_msg=str(e))        
    
       # construct display name for each BAM file   
       # TODO get Sample name (from relationship to AppResult)
       # TODO add file size
       for f in bs_files:           
           file_info.append( { "file_name" : result.Name + " - " + f.Name + " (" + readable_bytes(f.Size) + ")",
                               "file_num" : f.Id,
                               "app_result_num" : result.Id } )                      
    
    return dict(project_name=project_name, file_info=file_info, err_msg="")


@auth.requires_login()
def confirm_analysis_inputs():
    """
    Confirms user's choice of file to analyze; offers naming app result and launch button
    """
    response.menu = False
    
    # get file_num and app_result_num that user selected    
    if (request.post_vars['file_choice']):
        [orig_app_result_num, session.file_num] = request.post_vars['file_choice'].split(',')        
    else:
        return dict(sample_name="", file_name="", project_name="", err_msg="We have a problem - expected File and AppResult info but didn't receive it")                  

    # get name of file and project and referenced sample from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
        project = bs_api.getProjectById(session.project_num)
        bs_file = bs_api.getFileById(session.file_num)
        app_ssn = bs_api.getAppSession(session.app_session_num)

        app_result = bs_api.getAppResultById(orig_app_result_num)
        samples_ids = app_result.getReferencedSamplesIds()    
    except Exception as e:
        return dict(sample_name="", file_name="", project_name="", err_msg=str(e))        

    # get input file name
    session.file_name = bs_file.Name
    
    # get sample num and name from AppResult, if present
    sample_name = "unknown"
    if samples_ids:
        session.sample_num = samples_ids[0]
        try:
            sample = bs_api.getSampleById(session.sample_num)
        except Exception as e:
            return dict(sample_name="", file_name="", project_name="", err_msg=str(e))               
        sample_name = sample.Name           

    # set scope for getting access token and url to redirect to afterwards
    session.return_url = 'start_analysis'
    session.scope = 'write'
    
    return dict(sample_name=T(str(sample_name)), file_name=T(str(bs_file.Name)), project_name=T(str(project.Name)), err_msg="")        


@auth.requires_login()
def get_auth_code():
    """
    Given an app session number, exchange this via BaseSpace API for item names to analyze
    """                    
    # record post var 'appresult_name', if present, in session var
    if (request.post_vars.app_result_name):
        session.app_result_name = request.post_vars.app_result_name
    
    scope = session.scope + ' project ' + str(session.project_num)
    
    # if on localhost, add port 8000 since likely using web2py Rocket server    
    if (request.is_local):
        redirect_uri = URL('get_access_token', scheme=True, host=True, port=8000)
    else:
        redirect_uri = URL('get_access_token', scheme=True, host=True)

    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num)
        userUrl = bs_api.getWebVerificationCode(scope,redirect_uri)
    except Exception as e:
        return dict(err_msg=str(e))
    redirect(userUrl)    


@auth.requires_login()
def get_access_token():
    """
    Given an authorization code, exchange this for an access token
    """
    # handle api errors
    if (request.get_vars.error):
        message = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(message=T(message))            
        
    # exchange authorization code for auth token
    auth_code = request.get_vars.code
    app_session_num = session.app_session_num
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,app_session_num)
        bs_api.updatePrivileges(auth_code)      
        access_token =  bs_api.getAccessToken()      
    except Exception as e:
        return dict(err_msg=str(e))

    # ensure the current app user is the same as the current BaseSpace user        
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    cur_user_id = user_row.username
    try:
        bs_user = bs_api.getUserById('current')
    except Exception as e:
        return dict(err_msg=str(e))

    if (bs_user.Id != cur_user_id):
        return dict(err_msg="Error - mismatch between PicardSpace user id of " + str(cur_user_id) + " and current BaseSpace user id of " + str(bs_user.Id) + ". Please re-login to PicardSpace.")
   
    # update user's access token in user table
    user_row.update_record(access_token=access_token)

    # go to url specified by original call to get token
    redirect(URL(session.return_url))
    

@auth.requires_login()
def start_analysis():
    """
    Create an app result in BaseSpace and the local db, then queue the input BAM file for download from BaseSpace
    """
    # get session id and current user id from db
    app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()
                 
    # add new AppResult to BaseSpace
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, app_ssn_row.app_session_num, user_row.access_token)
        project = bs_api.getProjectById(session.project_num)
        sample = bs_api.getSampleById(session.sample_num)
        app_result = project.createAppResult(bs_api, session.app_result_name, "PicardSpace AppResult", appSessionId=app_ssn_row.app_session_num, samples=[ sample ] )
    except Exception as e:
        return dict(err_msg=str(e))
        
    # add new AppResult to db            
    app_result_id = db.app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=session.project_num,
        app_result_name=session.app_result_name,
        app_result_num=app_result.Id,
        sample_num=session.sample_num,        
        status="queued for download",
        message="none")      
    db.commit()    

    # add input BAM file to db
    bs_file_id = db.bs_file.insert(
        app_result_id=app_result_id, # TODO currently this is newly created appResult that will analyze this BAM, not the AppResult that contains this BAM in BaseSpace - change this and/or make clearer
        file_num=session.file_num, 
        file_name=session.file_name,
        io_type="input")

    # TODO adding BAM as input file to new AppResult -- move to new AppResult above when bs_file is refactored just above
    ar_row = db(db.app_result.id==app_result_id).select().first()
    ar_row.update_record(input_file_id=bs_file_id)
    
    # add BAM File to download queue
    db.download_queue.insert(status='pending', bs_file_id=bs_file_id)

    # clear session vars
    session.app_session_num = None
    session.project_num = None
    session.scope = None  
    session.app_result_name = None
    session.file_num = None
    session.file_name = None

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis Has Started!')))
    

# for user authentication
def user(): return dict(form=auth())
