import time
from picardSpace import AnalysisInputFile

while True:
    # iterate through all entires in the download queue
    for row in db(db.download_queue.status=='pending').select():

        # get queued app result from db
        # note: only downloading 1 file per app result for now
        f_row = db(db.bs_file.app_result_id==row.app_result_id).select().first()

        # update status of app result
        ar_row = db(db.app_result.id==row.app_result_id).select().first()
        ar_row.update_record(status="downloading")
        db.commit()

        # create a File object
        als_file = AnalysisInputFile(
            app_result_id=f_row.app_result_id,
            bs_file_id=f_row.id,
            #app_session_id=f_row.app_session_id,
            file_num=f_row.file_num,
            file_name=f_row.file_name,
            local_path=f_row.local_path)

        # download the file from BaseSpace
        try:
            als_file.download_and_analyze()
        except Exception as e:
            # TODO print to log file
            print "Error: {0}".format(str(e))
            row.update_record(status='error')
        else:
            row.update_record(status='complete')
        db.commit()

    time.sleep(5) # check every x seconds

#python web2py.py -S picardSpace -M -R applications/picardSpace/private/downloadfiles.py
