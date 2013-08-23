# -*- coding: utf-8 -*-
import os.path
import re
import shutil
from datetime import datetime
import boto.ec2
from boto.exception import EC2ResponseError
from gluon import HTTP
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
from BaseSpacePy.api.BillingAPI import BillingAPI
from picardSpace import File, ProductPurchase, AppResult, readable_bytes, get_auth_code_util, get_access_token_util, analyze_bs_file

# Auth notes:
# 1. All '@auth.requires_login' decorators redirect to login() if a user isn't logged in when the method is called (and _next=controller_method)
# 2. Once a user is logged into picardSpace, they can use their existing tokens to view the results -- even if they log out of BaseSpace -- because tokens are good regardless of BaseSpace login

def clear_session_vars():
    """
    Clear all session variables
    """
    session.app_session_num = None         # contains app sesssion num that user launched with from BaseSpace
    session.return_url = None              # the url to return to when oauth or billing is complete 
    session.in_login = False               # flag to handle_redirect_uri() to determine if in login or non-login oauth
    session.token = None                   # temporarily holds access token from login oauth    
    session.paid = False                   # flag to record that user has paid for analysis
    session.purchase_id = None             # the current purchase id while a purchase is taking place


def handle_redirect_uri():
    """
    This method is called from BaseSpace when: 
    1) the app is launched
    2) an auth code is returned from either login or non-login oauth2    
    3) (future) after analysis is complete and user returns to view results 
    """    
    # handle api errors
    if request.get_vars.error:
        err_msg = "Error - " + str(request.get_vars.error) + ": " + str(request.get_vars.error_description)
        return dict(err_msg=err_msg)

    if request.get_vars.action:  
        # handle case: just launched from BaseSpace
        if (request.get_vars.action == 'trigger'):            
        
            if not request.get_vars.appsessionuri:
                return dict(err_msg="Error: app trigger from BaseSpace not accompanied by an AppSession Id")                 
            
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
            ref_content = ssn_ref.Content
            project_num = ref_content.Id                        
            
            # create app_session in db
            db.app_session.insert(app_session_num=session.app_session_num,
                project_num=project_num,
                date_created=str(app_ssn.DateCreated),
                status="newly created",
                message="newly launched App Session - no analysis performed yet")
            
            # log user into PicardSpace (user should already be logged into BaseSpace)            
            session.return_url = URL('user_now_logged_in')            
            redirect( URL('user', args=['login']) )
 
        # handle purchases returning from BaseSpace
        elif (request.get_vars.action == 'purchase'):            
            if not request.get_vars.purchaseid:
                return dict(err_msg="Error: purchase from BaseSpace not accompanied by a purchase id")

            # get purchase from db
            p_row = db(db.purchase.purchase_num==request.get_vars.purchaseid).select().first()
            if not p_row:
                return dict(err_msg="Error: product id not recognized for purchase")

            # check that purchase is for the current session's AppSession
            ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
            if (p_row.app_session_id != ssn_row.id):
                return dict(err_msg="Error: the requested purchase is not for the current session")
            
            # get invoice number from BaseSpace now that this purchase is complete
            app = db(db.app_data.id > 0).select().first()
            user_row = db(db.auth_user.id==auth.user_id).select().first()
            try:
                store_api = BillingAPI(app.store_url, app.version, 
                                       session.app_session_num, user_row.access_token)
                purch = store_api.getPurchaseById(request.get_vars.purchaseid)                        
            except Exception as e:
                return dict(err_msg=str(e))                                
            
            # check purchase status in BaseSpace
            try:
                if purch.Status == 'CANCELLED':
                    p_row.update_record(status='cancelled')
                    redirect(URL('view_results', vars=dict(message='Your Analysis Was Canceled')))                
            except AttributeError:
                return dict(err_msg="Error: purchase does not have a status")
            if purch.Status == 'ERRORED':
                p_row.update_record(status='errored')
                return dict(err_msg="Error: there was a purchase error in BaseSpace. Please return to BaseSpace and re-launch the app.")                
            if purch.Status == 'PENDING':
                redirect(URL('view_results', vars=dict(message='The purchase for your analysis is Pending in BaseSpace. Analysis has not started.')))                
            if purch.Status != 'COMPLETED':
                return dict(err_msg="Error: purchase was not completed in BaseSpace")            
            
            # record invoice number and set purchase status to paid in db
            try:
                p_row.update_record(status='paid', invoice_number=purch.InvoiceNumber)
            except AttributeError:
                return dict(err_msg="Error: this purchase does not have invoice number. This is most likely because the purchase did not complete successfully -- please try the purchase again.")
            db.commit()            
            redirect(session.return_url)
    
        # handle OAuth2 response - exchange authorization code for auth token               
        elif (request.get_vars.action == 'oauthv2authorization'):
            if not request.get_vars.code:
                return dict(err_msg="Error: oauth2 authorization from BaseSpace not accompanied by an auth code")            
                                                                                                                                                                                                                                                                                                                                                                                                           
            # complete login, if login is in progress
            if session.in_login:
                redirect( URL('user', args=['login'], vars=dict(code=request.get_vars.code)))
    
            # ensure user is logged in
            if not session.auth:
                return dict(err_msg="Error - user isn't logged in but should be")
    
            # non-login oauth2                        
            try:
                access_token = get_access_token_util(request.get_vars.code)
            except Exception as e:
                return dict(err_msg=str(e))
    
            # ensure the current app user is the same as the current BaseSpace user        
            user_row = db(db.auth_user.id==auth.user_id).select().first()
            cur_user_id = user_row.username
            app = db(db.app_data.id > 0).select().first()
            try:
                bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                                      app.baseSpaceUrl, app.version, 
                                      session.app_session_num, access_token)
                bs_user = bs_api.getUserById('current')
            except Exception as e:
                return dict(err_msg=str(e))
    
            if (bs_user.Id != cur_user_id):
                return dict(err_msg="Error - mismatch between PicardSpace user id of " + str(cur_user_id) + " and current BaseSpace user id of " + str(bs_user.Id) + ". Please re-login to PicardSpace.")
                                   
            # update user's access token in user table
            user_row.update_record(access_token=access_token)
            db.commit()
                
            # go to url specified by original call to get token
            redirect(session.return_url)                  

    # shouldn't reach this point - redirect to index page
    return dict(err_msg="Error - didn't recognize parameters after return from BaseSpace redirect")
                                            

def index():
    """
    Method for user reaching PicardScape outside of launch from BaseSpace -- offer login    
    """
    response.title = "PicardSpace"
    response.subtitle = "Home Page"
    main_msg = 'Welcome to PicardSpace'
    scnd_msg = ''
    err_msg  = ''    
    clear_session_vars()
           
    # if a user is already logged into PicardSpace, redirect to logged-in screen
    if auth.user_id:
        redirect(URL('view_results'))       
        
    # construct login_url for login link, e.g.:
    # http://localhost:8000/PicardSpace/default/user/login?_next=/PicardSpace/default/user_now_logged_in'
    if (request.is_local):        
        login_url = URL('user', args=['login'], scheme=True, host=True, port=8000)  # vars=dict(_next=URL('user_now_logged_in')), 
    else:
        login_url = URL('user', args=['login'], scheme=True, host=True)
                                        
    return dict(main_msg=main_msg, scnd_msg=scnd_msg, err_msg=err_msg, 
                login_url=login_url, bs_url=auth.settings.logout_next)


@auth.requires_login()
def user_now_logged_in():
    """
    Just determined that the user is logged into picardSpace; if a project context was provided, have user choose inputs, otherwise view results.
    If the user owns the launch project, request write access (so no oauth dialogs after billing).
    If not, wait until after billing to create writeback project and request write access to it.
    """
    # determine if the user pre-selected a sample/app_result/project to analyze
    if (not session.app_session_num):
        redirect(URL('view_results'))
    else:            
        # an app session num was provided, update app session with user info
        ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
        ssn_row.update_record(user_id=auth.user_id)
        
        # start oauth, with permission to:
        # 1. Read (and Browse) the launch Project 
        # 2. Create new Projects, if needed, for writeback
        # (using Read Project instead of Browse due to bug in Browsing File metadata)
        # (using Browse Global to browse Samples from input AppResult that are in different Projects)                
        scope = 'create projects, browse global, read project %s' % (str(ssn_row.project_num))                                                                                                              
        session.return_url = URL('choose_analysis_app_result', vars=dict(ar_offset=0, ar_limit=5))
        redirect(URL('get_auth_code', vars=dict(scope=scope)))


@auth.requires_login()
def choose_analysis_app_result():
    """
    Offers the user choice of AppResult to analyze
    """
    ret = dict(bs_url=auth.settings.logout_next, project_name="", ar_info="", 
               ar_start="", ar_end="", ar_tot="", next_offset="", 
               next_limit="", prev_offset="", prev_limit="", 
               ar_back="", ar_offset="", ar_limit="", err_msg="")        
    ret['ar_offset'] = 0
    const_ar_limit = 5
    ret['ar_limit'] = const_ar_limit
    if request.vars.ar_offset:
        ret['ar_offset'] = int(request.vars.ar_offset)
    if request.vars.ar_limit:
        ret['ar_limit'] = int(request.vars.ar_limit)    

    # record offset and limit for 'back' link    
    ret['ar_back'] = URL('choose_analysis_app_result', vars=dict(ar_offset=ret['ar_offset'], ar_limit=ret['ar_limit']))                    

    # get name of project from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              session.app_session_num, user_row.access_token)        
        proj = bs_api.getProjectById(ssn_row.project_num)
    except Exception as e:
        ret['err_msg'] = "Error retrieving project from BaseSpace: " + str(e) 
        return ret        
    ret['project_name'] = proj.Name    

    # get App Results for current Project, limited by limit and offset for performance
    try:
        # app_result list is in condensed API form - no References, Genome -- get these below                    
        app_results = proj.getAppResults(bs_api, myQp={'Limit':1024})
    except Exception as e:
        ret['err_msg'] = "Error retrieving AppResults from BaseSpace: " + str(e)
        return ret
    ret['ar_tot'] = len(app_results)

    # don't allow indexing off end of app_results list
    ret['ar_end'] = ret['ar_offset'] + ret['ar_limit']        
    if ret['ar_end'] > ret['ar_tot']:
        ret['ar_end'] = ret['ar_tot']                
                                
    ar_info = []        
    for n in range(ret['ar_offset'], ret['ar_end']):        
        ar_short = app_results[n]            
        try:
            # get full-form app_result from API to get Sample name (from relationship to AppResult)            
            ar = bs_api.getAppResultById(ar_short.Id)            
            # get Samples - this method calls API once for each Sample
            samples = ar.getReferencedSamples(bs_api)
        except Exception as e:
            ret['err_msg'] = "Error retrieving items from BaseSpace: " + str(e)
            return ret
        # build string of Sample names for display            
        samples_ids = []
        for s in samples:
            samples_ids.append(s.SampleId)          
        ar_info.append( { "app_result_name" : ar.Name + " - " + ', '.join(samples_ids),    # + ", " + str(ar.DateCreated),
                          "app_result_num" : ar.Id } )                                                  
    ret['ar_info'] = ar_info
    
    # calculate next and prev start/end                                                                                                                                        
    ret['next_offset'] = ret['ar_end']
    ret['next_limit'] = const_ar_limit    
    ret['prev_offset'] = ret['ar_offset'] - const_ar_limit
    ret['prev_limit'] = const_ar_limit                                                                    
    if ret['next_offset'] > ret['ar_tot']:
        ret['next_offset'] = ret['ar_tot']    
    if ret['prev_offset'] < 0:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        ret['prev_offset'] = 0
    
    # handle zero app results
    if ret['ar_tot'] == 0:
        ret['ar_start'] = 0
    else:
        ret['ar_start'] = ret['ar_offset'] + 1
    return ret                                                                                                                                                                                                            


@auth.requires_login()
def choose_analysis_file():
    """
    Offers the user choice of file to analyze
    """
    ret = dict(app_result_name="", file_info="", file_back="", ar_num="", 
               ar_back="", err_msg="")
    # get required inputs app result selection and back link
    if ('ar_num' not in request.vars or
        'ar_back' not in request.vars):
        ret['err_msg'] = "We have a problem - expected AppResult and back link but didn't receive them." 
        return ret                     
    ret['ar_num'] = request.vars['ar_num']                      
    ret['ar_back'] = request.vars['ar_back']                    
    
    # create 'back' link    
    ret['file_back'] = URL('choose_analysis_file', 
                           vars=dict(ar_num=ret['ar_num'], 
                                     ar_back=ret['ar_back']))                  
    # get list of BAM files for this AppResult from BaseSpace
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              session.app_session_num, user_row.access_token)
        app_result = bs_api.getAppResultById(ret['ar_num'])
        bs_files = app_result.getFiles(bs_api, myQp={'Extensions':'bam', 'Limit':100})
    except Exception as e:
        ret['err_msg'] = "Error retrieving items from BaseSpace: " + str(e)
        return ret         
    # get Sample name from relationship to AppResult for display
    samples = app_result.getReferencedSamples(bs_api)

    # build string of Sample ids for display            
    samples_ids = []
    for s in samples:
        samples_ids.append(s.SampleId)                
                
    # construct display name for each BAM file   
    file_info = []    
    for f in bs_files:          
        # don't allow analysis of files > 5 GB
        large_file = ""
        if (f.Size > 5*(2**30)):     
            large_file = "large_file"            
        file_info.append( { "file_name" : f.Name + " (" + readable_bytes(f.Size) + ")",
                            "file_num" : f.Id,
                            "large_file" : large_file } )                      
    ret['file_info'] = file_info
    ret['app_result_name'] = app_result.Name + " - " + ', '.join(samples_ids)    
    return ret


@auth.requires_login()
def confirm_analysis_inputs():
    """
    Presents final confirmation to user before launching analysis.
    Offers user form to name analysis (app result name currently).
    Checks that user owns Project that contains input file; if not, uses 'PicardSpace Result' Project, which will be created if it doesn't already exist.
    """
    ret = dict(sample_sampleid="", file_name="", project_name="", writeback_msg="",
               ar_num="", file_num="", file_back="", price="", confirm_msg="", 
               genome_name="", known_genome=False, genome_msg="", 
               is_paired_end="", free_trial=False, err_msg="") 
    
    # get file_num and app_result_num that user selected    
    if ('file_num' not in request.vars or
        'ar_num' not in request.vars or
        'file_back' not in request.vars):
        ret['err_msg'] = "We have a problem - expected File and AppResult info but didn't receive it"
        return ret        
    ret['file_num'] = request.vars['file_num']
    ret['ar_num'] = request.vars['ar_num']
    ret['file_back'] = request.vars['file_back']    

    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              session.app_session_num, user_row.access_token)        
        launch_project = bs_api.getProjectById(ssn_row.project_num)
        input_file = bs_api.getFileById(ret['file_num'])
        app_result = bs_api.getAppResultById(ret['ar_num'])
        samples_ids = app_result.getReferencedSamplesIds()    
    except Exception as e:
        ret['err_msg'] = "Error retrieving items from BaseSpace: " + str(e) 
        return ret        
    ret['file_name'] = input_file.Name
    
    # calculate how much to charge                
    try:        
        prod_purch = ProductPurchase('AlignmentQC')
    except Exception as e:
        ret['err_msg'] = "Error creating product purchase: " + str(e) 
        return ret
    try:
        prod_purch.calc_quantity(ret['file_num'], auth.user_id, False)        
    except Exception as e:
        ret['err_msg'] = "Error calculating product price: " + str(e) 
        return ret                   
    ret['price'] = int(prod_purch.prod_quantity) * int(prod_purch.prod_price)
    
    if ret['price'] == 0:
        if prod_purch.free_trial:
            ret['free_trial'] = True
        ret['confirm_msg'] = "Make It So"
    else:
        ret['confirm_msg'] = "Checkout..."
    
    # get sample num and name from AppResult, if present; only recognizing single sample per app result for now
    if samples_ids:
        sample_num = samples_ids[0]
        try:
            sample = bs_api.getSampleById(sample_num)
        except Exception as e:
            ret['err_msg'] = "Error retrieving sample from BaseSpace: " + str(e)   
            return ret                     
        ret['sample_sampleid'] = sample.SampleId

    # get paired-end status of sample
    try:
        if sample.IsPairedEnd:
            ret['is_paired_end'] = 'Paired-end'
        else:            
            ret['is_paired_end'] = 'Single-end'
    except AttributeError:
        ret['is_paired_end'] = 'unknown'       
        
    # get genome of sample, get id from href for now
    try:
        match = re.search('genomes/(\d+)$', sample.HrefGenome)
    except AttributeError:
        ret['genome_name'] = 'Unknown genome'
    else:
        if not match:
            ret['genome_name'] = 'Unrecognized genome'
        else:
            genome_num = match.group(1)            
            # look up genome in local db; if absent, get display name from BaseSpace
            gen_row = db(db.genome.genome_num==genome_num).select().first()                    
            if gen_row:
                ret['genome_name'] = gen_row.display_name
                ret['known_genome'] = True
            else:
                try:
                    genome = bs_api.getGenomeById(genome_num)
                except Exception as e:
                    ret['err_msg'] = "Error retrieving genome from BaseSpace: " + str(e)   
                    return ret            
                ret['genome_name'] = "Unsupported genome: " + genome.DisplayName

    # determine if user owns launch project, if not use 'PicardSpace Results' - won't create new project until after user confirms analysis
    if user_row.username == launch_project.UserOwnedBy.Id:
        # user is owner - assume they want to write back to source project
        try:
            project = bs_api.getProjectById(ssn_row.project_num)
        except Exception as e:
            ret['err_msg'] = "Error retrieving project from BaseSpace: " + str(e)           
            return ret         
        ret['project_name'] = project.Name
    else:
        ret['project_name'] = 'PicardSpace Results'

    # add writeback message if writing to PicardSpace Results project    
    if ret['project_name'] == 'PicardSpace Results':
        ret['writeback_msg'] = "Since you are not the owner of the Project that contains the BAM file you selected, you can not save files in that Project. Instead, your output files will be saved in a BaseSpace Project that you own named 'PicardSpace Results'."
    if ret['known_genome'] == False:
        ret['genome_msg'] = "GC-Bias metrics are only calculated for samples with known genomes."    
    return ret        


@auth.requires_login()
def start_billing():
    """
    Records parameters to launch analysis and initiates billing process
    """
    if ('ar_name' not in request.vars or
        'ar_num' not in request.vars or
        'file_num' not in request.vars):        
        return dict(err_msg="We have a problem - expected query variables but didn't receive them")
    ar_name = request.vars['ar_name']
    ar_num = request.vars['ar_num']
    file_num = request.vars['file_num']

    # get store API, set long timeout since purchase requests may be long
    user_row = db(db.auth_user.id==auth.user_id).select().first()    
    app = db(db.app_data.id > 0).select().first()            
    try:
        store_api = BillingAPI(app.store_url, app.version, session.app_session_num, user_row.access_token)                
    except Exception as e:
        return dict(err_msg="Error getting BaseSpace billing API: " + str(e))    
    try:    
        store_api.setTimeout(30)            
    except Exception as e:
        return dict(err_msg="Error setting BaseSpace billing timeout: " + str(e))
    
    # calculate how much to charge
    try:        
        # add tags to this purchase as an example
        prod_purch = ProductPurchase('AlignmentQC', ['tag1','tag2'])
    except Exception as e:
        return dict(err_msg="Error creating product purchase: " + str(e))
    try:
        prod_purch.calc_quantity(file_num, auth.user_id, True)        
    except Exception as e:
        return dict(err_msg="Error calculating product price: " + str(e))        
    
    # create purchase, if not free
    if prod_purch.prod_quantity != 0:                    
        try:
            purchase = store_api.createPurchase(
                {'id':prod_purch.prod_num, 'quantity':prod_purch.prod_quantity,
                'tags':prod_purch.tags }, session.app_session_num)
        except Exception as e:
            return dict(err_msg="Error creating purchase: " + str(e))        
        # capture url for user to view BaseSpace billing dialog
        if not purchase.HrefPurchaseDialog:
            return dict(err_msg="There was a problem getting billing information from BaseSpace")
        refund_secret = purchase.RefundSecret
        purchase_num = purchase.Id
        date_created = str(purchase.DateCreated)
        amount = purchase.Amount
        amount_of_tax = purchase.AmountOfTax   
        amount_total = purchase.AmountTotal
        status = "pending"
        redirect_url = purchase.HrefPurchaseDialog
        session.return_url = URL('create_writeback_project', vars=dict(ar_name=ar_name, ar_num=ar_num, file_num=file_num))
    else:
        # free analysis
        refund_secret = "none"
        purchase_num = "none"
        date_created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        amount = 0
        amount_of_tax = 0    
        amount_total = 0
        if prod_purch.free_trial:
            status = "free trial"
        else:
            status="free"
        redirect_url = URL('create_writeback_project', vars=dict(ar_name=ar_name, ar_num=ar_num, file_num=file_num))
        
    # record purchase in db
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()    
    purchase_id = db.purchase.insert(purchase_num = purchase_num,
                                     app_session_id = ssn_row.id,
                                     date_created = date_created,
                                     amount = amount,
                                     amount_of_tax = amount_of_tax,    
                                     amount_total = amount_total,
                                     status = status,
                                     refund_status = "NOTREFUNDED",
                                     refund_comment = "",
                                     refund_secret = refund_secret,
                                     access_token = user_row.access_token)    
    db.purchased_product.insert(purchase_id = purchase_id,
                                product_id = prod_purch.prod_id,
                                quantity = prod_purch.prod_quantity,
                                prod_price = prod_purch.prod_price,
                                tags = prod_purch.tags)                    
    db.commit()
    # set purchase id now that purchase is in db (or free)
    if prod_purch.prod_quantity != 0:
        session.purchase_id = purchase_id
    else:
        session.purchase_id = 'free'        
    redirect(redirect_url)
            

@auth.requires_login()
def create_writeback_project():
    """
    Accepts app result name for new analysis and begins oauth process to start analysis
    """
    if ('ar_name' not in request.vars or
        'ar_num' not in request.vars or
        'file_num' not in request.vars):        
        return dict(err_msg="We have a problem - expected query variables but didn't receive them")    
    ar_name = request.vars['ar_name']
    ar_num = request.vars['ar_num']
    file_num = request.vars['file_num']
    
    # get session id and current user id from db
    ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()                    
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              ssn_row.app_session_num, user_row.access_token)
        launch_project = bs_api.getProjectById(ssn_row.project_num)
    except Exception as e:
        return dict(err_msg=str(e))
    
    # if the user doesn't own the launch Project, then create 'PicardSpace Results' Project    
    if user_row.username != launch_project.UserOwnedBy.Id:                  
        try:
            wb_proj = bs_api.createProject('PicardSpace Results')    
        except Exception as e:
            return dict(err_msg=str(e))
        wb_proj_num = wb_proj.Id
    else:
        wb_proj_num = ssn_row.project_num        
    
    # start oauth to get write access to writeback project, then start analysis
    session.return_url = URL('start_analysis', vars=dict(
        ar_name=ar_name, ar_num=ar_num, file_num=file_num, 
        wb_proj_num=wb_proj_num))
    redirect(URL('get_auth_code', vars=dict(scope='write project ' + str(wb_proj_num))))            
    

@auth.requires_login()
def get_auth_code():
    """
    Begin Oauth process by getting an authentication code for a given scope
    """         
    if ('scope' not in request.vars):
        return dict(err_msg="We have a problem - expected scope but didn't receive it")
    scope = request.vars['scope']
        
    try:
        redirect_url = get_auth_code_util(scope)        
    except Exception as e:
        return dict(err_msg=str(e))                
    raise HTTP(
            307, 
            "You are being redirected to the <a href='" + redirect_url + "'> BaseSpace api server</a>",
            Location=redirect_url)  


@auth.requires_login()
def start_analysis():
    """
    Create an app result in BaseSpace and the local db, then queue the input BAM file for download from BaseSpace
    """
    if ('ar_name' not in request.vars or
        'wb_proj_num' not in request.vars or
        'ar_num' not in request.vars or
        'file_num' not in request.vars):        
        return dict(err_msg="We have a problem - expected query variables but didn't receive them")    
    ar_name = request.vars['ar_name']
    wb_proj_num = request.vars['wb_proj_num']
    ar_num = request.vars['ar_num']
    file_num = request.vars['file_num']    

    # for purchased analysis, make sure the user paid
    if not session.purchase_id:
        return dict(err_msg="Error in determining purchase status of this analysis")
    if session.purchase_id != 'free':
        p_row = db(db.purchase.id==session.purchase_id).select().first()
        if p_row.status != 'paid':
            return dict(err_msg="You gotta pay to play - we didn't receive billing for this analysis")
    
    # get input app result and sample objs from Basespace
    app_ssn_row = db(db.app_session.app_session_num==session.app_session_num).select().first()   
    user_row = db(db.auth_user.id==auth.user_id).select().first()                    
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              app_ssn_row.app_session_num, user_row.access_token)            
        input_app_result = bs_api.getAppResultById(ar_num)
        samples_ids = input_app_result.getReferencedSamplesIds()
    except Exception as e:
        return dict(err_msg=str(e))
    
    # get Samples referenced from AppResult - only recognizing single sample per app result for now
    sample_num = None
    sample = None
    if samples_ids:
        sample_num = samples_ids[0]
        try:
            sample = bs_api.getSampleById(sample_num)
        except Exception as e:
            return dict(err_msg=str(e))
    
    # get pair-end status
    try:
        if sample.IsPairedEnd:
            is_paired_end = 'paired'
        else:            
            is_paired_end = 'single'
    except AttributeError:
        is_paired_end = 'unknown'    

    # get genome of sample, get id from href for now
    try:    
        match = re.search('genomes/(\d+)$', sample.HrefGenome)
    except AttributeError:
        genome_id = None
    else:
        if not match:
            genome_id = None        
        else:
            genome_num = match.group(1)
            gen_row = db(db.genome.genome_num==genome_num).select().first()                    
            if gen_row:
                genome_id = gen_row.id
            else:
                genome_id = None # null entry is unsupported or unknown genome 
                
    # clean app result name - only allow alpha, numeric, spaces, and a few symbols
    ar_name = re.sub("[^ a-zA-Z0-9_.,()\[\]+-]", "", ar_name.strip())        
    if not ar_name:
        ar_name = 'PicardSpace Result'
            
    # add new AppResult to BaseSpace
    try:
        wb_proj = bs_api.getProjectById(wb_proj_num)    
        input_file = bs_api.getFileById(file_num)
        output_app_result = wb_proj.createAppResult(bs_api, ar_name, "PicardSpace AppResult", appSessionId=app_ssn_row.app_session_num, samples=[ sample ] )
    except Exception as e:
        return dict(err_msg=str(e))
    
    # add input AppResult to db
    input_app_result_id = db.input_app_result.insert(
        project_num=app_ssn_row.project_num,
        app_result_name=input_app_result.Name,
        app_result_num=ar_num,
        sample_num=sample_num)
    db.commit()
    
    # add input BAM file to db
    input_file_id = db.input_file.insert(
        app_result_id=input_app_result_id,
        is_paired_end=is_paired_end,
        genome_id=genome_id,
        file_num=file_num, 
        file_name=input_file.Name)
    db.commit()                    
                                                            
    # add new output AppResult to db            
    output_app_result_id = db.output_app_result.insert(
        app_session_id=app_ssn_row.id,
        project_num=wb_proj_num,
        app_result_name= ar_name,
        app_result_num=output_app_result.Id,
        sample_num=sample_num,        
        input_file_id=input_file_id)             
    db.commit()
    output_ar_row = db(db.output_app_result.id==output_app_result_id).select().first()
    output_ar = AppResult.init_from_db(output_ar_row)
    
    # begin download and analysis, update session status 
    if (current.debug_ps):
        app_ssn_row.update_record(status='starting download', message='')
        db.commit()   
        analyze_bs_file(input_file_id)
    elif (current.AWS_on_demand):
        app_ssn_row.update_record(status='analysis instance launching', message='Your analysis will begin within the next few minutes')
        db.commit()
        
        # ensure AWS info is in db
        aws = db(db.aws_data.id > 0).select().first()
        if not aws.region_name:
            output_ar.abort_and_refund("AWS connection data not available")
        try:
            conn = boto.ec2.connect_to_region(aws.region_name)
        except Exception as e:                                
            output_ar.abort_and_refund("error connection to AWS region")            
        user_data_script = ["#!/bin/sh",
            "exec > /home/www-data/web2py/applications/PicardSpace/private/user_data.log 2>&1",
            "set -x # turn on debug trace mode",
            "bash /home/www-data/web2py/applications/PicardSpace/private/init_instance.bash " + str(input_file_id),            
            "shutdown -h now"]            
        try:
            reservation = conn.run_instances(aws.analysis_image_id, 
                key_name = aws.analysis_key_name, 
                instance_type = aws.analysis_instance_type, 
                security_groups = [aws.analysis_security_group], 
                placement = aws.analysis_availability_zone, 
                user_data = '\n'.join(user_data_script), 
                instance_initiated_shutdown_behavior='terminate')
        except EC2ResponseError as e:            
            output_ar.abort_and_refund("error launching analysis instance: {0}".format(str(e.reason)))        
        except Exception as e:            
            output_ar.abort_and_refund("error launching analysis instance")
        else:
            # store new instance id in db for troubleshooting
            if reservation.instances:
                instance = reservation.instances[0]
                db.aws_session.insert(app_session_id = app_ssn_row.id,
                    instance_id = instance.id)
                db.commit()
            else:
                output_ar.abort_and_refund("error launching the analysis instance")                    
    else:
        app_ssn_row.update_record(status='analysis queued', message='')
        db.commit()
        scheduler.queue_task(analyze_bs_file, 
                             pvars = {'input_file_id':input_file_id}, 
                             timeout = 86400, # seconds
                             immediate = True)                     
    # everything should now be in db
    clear_session_vars()

    # redirect user to view_results page -- with message that their analysis started
    redirect(URL('view_results', vars=dict(message='Your Analysis Has Started!')))    


@auth.requires_login()
def view_results():
    """
    Main page for logged-in users - shows list of past analyses and option to launch new analysis
    """        
    ret = dict(message="", app_ssns=[], ar_start="", ar_end="", ar_tot="", 
               next_offset="", next_limit="", prev_offset="", prev_limit="", 
               ar_back="", err_msg="")
    # if arriving from just-launched analysis, display msg 'just launched'        
    if request.get_vars.message:
        ret['message'] = request.get_vars.message    
        
    # handle pagination vars
    ret['ar_offset'] = 0
    const_ar_limit = 5
    ret['ar_limit'] = const_ar_limit
    if request.vars.ar_offset:
        ret['ar_offset'] = int(request.vars.ar_offset)
    if request.vars.ar_limit:
        ret['ar_limit'] = int(request.vars.ar_limit)    

    # record offset and limit for 'back' link    
    ret['ar_back'] = URL('view_results', vars=dict(ar_offset=ret['ar_offset'],
                                                   ar_limit=ret['ar_limit']))                
    # get BaseSpace API
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    app = db(db.app_data.id > 0).select().first()
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              session.app_session_num, user_row.access_token)        
    except Exception as e:
        ret['err_msg'] = "Error getting BaseSpace API object: " + str(e)
        return ret            
    # get app sessions that have analyses for the current user, 
    # sorted by date created, limited to offset and limit    
    ssn_rows = db((db.app_session.status != 'newly created') 
        & (db.app_session.user_id==auth.user_id)).select(
        limitby=(ret['ar_offset'], ret['ar_offset'] + ret['ar_limit']),
        orderby=~db.app_session.date_created)

    # get total number of app sessions with analyses
    ret['ar_tot'] = db((db.app_session.status != 'newly created') 
        & (db.app_session.user_id==auth.user_id)).count()            
    
    # don't allow indexing off end of app_results list
    ret['ar_end'] = ret['ar_offset'] + ret['ar_limit']        
    if ret['ar_end'] > ret['ar_tot']:
        ret['ar_end'] = ret['ar_tot']                                                    
    
    app_ssns = []
    for ssn_row in ssn_rows:
        # handling only one app result per app session
        rslt_row = db(db.output_app_result.app_session_id==ssn_row.id).select().first()
        # get project name for each AppResult    
        ssn_view = {'link_to_results':False, 'app_result_name':'', 
                    'project_name':'None', 'status':ssn_row.status, 
                    'app_session_id':ssn_row.id, 'notes':ssn_row.message, 
                    'date_created':ssn_row.date_created }
        if rslt_row:
            try:
                proj = bs_api.getProjectById(rslt_row.project_num)
            except Exception as e:
                # project may have been transfered to another user - list as not accessible
                # - not differentiating between url timeout and missing project
                ssn_view['link_to_results'] = False
                ssn_view['app_result_name'] = 'Not Accessible: ' + rslt_row.app_result_name
                ssn_view['project_name'] = 'Not Accessible'                                                                                
            else:
                ssn_view['link_to_results'] = True
                ssn_view['app_result_name'] = rslt_row.app_result_name
                ssn_view['project_name'] = proj.Name            
        app_ssns.append(ssn_view)
    ret['app_ssns'] = app_ssns
                
    # calculate next and prev start/end                                                                                                                                        
    ret['next_offset'] = ret['ar_end']
    ret['next_limit'] = const_ar_limit    
    ret['prev_offset'] = ret['ar_offset'] - const_ar_limit
    ret['prev_limit'] = const_ar_limit                                                                    
    if ret['next_offset'] > ret['ar_tot']:
        ret['next_offset'] = ret['ar_tot']    
    if ret['prev_offset'] < 0:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      
        ret['prev_offset'] = 0

    # handle zero app results
    if ret['ar_tot'] == 0:
        ret['ar_start'] = 0
    else:
        ret['ar_start'] = ret['ar_offset'] + 1
    return ret  

    
@auth.requires_login()
def view_alignment_metrics():
    """
    Display multiple picard metrics graphs and alignment metrics
    """
    ret = dict(aln_tbl="", hdr="", sample_num="", sample_sampleid ="",
               input_file_name="", input_project_name="", 
               input_app_result_name="", output_app_result_name="", 
               output_project_name="", ar_back="",
               input_project_href="", output_project_href="",
               mult_metrics_stderr="", gc_bias_stderr="", aln_stderr="",
               qual_by_cycle_png="", qual_by_cycle_url="",
               qual_dist_png="", qual_dist_url="",
               gc_bias_png="", gc_bias_url="",
               insert_size_png="", insert_size_url="",
               genome="", err_msg="")
    app_session_id = request.get_vars.app_session_id    
    ret['aln_tbl'] = [["data not available"]]
        
    # get 'back' url of view results page
    if (request.vars['ar_back']):
        ret['ar_back'] = request.vars['ar_back']
    else:
        ret['ar_back'] = URL('view_results')
        
    # get AppResult from db
    user_row = db(db.auth_user.id==auth.user_id).select().first()
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    output_ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    input_file_row = db(db.input_file.id==output_ar_row.input_file_id).select().first()
    input_ar_row = db(db.input_app_result.id==input_file_row.app_result_id).select().first()
    app = db(db.app_data.id > 0).select().first()    
    genome_row = db(db.genome.id==input_file_row.genome_id).select().first()    
                
    # get Sample and Project from BaseSpace
    try:
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, 
                              app.baseSpaceUrl, app.version, 
                              ssn_row.app_session_num, user_row.access_token)        
        sample = bs_api.getSampleById(output_ar_row.sample_num)        
        output_project = bs_api.getProjectById(output_ar_row.project_num)
        input_project = bs_api.getProjectById(input_ar_row.project_num)
    except Exception as e:
        ret['err_msg'] = "Error retrieving items from BaseSpace: " + str(e)
        return ret            
    ret['sample_sampleid'] = sample.SampleId
    ret['sample_num'] = sample.Id
    ret['input_file_name'] = input_file_row.file_name 
    ret['input_project_name'] = input_project.Name 
    ret['input_app_result_name'] = input_ar_row.app_result_name  
    ret['output_app_result_name'] = output_ar_row.app_result_name 
    ret['output_project_name'] = output_project.Name

    ret['input_project_href'] = input_project.HrefBaseSpaceUI
    ret['output_project_href'] = output_project.HrefBaseSpaceUI    
    if genome_row:
        ret['genome'] = genome_row.display_name
    else:
        ret['genome'] = 'unknown'        
    
    # get BaseSpace links to output files
    app_result = AppResult.init_from_db(output_ar_row)
    
        
    # generate urls to individual metrics tables and stderr
    back = URL('view_alignment_metrics', vars=dict(app_session_id=app_session_id, ar_back=ret['ar_back']))    
    mm_stderr = app_result.get_output_file('mult_metrics_stderr')    
    if mm_stderr:
        ret['mult_metrics_stderr'] = URL("view_textfile", vars=dict(
            file_id = mm_stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = back))
    # support standalone aln metrics stderr
    else:        
        oaln_stderr = app_result.get_output_file('aln_stderr')
        if oaln_stderr:
            ret['aln_stderr'] = URL("view_textfile", vars=dict(
                file_id = oaln_stderr.bs_file_id, 
                app_session_id = app_session_id,
                back = back))
            
    gc_stderr = app_result.get_output_file('gc_bias_stderr')
    if gc_stderr:
        ret['gc_bias_stderr'] = URL("view_textfile", vars=dict(
            file_id = gc_stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = back))                
    ret['qual_by_cycle_url'] = URL("view_qual_by_cycle_metrics", vars=dict(
            app_session_id = app_session_id,
            back = back))
    ret['qual_dist_url'] = URL("view_qual_dist_metrics", vars=dict(
            app_session_id = app_session_id,
            back = back))
    ret['gc_bias_url'] = URL("view_gc_bias_metrics", vars=dict(
            app_session_id = app_session_id,
            back = back))    
    ret['insert_size_url'] = URL("view_insert_size_metrics", vars=dict(
            app_session_id = app_session_id,
            back = back))
    
    # get links to image files
    try:
        ret['qual_by_cycle_png'] = app_result.get_file_url('qual_by_cycle_png')
    except Exception as e:
        ret['err_msg'] = "Error retrieving qual by cycle file link from BaseSpace: " + str(e)
        return ret        
    try:
        ret['qual_dist_png'] = app_result.get_file_url('qual_dist_png')        
    except Exception as e:
        ret['err_msg'] = "Error retrieving qual dist file link from BaseSpace: " + str(e)
        return ret        
    try:
        ret['gc_bias_png'] = app_result.get_file_url('gc_bias_png')
    except Exception as e:
        ret['err_msg'] = "Error retrieving gc bias file link from BaseSpace: " + str(e)
        return ret        
    try:
        ret['insert_size_png'] = app_result.get_file_url('insert_size_png')
    except Exception as e:
        ret['err_msg'] = "Error retrieving insert size file link from BaseSpace: " + str(e)
        return ret            
    
    # get alignment metrics table
    try:
        f = app_result.download_file(file_type = 'aln_txt',
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret    
    
    if f:
        # read local file into array (for display in view)
        aln_tbl = []
        with open( f.local_path, "r") as ALN_QC:

            # get picard output header - collect lines finding line starting with 'CATEGORY'
            line = ALN_QC.readline()
            while line and not re.match("CATEGORY", line):
                ret['hdr'] += line
                line = ALN_QC.readline()
            # get picard metric data (and table headings)
            if line:
                aln_tbl.append(line.rstrip().split("\t"))
                for line in ALN_QC:
                    if line.rstrip():
                        aln_tbl.append(line.rstrip().split("\t"))
                # transpose list (for viewing - so it is long instead of wide)(now its a tuple)
                ret['aln_tbl'] = zip(*aln_tbl)
            
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(f.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                
    return ret


@auth.requires_login()
def view_textfile():
    """
    Display the contents of an output text file
    """
    ret = dict(back="", file_name="", file_contents="", err_msg="")    

    if ('file_id' not in request.vars or
        'app_session_id' not in request.vars):
        ret['err_msg'] = "We have a problem - expected file and app session ids but didn't receive them." 
        return ret             
    file_id = request.get_vars.file_id
    app_session_id = request.get_vars.app_session_id
    
    ret['back'] = URL('view_alignment_metrics')
    if 'back' in request.vars:    
        ret['back'] = request.vars.back        
    
    file_row = db(db.output_file.id==file_id).select().first()
    ssn_row = db(db.app_session.id==app_session_id).select().first()

    f = File(file_name=file_row.file_name,
             file_num=file_row.file_num)
    try:
        f.download_file(file_row.file_num,
            os.path.join(current.scratch_path, "viewing", ssn_row.app_session_num),
            app_session_id)
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret
        
    if f:
        ret['file_name'] = f.file_name
        with open(f.local_path, "r") as FH:
            cnt = 0
            for line in FH:
                ret['file_contents'] += line
                cnt += 1
                # don't display too many lines
                if cnt > 50000:
                    ret['file_contents'] += '(truncated)'
                    break
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(f.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                
    return ret


@auth.requires_login()
def view_qual_by_cycle_metrics():
    """
    Display picard's quality by cycle metrics
    """
    ret = dict(back="", data_tbl="", hdr="", stderr="", err_msg="")
    
    if 'app_session_id' not in request.vars:
        ret['err_msg'] = "We have a problem - expected app session id but didn't receive one." 
        return ret             
    app_session_id = request.get_vars.app_session_id
    
    ret['back'] = URL('view_alignment_metrics')
    if 'back' in request.vars:    
        ret['back'] = request.vars.back
    
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    ar = AppResult.init_from_db(ar_row)        
    
    # get stderr 'LOG'
    stderr = ar.get_output_file('mult_metrics_stderr')
    if stderr:
        ret['stderr'] = URL("view_textfile", vars=dict(
            file_id = stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = URL('view_qual_by_cycle_metrics', vars=dict(app_session_id = app_session_id, back = ret['back']))))    
    # get output text file
    try:
        f = ar.download_file(file_type = 'qual_by_cycle_txt',
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret                
        
    ret['data_tbl'] = [["data not available"]]            
    if f:
        # read local file into array (for display in view)
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("CYCLE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                data_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        data_tbl.append(line.rstrip().split("\t"))
                ret['data_tbl'] = data_tbl
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(f.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                             
    return ret


@auth.requires_login()
def view_qual_dist_metrics():
    """
    Display picard's quality distribution metrics
    """
    ret = dict(back="", data_tbl="", hdr="", stderr="", err_msg="")
    
    if 'app_session_id' not in request.vars:
        ret['err_msg'] = "We have a problem - expected app session id but didn't receive one." 
        return ret             
    app_session_id = request.get_vars.app_session_id
    
    ret['back'] = URL('view_alignment_metrics')
    if 'back' in request.vars:    
        ret['back'] = request.vars.back
    
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    ar = AppResult.init_from_db(ar_row)        
    
    # get stderr 'LOG'
    stderr = ar.get_output_file('mult_metrics_stderr')
    if stderr:
        ret['stderr'] = URL("view_textfile", vars=dict(
            file_id = stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = URL('view_qual_dist_metrics', vars=dict(app_session_id = app_session_id, back = ret['back']))))    
    # get output text file
    try:
        f = ar.download_file(file_type = 'qual_dist_txt',                            
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret                            
                    
    ret['data_tbl'] = [["data not available"]]         
    if f:
        # read local file into array (for display in view)
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("QUALITY", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                data_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        data_tbl.append(line.rstrip().split("\t"))
                ret['data_tbl'] = data_tbl
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(f.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                             
    return ret


@auth.requires_login()
def view_gc_bias_metrics():
    """
    Display picard's gc-bias summary and histogram metrics
    """
    ret = dict(back = "", sum_tbl="", hist_tbl="", hdr="", stderr="", err_msg="")        
    
    if 'app_session_id' not in request.vars:
        ret['err_msg'] = "We have a problem - expected app session id but didn't receive one." 
        return ret             
    app_session_id = request.get_vars.app_session_id
    
    ret['back'] = URL('view_alignment_metrics')
    if 'back' in request.vars:    
        ret['back'] = request.vars.back
    
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    ar = AppResult.init_from_db(ar_row)        
    
    # get stderr 'LOG'
    stderr = ar.get_output_file('gc_bias_stderr')
    if stderr:
        ret['stderr'] = URL("view_textfile", vars=dict(
            file_id = stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = URL('view_gc_bias_metrics', vars=dict(app_session_id = app_session_id, back = ret['back']))))    
    # get output text files - summary and histogram values
    try:
        sf = ar.download_file(file_type = 'gc_bias_summary',                              
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret                    
    try:
        hf = ar.download_file(file_type = 'gc_bias_txt',                               
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret                
               
    # first parse summary metrics file (then histogram data file)
    ret['hdr'] += 'GC Bias Summary Values:\n'     
    ret['sum_tbl'] = [["data not available"]]
    ret['hist_tbl'] = [["data not available"]]
    if sf and hf:
        # read local file into array (for display in view)
        sum_tbl = []
        with open( sf.local_path, "r") as QC:
            # get picard output header
            line = QC.readline()
            while line and not re.match("WINDOW_SIZE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                sum_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        sum_tbl.append(line.rstrip().split("\t"))
                ret['sum_tbl'] = sum_tbl                        

        # parse histogram data file    
        ret['hdr'] += '\nGC-Bias Histogram Values:\n'            
        hist_tbl = []
        with open( hf.local_path, "r") as QC:
            # get picard output header
            line = QC.readline()
            while line and not re.match("GC", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:
                hist_tbl.append(line.rstrip().split("\t"))
                for line in QC:
                    if line.rstrip():
                        hist_tbl.append(line.rstrip().split("\t"))
                ret['hist_tbl'] = hist_tbl
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(hf.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                  
    return ret


@auth.requires_login()
def view_insert_size_metrics():
    """
    Display picard's insert size metrics
    """
    ret = dict(back = "", hist_tbl="", data_tbl="", hdr="", stderr="", err_msg="")    

    if 'app_session_id' not in request.vars:
        ret['err_msg'] = "We have a problem - expected app session id but didn't receive one." 
        return ret             
    app_session_id = request.get_vars.app_session_id
    
    ret['back'] = URL('view_alignment_metrics')
    if 'back' in request.vars:    
        ret['back'] = request.vars.back
    
    ssn_row = db(db.app_session.id==app_session_id).select().first()
    ar_row = db(db.output_app_result.app_session_id==app_session_id).select().first()        
    ar = AppResult.init_from_db(ar_row)        
    
    # get stderr 'LOG'
    stderr = ar.get_output_file('mult_metrics_stderr')
    if stderr:
        ret['stderr'] = URL("view_textfile", vars=dict(
            file_id = stderr.bs_file_id, 
            app_session_id = app_session_id,
            back = URL('view_insert_size_metrics', vars=dict(app_session_id = app_session_id, back = ret['back']))))    
    # get output text file
    try:
        f = ar.download_file(file_type = 'insert_size_txt',                              
            dest_path = os.path.join(current.scratch_path, "viewing", str(ssn_row.app_session_num)))
    except Exception as e:
        ret['err_msg'] = "Error downloading file from BaseSpace: " + str(e)
        return ret                            
                    
    ret['hist_tbl'] = [["data not available"]]
    ret['data_tbl'] = [["data not available"]]                            
    if f:
        # read local file into array (for display in view)
        hist_tbl = []
        data_tbl = []
        with open( f.local_path, "r") as QC:

            # get picard output header
            line = QC.readline()
            while line and not re.match("MEDIAN_INSERT_SIZE", line):
                ret['hdr'] += line
                line = QC.readline()
            # get picard metric data (and table headings)
            if line:                
                data_tbl.append(line.rstrip().split("\t")) # summary headers
                line = QC.readline()
                if line:
                    data_tbl.append(line.rstrip().split("\t")) # summary data line
                    line = QC.readline()
                    ret['data_tbl'] = zip(*data_tbl)
                    while line and not re.match("insert_size", line): # add to header
                        ret['hdr'] += line
                        line = QC.readline()
                    if line:
                        hist_tbl.append(line.rstrip().split("\t")) # histogram header
                        for line in QC:
                            if line.rstrip():
                                hist_tbl.append(line.rstrip().split("\t")) # histogram data
                ret['hist_tbl'] = hist_tbl
        # delete local files
        try:
            shutil.rmtree(os.path.dirname(f.local_path))            
        except Exception as e:
            ret['err_msg'] = "Error deleting local files: " + str(e)            
            return ret                  
    return ret


@auth.requires_login()
def help_me():
    """
    Display 'help' info such as troubleshooting help
    """
    return dict(bs_url=auth.settings.logout_next)


# for user authentication
def user(): return dict(form=auth())
