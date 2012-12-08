import time
from picardSpace import AnalysisInputFile

while True:
    # iterate through all entries in the download queue
    for row in db(db.download_queue.status=='pending').select():

        # get queued file from db
        f_row = db(db.bs_file.id==row.bs_file_id).select().first()
        ar_row = db(db.app_result.input_file_id==f_row.id).select().first()

        # update status of app result
        ar_row.update_record(status='downloading')
        db.commit()

        # create a File object
        als_file = AnalysisInputFile(
            app_result_id=f_row.app_result_id, # incorrect
            bs_file_id=f_row.id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        # download the file from BaseSpace
        try:
            als_file.download_and_analyze()
        except Exception as e:            
            # print error msg, and update download queue and AppResult status in db
            print "Error: {0}".format(str(e))
            row.update_record(status='error')
            ar_row.update_record(status='error', message=str(e))            
        else:
            row.update_record(status='complete')
        db.commit()

    time.sleep(5) # check every x seconds

#python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/downloadfiles.py
