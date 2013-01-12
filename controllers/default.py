# -*- coding: utf-8 -*-

import os.path
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
import re
from picardSpace import File, readable_bytes, get_auth_code_util, get_access_token_util
import shutil

# Auth notes:
# 1. All '@auth.requires_login' decorators redirect to login() if a user isn't logged in when the method is called (all methods except index() )
# 2. Once a user is logged into picardSpace, they can use their existing tokens to view the results -- even if they log out of BaseSpace -- because tokens are good regardless of BaseSpace login
#

def clear_session_vars():
    """
    Clear all session variables
    """
    session.app_session_num = None
    session.project_num = None
    session.scope = None                   # scope for OAuth2, non-login
    session.login_scope = None             # scope for OAuth2 during login
    session.app_result_name = None
    session.file_num = None
    session.file_name = None
    session.input_app_result_num = None
    session.ar_offset = None
    session.ar_limit = None
    session.return_url = None 
    session.in_login = False  
    session.token = None


def handle_redirect_uri():
    """
    """    
    # handle api errors
    if (request.get_vars.error):
        err_msg = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_message)
        return dict(err_msg=err_msg)                    
        
    # handle case: just launched from BaseSpace 
    if (request.get_vars.appsessionuri):
                
        # clear all session variables
        clear_session_vars()
        
        # record app session number
        appsessionuri = request.get_vars.appsessionuri
        session.app_session_num = os.path.basename(appsessionuri)
    
        # get app session num from BaseSpace
        app = db(db.app_data.id > 0).select().first()
        try:
            bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,session.app_session_num)
            app_ssn = bs_api.getAppSession()     
        except Exception as e:
            return dict(err_msg=str(e))            
        
        # get the project num and access string of pre-selected Project
        ssn_ref = app_ssn.References[0]
        if (ssn_ref.Type != 'Project'):
            return dict(err_msg="Error - unrecognized reference type " + ssn_ref.Type + ". ")
        else:            
            ref_content = ssn_ref.Content
            session.project_num = ref_content.Id
            session.login_scope = ref_content.getAccessStr(scope='read')
            
            # create app_session in db
            app_session_id = db.app_session.insert(app_session_num=session.app_session_num,
                project_num=session.project_num,
                date_created=app_ssn.DateCreated,
                status="newly created")
            
            # log user into PicardSpace (user should already be logged into BaseSpace)
            # TODO change to be an actual url, as the name suggests, not just a controller name?
            session.return_url = 'user_now_logged_in'
            #redirect(URL('user/login'))
            # TODO not clear if _next is needed here
            #redirect( URL('user', args=['login'], vars=dict(_next=URL('user_now_logged_in')) ) )
            redirect( URL('user', args=['login']) )
                                                                                                                                                                                                                                                                                                                                                                                              

    # handle OAuth2 response - exchange authorization code for auth token
    if (request.get_vars.code):
        
        # complete login, if login is in progress
        if session.in_login:
            #redirect( URL('user', args=['login'], vars=dict(code=request.get_vars.code, _next=URL(session.return_url)) ) )
            redirect( URL('user', args=['login'], vars=dict(code=request.get_vars.code) ) )
            # TODO update user token for login session (code elsewhere)

        # otherwise, handle standard OAuth2 response
        auth_code = request.get_vars.code                
        
        # TODO swap this out for get_access_token_util()
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

    # shouldn't reach this point            
    return dict(err_msg="Error - didn't recognize query variables")
    
# TODO slim down index() so doesn't capture session id
# TODO remove get_access_token()?                        
             
                                


def index():
    """
    A user just launched the PicardSpace app
    Retrieve the app session number to identify items that the users selected to analyze
    """
    response.title = "PicardSpace"
    response.subtitle = "Home Page"

    # clear existing session vars 
    clear_session_vars()
    
    main_msg = 'Welcome to PicardSpace'
    scnd_msg = ''
    err_msg  = ''
    
    # record app session number if provided
#    if (request.get_vars.appsessionuri):
#        appsessionuri = request.get_vars.appsessionuri
#        session.app_session_num = os.path.basename(appsessionuri)
         
        # get app session num from BaseSpace
#        app = db(db.app_data.id > 0).select().first()
#        try:
#            bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,session.app_session_num)
#            app_ssn = bs_api.getAppSession()     
#        except Exception as e:
#            return dict(main_msg=T(main_msg), scnd_msg=T(scnd_msg), err_msg=T(str(e)))            

        # get the project num and access string of pre-selected Project
#        ssn_ref = app_ssn.References[0]
#        if (ssn_ref.Type != 'Project'):
#            err_msg += "Error - unrecognized reference type " + ssn_ref.Type + ". "
#        else:            
#            ref_content = ssn_ref.Content
#            session.project_num = ref_content.Id
#            session.scope = ref_content.getAccessStr(scope='read')
            
            # create app_session in db
#            app_session_id = db.app_session.insert(app_session_num=session.app_session_num,
#                project_num=session.project_num,
#                date_created=app_ssn.DateCreated,
#                status="newly created")
                
            # user should already be logged into BaseSpace, so redirect to logged-in screen
#            redirect(URL('user_now_logged_in'))
        
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(URL('user_now_logged_in'))       

    session.return_url = 'user_now_logged_in'    
    
    # construct login_url for login link
    # http://localhost:8000/PicardSpace/default/user/login?_next=/PicardSpace/default/user_now_logged_in'
    # TODO for login button on index page, should actually go to temp page that sets session.login_scope="" from None, then redirects to login()
    if (request.is_local):
        login_url = URL('user', args=['login'], vars=dict(_next=URL('user_now_logged_in')), scheme=True, host=True, port=8000)
        #login_url = URL('user', args=['login'], scheme=True, host=True, port=8000)
    else:
        login_url = URL('user', args=['login'], vars=dict(_next=URL('user_now_logged_in')), scheme=True, host=True)
        #login_url = URL('user', args=['login'], scheme=True, host=True)

                                    
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

        # record access token from login (needed since web2py will only record token on very first login)
        if session.token:
            user_row = db(db.auth_user.id==auth.user_id).select().first()
            user_row.update_record(access_token=session.token)
            session.token = None

        # get and record access_token for pre-selected item (e.g. Project)
        # if user already granted access, no oauth dialog will show
        #session.return_url = 'choose_analysis_app_result'
        #session.scope = 'read'
        #redirect(URL('get_auth_code'))
        redirect(URL('choose_analysis_app_result'))

        return dict(message=T(message))


@auth.requires_login()
def choose_analysis_app_result():
    """
    Offers the user choice of AppResult to analyze
    """
    ar_offset = 0
    const_ar_limit = 5
    ar_limit = const_ar_limit
    if request.get_vars.ar_offset:
        ar_offset=int(request.get_vars.ar_offset)
    if request.get_vars.ar_limit:
        ar_limit=int(request.get_vars.ar_limit)    

    # record offest and limit for 'back' link
    session.ar_offset = ar_offset
    session.ar_limit = ar_limit
            
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
        return dict(project_name="", ar_info="", ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", err_msg=str(e))        
    project_name = proj.Name    

    # get App Results for current Project, limited by limit and offset for performance
    ar_info = []    
    try:      
        # app_result list is in condensed API form - no References, Genome -- get these below                        
        #app_results = proj.getAppResults(bs_api, myQp={'Limit':ar_limit,'Offset':ar_offset})
        app_results = proj.getAppResults(bs_api, myQp={'Limit':1024})
        ar_tot = len(app_results)

        # don't allow indexing off end of app_results list
        ar_end = ar_offset+ar_limit        
        if ar_end > ar_tot:
            ar_end = ar_tot                
                                        
        for n in range(ar_offset,ar_end):        
            ar_short = app_results[n]
            
            # get full-form app_result from API to get Sample name (from relationship to AppResult)            
            ar = bs_api.getAppResultById(ar_short.Id)
            
            # get Samples - this method calls API once for each Sample
            samples = ar.getReferencedSamples(bs_api)

            # build string of Sample names for display            
            samples_names = []
            for s in samples:
                samples_names.append(s.Name)
          
            ar_info.append( { "app_result_name" : ar.Name + " - " + ', '.join(samples_names),    # + ", " + ar.DateCreated,
                              "app_result_num" : ar.Id } )                                                  
    except Exception as e:
        return dict(project_name=project_name, ar_info="", ar_start="", ar_end="", ar_tot="", next_offset="", next_limit="", prev_offset="", prev_limit="", err_msg=str(e))                                                                                                                                                                                 
    
    # calculate next and prev start/end                                                                                                                                        
    next_offset = ar_end
    next_limit = const_ar_limit    
    prev_offset = ar_offset - const_ar_limit
    prev_limit = const_ar_limit                                                                    
    if next_offset > ar_tot:
        next_offset = ar_tot    
    if prev_offset < 0:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        prev_offset = 0
                                                                                                                                                                                                                
    return dict(project_name=project_name, ar_info=ar_info, ar_start=ar_offset+1, ar_end=ar_end, ar_tot=ar_tot, next_offset=next_offset, next_limit=next_limit, prev_offset=prev_offset, prev_limit=prev_limit, err_msg="")


@auth.requires_login()
def choose_analysis_file():
    """
    Offers the user choice of file to analyze
    """
    # get app_result_num that user selected    
    if (request.post_vars['ar_choice']):
        session.input_app_result_num = request.post_vars['ar_choice']
    
    # check that session ar num is set (could've arrived from from back link)
    if (not session.input_app_result_num):    
        return dict(app_result_name="", file_info="", ar_limit="", ar_offset="", err_msg="We have a problem - expected AppResult info but didn't receive it")                  
            
    # get list of BAM files for this AppResult from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)
        app_result = bs_api.getAppResultById(session.input_app_result_num)
        bs_files = app_result.getFiles(bs_api, myQp={'Extensions':'bam', 'Limit':100})
    except Exception as e:
        return dict(app_result_name="", file_info="", ar_limit="", ar_offset="", err_msg=str(e))     
    
    # get Sample name from relationship to AppResult for display
    samples = app_result.getReferencedSamples(bs_api)

    # build string of Sample names for display            
    samples_names = []
    for s in samples:
        samples_names.append(s.Name)                
                
    # construct display name for each BAM file   
    file_info = []    
    for f in bs_files:           
        file_info.append( { "file_name" : f.Name + " (" + readable_bytes(f.Size) + ")",
                            "file_num" : f.Id,
                            "app_result_num" : app_result.Id } )                      
    
    app_result_name=app_result.Name + " - " + ', '.join(samples_names)
    
    return dict(app_result_name=app_result_name, file_info=file_info, ar_limit=session.ar_limit, ar_offset=session.ar_offset, err_msg="")
    

@auth.requires_login()
def confirm_analysis_inputs():
    """
    Confirms user's choice of file to analyze; offers naming app result and launch button
    """    
    # get file_num and app_result_num that user selected    
    if (request.post_vars['file_choice']):
        [session.input_app_result_num, session.file_num] = request.post_vars['file_choice'].split(',')        
    else:
        return dict(sample_name="", file_name="", project_name="", err_msg="We have a problem - expected File and AppResult info but didn't receive it")                  

    # TODO check that project is writeable
    
    
    # get name of file and project and referenced sample from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num, user_row.access_token)        
        project = bs_api.getProjectById(session.project_num)
        input_file = bs_api.getFileById(session.file_num)
        app_ssn = bs_api.getAppSession(session.app_session_num)

        app_result = bs_api.getAppResultById(session.input_app_result_num)
        samples_ids = app_result.getReferencedSamplesIds()    
    except Exception as e:
        return dict(sample_name="", file_name="", project_name="", err_msg=str(e))        

    # get input file name
    session.file_name = input_file.Name
    
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
    
    return dict(sample_name=T(str(sample_name)), file_name=T(str(input_file.Name)), project_name=T(str(project.Name)), err_msg="")        


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
#    if (request.is_local):
#        redirect_uri = URL('get_access_token', scheme=True, host=True, port=8000)        
#    else:
#        redirect_uri = URL('get_access_token', scheme=True, host=True)

    try:
        get_auth_code_util(scope)
    except Exception as e:
        return dict(err_msg=str(e))
    
    #app = db(db.app_data.id > 0).select().first()
    #try:
    #    bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, session.app_session_num)
    #    userUrl = bs_api.getWebVerificationCode(scope,redirect_uri)
    #except Exception as e:
    #    return dict(err_msg=str(e))
    #redirect(userUrl)    


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
    try:
        access_token = get_access_token_util(request.get_vars.code)
    except Exception as e:
        return dict(err_msg=str(e))
                            
    #auth_code = request.get_vars.code
    #app_session_num = session.app_session_num
    #app = db(db.app_data.id > 0).select().first()
    #try:
    #    bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version,app_session_num)
    #    bs_api.updatePrivileges(auth_code)      
    #    access_token =  bs_api.getAccessToken()      
    #except Exception as e:
    #    return dict(err_msg=str(e))

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
                 
    # add new AppResult to BaseSpace - using same Project that contains input file
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, app_ssn_row.app_session_num, user_row.access_token)
        project = bs_api.getProjectById(session.project_num)
        input_app_result = bs_api.getAppResultById(session.input_app_result_num)
        sample = bs_api.getSampleById(session.sample_num)
        output_app_result = project.createAppResult(bs_api, session.app_result_name, "PicardSpace AppResult", appSessionId=app_ssn_row.app_session_num, samples=[ sample ] )
    except Exception as e:
        return dict(err_msg=str(e))
    
    # add input app_result to db
    input_app_result_id = db.input_app_result.insert(
        project_num=session.project_num,
        app_result_name=input_app_result.Name,
        app_result_num=session.input_app_result_num,
        sample_num=session.sample_num)
    db.commit()
    
    # add input BAM file to db
    input_file_id = db.input_file.insert(
        app_result_id=input_app_result_id,
        file_num=session.file_num, 
        file_name=session.file_name)
    db.commit()                    
                                                            
    # add new output AppResult to db            
    output_app_result_id = db.output_app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=session.project_num,
        app_result_name=session.app_result_name,
        app_result_num=output_app_result.Id,
        sample_num=session.sample_num,        
        input_file_id=input_file_id)             
    db.commit()
    
    # add BAM File to download queue 
    db.download_queue.insert(status='pending', input_file_id=input_file_id)
    # update AppSession status
    app_ssn_row.update_record(status="input file queued for download")
    db.commit()    
    
    # clear session vars
    clear_session_vars()

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis Has Started!')))    
    

@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """        
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
        rslt_rows = db(db.output_app_result.app_session_id==ssn_row.id).select()

        # get project name for each AppResult    
        for rslt_row in rslt_rows:          
            try:
                proj = bs_api.getProjectById(rslt_row.project_num)
            except Exception as e:
                return dict(message=T(message), app_ssns=app_ssns, err_msg=T(str(e)))                                  

            app_ssns.append( { 'app_result_name':rslt_row.app_result_name, 'project_name':proj.Name, 'status':ssn_row.status, 'app_session_id':ssn_row.id, 'notes':ssn_row.message, 'date_created':ssn_row.date_created } )
            #    'sample_name':sample_name, 'file_name':input_file.Name,                 
        
    return dict(message=T(message), app_ssns=app_ssns, err_msg=T(err_msg))

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display picard's output from CollectAlignmentMetrics
    """
    app_session_id = request.get_vars.app_session_id
    
    # set var defaults
    hdr = ""
    aln_tbl = []
    tps_aln_tbl = [["data not available"]]
    file_name = "unknown"
    
    # get AppResult from db
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    output_ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    input_file_row = db(db.input_file.id==output_ar_row.input_file_id).select().first()
    input_ar_row = db(db.input_app_result.id==input_file_row.app_result_id).select().first()
    app = db(db.app_data.id > 0).select().first()    
                
    # get Sample and Project from BaseSpace
    try:
        bs_api = BaseSpaceAPI(app.client_id,app.client_secret,app.baseSpaceUrl,app.version, ssn_row.app_session_num, user_row.access_token)        
        sample = bs_api.getSampleById(output_ar_row.sample_num)        
        output_project = bs_api.getProjectById(output_ar_row.project_num)
        input_project = bs_api.getProjectById(input_ar_row.project_num)
    except Exception as e:    
        return(dict(aln_tbl=tps_aln_tbl, 
            hdr=hdr,
            sample_name="", 
            sample_num="",
            input_file_name="", 
            input_project_name="", 
            input_app_result_name="", 
            output_app_result_name="", 
            output_project_name="", 
            err_msg=T(str(e))))

    # get output file info from db    
    f_rows = db(db.output_file.app_result_id==output_ar_row.id).select()
    f_row = None
    for row in f_rows:
        # find file with aln metrics extension
        m = re.search(current.aln_metrics_ext + "$", row.file_name)
        if m:
            f_row = row
            break

    if f_row:        
        # create file object
        f = File(app_result_id=f_row.app_result_id,
                file_name=f_row.file_name,
                local_path=None,
                file_num=f_row.file_num)
        
        # download file from BaseSpace
        local_dir=os.path.join(request.folder, "private", "downloads", "viewing", str(ssn_row.app_session_num))         
        try:
            local_path = f.download_file(f_row.file_num, local_dir, app_session_id)
        except Exception as e:
            return(dict(aln_tbl=tps_aln_tbl, 
                hdr=hdr, 
                sample_name=sample.Name, 
                sample_num=sample.Id,
                input_file_name=input_file_row.file_name, 
                input_project_name=input_project.Name, 
                input_app_result_name=input_ar_row.app_result_name,  
                output_app_result_name=output_ar_row.app_result_name, 
                output_project_name=output_project.Name, 
                err_msg=T(str(e))))
        
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
            return(dict(aln_tbl=tps_aln_tbl, 
                hdr=hdr, sample_name=sample.Name, 
                input_file_name=input_file_row.file_name, 
                input_project_name=input_project.Name, 
                input_app_result_name=input_ar_row.app_result_name,  
                output_app_result_name=output_ar_row.app_result_name, 
                output_project_name=output_project.Name, 
                err_msg=T(str(e))))

    # TODO check that user is correct (could jump to this page as another user)
    return(dict(aln_tbl=tps_aln_tbl, 
        hdr=hdr, 
        sample_name=sample.Name, 
        sample_num=sample.Id,
        input_file_name=input_file_row.file_name, 
        input_project_name=input_project.Name,        
        input_app_result_name=input_ar_row.app_result_name,  
        output_app_result_name=output_ar_row.app_result_name, 
        output_project_name=output_project.Name, 
        err_msg=""))
                

# for user authentication
def user(): return dict(form=auth())
