#!/usr/bin/env python
# coding: utf8
import os.path
from subprocess import call
from datetime import datetime
import shutil
import re
from gluon import *
from BaseSpacePy.api.BaseSpaceAPI import BaseSpaceAPI
from BaseSpacePy.api.BillingAPI import BillingAPI


class UnrecognizedProductException(Exception):
    def __init__(self, value):
        self.parameter = 'The following product name was not recognized: ' + str(value)
    def __str__(self):
        return repr(self.parameter)


class File(object):
    """
    A File in BaseSpace
    """
    def __init__(self, file_name, local_path=None, file_num=None, 
                 bs_file_id=None, app_result_id=None, genome_id=None, 
                 is_paired_end=None):              
        self.file_name = file_name
        self.local_path = local_path # full path including file name
        self.file_num = file_num        
        self.bs_file_id = bs_file_id
        self.app_result_id = app_result_id
        self.genome_id = genome_id
        self.is_paired_end = is_paired_end


    def download_file(self, file_num, local_dir, app_session_id):
        """
        Download a file from BaseSpace into the provided directory (created if doesn't exist)
        """
        db = current.db
        # get access token for app session's user (can't use current user since may be accessing from scheduler worker)        
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
        self.local_path = os.path.join(local_dir, f.Name)                          
        

    def get_file_url(self, file_num, app_session_id):
        """
        Returns the S3 link to the provided file
        """
        db = current.db
        # get access token for app session's user (can't use current user since may be accessing from scheduler worker)        
        ssn_row = db(db.app_session.id==app_session_id).select().first()
        user_row = db(db.auth_user.id==ssn_row.user_id).select().first()                                                        
        app = db(db.app_data.id > 0).select().first()
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, ssn_row.app_session_num, user_row.access_token)
        f = bs_api.getFileById(file_num)                    
                
        return f.getFileUrl(bs_api)                
        
    
class AnalysisInputFile(File):
    """
    Class to download, analyze, and write-back results of a single file    
    """            
    def download_and_start_analysis(self):
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
        time_start_download = datetime.now()        
        
        # set local_path location and url for downloading, and download file from BaseSpace        
        local_dir = AppResult.scratch_path(ssn_row.app_session_num)        
        self.download_file(file_num=self.file_num, local_dir=local_dir, app_session_id=ssn_row.id)
        
        # update file's local path
        file_row = db(db.input_file.id==self.bs_file_id).select().first()     
        #file_row.update_record(local_path=local_file)
        file_row.update_record(local_path=self.local_path)
        db.commit()               
    
        # update app_session status to 'download complete, in analysis queue'
        ssn_row.update_record(status="queued for analysis", message="download complete")
        db.commit()
        time_end_download = datetime.now()
        time_download = time_end_download - time_start_download 

        # add file to analysis queue
        #if (current.debug_ps):
        #analyze_bs_file(input_file_id=self.bs_file_id, time_download=time_download)                              
        #else:
        #    current.scheduler.queue_task(analyze_bs_file, 
        #                                 pvars = {'input_file_id':self.bs_file_id, 'time_download':time_download}, 
        #                                 timeout = 86400) # seconds

        # create AppResult object to analyze downloaded File
        app_result = AppResult(
            app_result_id=ar_row.id,
            app_session_id=ar_row.app_session_id,
            project_num=ar_row.project_num,
            app_result_name=ar_row.app_result_name,
            app_result_num=ar_row.app_result_num)                        
        app_result.run_analysis_and_writeback(self, time_download)                


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

    @staticmethod
    def init_from_db(row):
        """
        Return an AppResult object from the provided db Row object
        """
        return AppResult(
                app_result_id=row.id,
                app_session_id=row.app_session_id,
                project_num=row.project_num,
                app_result_name=row.app_result_name,
                app_result_num=row.app_result_num)  
    

    @staticmethod
    def scratch_path(app_ssn_num):
        """
        Return the path to the local working directory for downloading and analysis
        """
        return os.path.join(current.scratch_path, "inputs", str(app_ssn_num))        
                      

    def run_analysis_and_writeback(self, input_file, time_download=None):
        """
        Run picard on the provided file and writeback output files to BaseSpace, updating statuses as we go
        """
        db = current.db                                    
        # update db and BaseSpace App Session with status
        self.update_status('running', 'picard is running', 'running')
        time_start_als = datetime.now()
                
        # run picard                        
        if self._run_picard(input_file):
            message = 'analysis successful; results not yet written back to BaseSpace'
            analysis_success = True            
        else:
            message = 'analysis failed - see stderr.txt; results not yet written back to BaseSpace'
            analysis_success = False        
        self.update_status("writing back", message)       
        time_start_wb = datetime.now()
       
        # write-back output files            
        self._writeback_app_result_files()
        message = "analysis and write-back successful"
        if not analysis_success:        
            message = "analysis failed - see stderr.txt; writeback successful"        
        self.update_status('deleting local files', message)    
                
        # delete local input and output files
        os.remove(input_file.local_path)
        while(len(self.output_files)):
            f = self.output_files.pop()        
            os.remove(f.local_path)         
                
        message += "; deleted local files"
        time_end_wb = datetime.now()

        # create timing file, write-back to BaseSpace
        self.writeback_timing(time_download = time_download,
                              time_analysis = time_start_wb - time_start_als,
                              time_writeback = time_end_wb - time_start_wb)        
        
        # delete scratch path
        #shutil.rmtree(os.path.dirname(input_file.local_path))
        ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        shutil.rmtree(self.scratch_path(ssn_row.app_session_num))        

        # delete local path from deleted output files in db        
        f_rows = db(db.output_file.app_result_id==self.app_result_id).select()
        for f_row in f_rows:
            f_row.update_record(local_path="")
        db.commit()

        # update session status
        status = 'complete'
        if not analysis_success:                    
            status = 'aborted'        
        self.update_status(status, message, status)


    def writeback_timing(self, time_download, time_analysis, time_writeback):
        """
        Write-back the provided timings (timedelta objects) to a file in BaseSpace
        """
        db = current.db
        time_file = "timing.txt"
        ssn_row = db(db.app_session.id==self.app_session_id).select().first()
        scratch_path = self.scratch_path(ssn_row.app_session_num)        
        time_path = os.path.join(scratch_path, time_file)        
        with open(time_path, "w") as FT:            
            if time_download:                
                time_total = time_download + time_analysis + time_writeback
                FT.write("TOTAL time: " + str(time_total) + "\n")
                FT.write("Download time: " + str(time_download) + "\n")                
            FT.write("Analysis time: " + str(time_analysis) + "\n")
            FT.write("Write-back time: " + str(time_writeback) + "\n")
        f_time = File(app_result_id=self.app_result_id,
                      file_name=time_file,
                      local_path=time_path)        
        self.output_files.append(f_time)    
        self._writeback_app_result_files()
        # remove local file
        os.remove(time_path)        
        self.output_files.pop()
            
            
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
        Run picard tools on a BAM file       
        """
        rv = self._collect_multiple_metrics(input_file)
        rv = rv and self._collect_gc_bias_metrics(input_file)

        # run individual programs to support command-line flags - not currently supported                
        #rv = self._collect_alignment_metrics(input_file)        
        #rv = rv and self._mean_quality_by_cycle(input_file)
        #rv = rv and self._quality_score_distribution(input_file)
        
        #if input_file.is_paired_end == 'paired':
        #    rv = rv and self._collect_insert_size_metrics(input_file)
                                    
        return rv


    def _collect_multiple_metrics(self, input_file):    
        """
        Run picard's CollectMultipleMetrics on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                        
                        
        # assemble output file names and paths
        outpath_base = input_path                            
        outpaths = [input_path + current.file_ext['aln_txt'],                    
                    input_path + current.file_ext['qual_by_cycle_txt'],
                    input_path + current.file_ext['qual_by_cycle_pdf'],
                    input_path + current.file_ext['qual_dist_txt'],
                    input_path + current.file_ext['qual_dist_pdf'], ]
        outpath_stdout = input_path + current.file_ext['mult_metrics_stdout']
        outpath_stderr = input_path + current.file_ext['mult_metrics_stderr']                                
        
        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "CollectMultipleMetrics.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),            
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_base,                                
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true",
            "PROGRAM=CollectAlignmentSummaryMetrics",
            "PROGRAM=QualityScoreDistribution",
            "PROGRAM=MeanQualityByCycle", ]

        # calculate insert size metrics only for paired-end reads
        if input_file.is_paired_end == 'paired':
            command.append("PROGRAM=CollectInsertSizeMetrics")
            outpaths.append(input_path + current.file_ext['insert_size_txt'])
            outpaths.append(input_path + current.file_ext['insert_size_hist'])
        
        # add optional genome if available
        gen_row = db(db.genome.id==input_file.genome_id).select().first()
        if gen_row:
            genome_path = os.path.join(current.genomes_path, gen_row.local_path)
            fasta_path = os.path.join(genome_path, "Sequence", "WholeGenomeFasta", "genome.fa")
            command.append("REFERENCE_SEQUENCE=" + fasta_path)                                            
        
        self.update_status('running', 'Collecting multiple metrics')
        
        # run command, write stdout, stderr to files
        with open(outpath_stdout, "w") as FO:            
            with open(outpath_stderr, "w") as FE:                                        
                rcode = call(command, stdout=FO, stderr=FE)   
        
        # rename files with long extensions (can't upload to BaseSpace due to bug)
        # these file don't initially have file extensions (picard's fault) -- add them        
        os.rename(input_path + current.file_ext['aln_txt'][:-4], input_path + current.file_ext['aln_txt'])
        os.rename(input_path + current.file_ext['qual_by_cycle_txt'][:-4], input_path + current.file_ext['qual_by_cycle_txt'])
        os.rename(input_path + current.file_ext['qual_dist_txt'][:-4], input_path + current.file_ext['qual_dist_txt'])
        if input_file.is_paired_end == 'paired':
            os.rename(input_path + current.file_ext['insert_size_txt'][:-4], input_path + current.file_ext['insert_size_txt']) 
       
        # use method below to add output files to writeback list
        self._run_command("", outpaths, outpath_stdout, outpath_stderr)
        # return true if command was successful
        if rcode == 0:
            return(True)
        else:
            return(False)  


    def _collect_alignment_metrics(self, input_file):    
        """
        Run picard's CollectAlignmentSummaryMetrics on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                
                
        # assemble output file names and paths                                                                    
        outpath_txt = input_path + current.file_ext['aln_txt']
        outpaths = [outpath_txt,]
        outpath_stdout = input_path + current.file_ext['aln_stdout']
        outpath_stderr = input_path + current.file_ext['aln_stderr']
        
        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "CollectAlignmentSummaryMetrics.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_txt, 
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        
        self.update_status('running', 'Collecting alignment metrics')
        return self._run_command(command, outpaths, outpath_stdout, outpath_stderr)    
        

    def _collect_gc_bias_metrics(self, input_file):    
        """
        Run picard's CollectGcBiasMetrics on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                
                        
        # assemble output file names and paths
        outpath_txt = input_path + current.file_ext['gc_bias_txt']        
        outpath_pdf = input_path + current.file_ext['gc_bias_pdf']
        outpath_sum = input_path + current.file_ext['gc_bias_summary']
        outpaths = [outpath_txt, outpath_pdf, outpath_sum]               
        outpath_stdout = input_path + current.file_ext['gc_bias_stdout']
        outpath_stderr = input_path + current.file_ext['gc_bias_stderr']                            

        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "CollectGcBiasMetrics.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_txt,
            "CHART_OUTPUT=" + outpath_pdf,
            "SUMMARY_OUTPUT=" + outpath_sum, 
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        
        # add required genome, return if not available
        gen_row = db(db.genome.id==input_file.genome_id).select().first()
        if gen_row:                               
            genome_path = os.path.join(current.genomes_path, gen_row.local_path)
            fasta_path = os.path.join(genome_path, "Sequence", "WholeGenomeFasta", "genome.fa")
            command.append("REFERENCE_SEQUENCE=" + fasta_path)                                            
        else:
            return True   
        
        self.update_status('running', 'Collecting gc-bias metrics')
        return self._run_command(command, outpaths, outpath_stdout, outpath_stderr)                                                                                                    


    def _collect_insert_size_metrics(self, input_file):    
        """
        Run picard's CollectInsertSizeMetrics on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                
                        
        # assemble output file names and paths
        outpath_txt = input_path + current.file_ext['insert_size_txt']        
        outpath_hist = input_path + current.file_ext['insert_size_hist']                        
        outpaths = [outpath_txt, outpath_hist]
        outpath_stdout = input_path + current.file_ext['insert_size_stdout']
        outpath_stderr = input_path + current.file_ext['insert_size_stderr']        
        
        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "CollectInsertSizeMetrics.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),            
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_txt,
            "HISTOGRAM_FILE=" + outpath_hist,             
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        
        # add optional genome if available
        gen_row = db(db.genome.id==input_file.genome_id).select().first()
        if gen_row:
            genome_path = os.path.join(current.genomes_path, gen_row.local_path)
            fasta_path = os.path.join(genome_path, "Sequence", "WholeGenomeFasta", "genome.fa")
            command.append("REFERENCE_SEQUENCE=" + fasta_path)                                            
        
        self.update_status('running', 'Collecting insert-size metrics')
        return self._run_command(command, outpaths, outpath_stdout, outpath_stderr)          


    def _mean_quality_by_cycle(self, input_file):    
        """
        Run picard's MeanQualityByCycle on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                
                        
        # assemble output file names and paths
        outpath_txt = input_path + current.file_ext['qual_by_cycle_txt']        
        outpath_pdf = input_path + current.file_ext['qual_by_cycle_pdf']                        
        outpaths = [outpath_txt, outpath_pdf]
        outpath_stdout = input_path + current.file_ext['qual_by_cycle_stdout']
        outpath_stderr = input_path + current.file_ext['qual_by_cycle_stderr']        
        
        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "MeanQualityByCycle.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),            
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_txt,
            "CHART_OUTPUT=" + outpath_pdf,             
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        
        # add optional genome if available
        gen_row = db(db.genome.id==input_file.genome_id).select().first()
        if gen_row:
            genome_path = os.path.join(current.genomes_path, gen_row.local_path)
            fasta_path = os.path.join(genome_path, "Sequence", "WholeGenomeFasta", "genome.fa")
            command.append("REFERENCE_SEQUENCE=" + fasta_path)                                            
        
        self.update_status('running', 'Calculating mean quality by cycle')
        return self._run_command(command, outpaths, outpath_stdout, outpath_stderr)


    def _quality_score_distribution(self, input_file):    
        """
        Run picard's QualityScoreDistribution on a BAM file       
        """
        input_path = input_file.local_path
        db = current.db                
                        
        # assemble output file names and paths
        outpath_txt = input_path + current.file_ext['qual_dist_txt']        
        outpath_pdf = input_path + current.file_ext['qual_dist_pdf']                        
        outpaths = [outpath_txt, outpath_pdf]
        outpath_stdout = input_path + current.file_ext['qual_dist_stdout']
        outpath_stderr = input_path + current.file_ext['qual_dist_stderr']        
        
        # assemble picard command and run it
        jar = os.path.join(current.picard_path, "QualityScoreDistribution.jar")
        command = ["java", "-jar", "-Xms1G",
            os.path.join(current.request.folder, jar),            
            "INPUT=" + input_path, 
            "OUTPUT=" + outpath_txt,
            "CHART_OUTPUT=" + outpath_pdf,             
            "VALIDATION_STRINGENCY=LENIENT",
            "ASSUME_SORTED=true"]
        
        # add optional genome if available
        gen_row = db(db.genome.id==input_file.genome_id).select().first()
        if gen_row:
            genome_path = os.path.join(current.genomes_path, gen_row.local_path)
            fasta_path = os.path.join(genome_path, "Sequence", "WholeGenomeFasta", "genome.fa")
            command.append("REFERENCE_SEQUENCE=" + fasta_path)                                            
        
        self.update_status('running', 'Calculating quality score distribution')
        return self._run_command(command, outpaths, outpath_stdout, outpath_stderr)


    def _run_command(self, command, outpaths, outpath_stdout, outpath_stderr):
        """
        Run the provided command, and return the command's return value
        Writeback files in the outpaths list and stdout + stderr
        """
        # run command, write stdout, stderr to files
        rcode = 0
        if (command):
            with open(outpath_stdout, "w") as FO:            
                with open(outpath_stderr, "w") as FE:                                        
                    rcode = call(command, stdout=FO, stderr=FE)        
        
        # add output files to writeback list
        for path in outpaths:    
            if (os.path.exists(path) and os.path.getsize(path)):           
                f = File(app_result_id=self.app_result_id,
                    file_name=os.path.split(path)[1],
                    local_path=path)
                self.output_files.append(f)
                               
        # truncate grossly long stderr (> 10 MB)
        if os.path.getsize(outpath_stderr) > 10000000:
            with open(outpath_stderr, "r+") as FE:
                FE.truncate(10000000)
            with open(outpath_stderr, "a") as FE:
                FE.write("[Truncated]")                        
        
        # add stderr to writeback list (if non-empty)
        if outpath_stderr:
            f_stderr = File(app_result_id=self.app_result_id,
                file_name=os.path.split(outpath_stderr)[1],
                local_path=outpath_stderr)                                
            self.output_files.append(f_stderr)
            
        # add stdout to writeback list (if non-empty)
        if os.path.getsize(outpath_stdout):
            f_stdout = File(app_result_id=self.app_result_id,
                file_name=os.path.split(outpath_stdout)[1],
                local_path=outpath_stdout)        
            self.output_files.append(f_stdout)            
                    
        # return true if command was successful
        if rcode == 0:
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
            db.output_file.insert(app_result_id=f.app_result_id,
                                  file_num=bs_file.Id, 
                                  file_name=f.file_name, 
                                  local_path=f.local_path)                                   
            db.commit()


    def download_file(self, file_ext, dest_path):
        """
        Downloads file with provided extension from BaseSpace to provided destination path 
        """
        db = current.db
        # get output file info from db    
        f_rows = db(db.output_file.app_result_id==self.app_result_id).select()
        f_row = None
        for row in f_rows:
            # find file with aln metrics extension
            m = re.search(file_ext + "$", row.file_name)
            if m:
                f_row = row
                break
        if f_row:                    
            f = File(app_result_id=f_row.app_result_id,
                    file_name=f_row.file_name,
                    file_num=f_row.file_num)                                                
            f.download_file(f_row.file_num, dest_path, self.app_session_id)                  
            return f


    def get_file_url(self, file_ext):
        """
        Returns S3 link of file with provided extension 
        """
        db = current.db
        # get output file info from db    
        f_rows = db(db.output_file.app_result_id==self.app_result_id).select()
        f_row = None
        for row in f_rows:
            # find file with aln metrics extension
            m = re.search(file_ext + "$", row.file_name)
            if m:
                f_row = row
                break
        if f_row:                    
            f = File(app_result_id=f_row.app_result_id,
                    file_name=f_row.file_name,
                    file_num=f_row.file_num)                                                
            return f.get_file_url(f_row.file_num, self.app_session_id)            


class ProductPurchase(object):
    """
    A product that a user may purchase
    """
    def __init__(self, prod_name, tags=[]):
        """
        Initialize product with price and num from db
        """              
        db=current.db        
        prod_row = db(db.product.name==prod_name).select().first()
        if not prod_row:
            raise UnrecognizedProductException(prod_name)
        self.prod_name = prod_name
        self.tags = tags
        self.prod_id = prod_row.id
        self.prod_price = prod_row.price
        self.prod_num = prod_row.num
        self.file_num = None
        self.amount = None
        self.prod_quantity = None

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
                self.prod_quantity = 0
            else:
                self.prod_quantity = 1                                   
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


def analyze_bs_file(input_file_id):
    """
    Downloads file from BaseSpace -- called from scheduler worker
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
        is_paired_end=f_row.is_paired_end,
        genome_id=f_row.genome_id,
        bs_file_id=f_row.id,
        file_num=f_row.file_num,
        file_name=f_row.file_name,
        local_path=f_row.local_path)

    # download the file from BaseSpace and queue analysis
    try:
        als_file.download_and_start_analysis()
    except Exception as e:            
        # update AppSession status in db and BaseSpace
        ssn_row.update_record(status='aborted', message=str(e))            
        db.commit()
        
        app = db(db.app_data.id > 0).select().first()
        user_row = db(db.auth_user.id==ssn_row.user_id).select().first()            
        bs_api = BaseSpaceAPI(app.client_id, app.client_secret, app.baseSpaceUrl, app.version, ssn_row.app_session_num, user_row.access_token)            
        app_ssn = bs_api.getAppSessionById(ssn_row.app_session_num)
        message = "Error downloading file from BaseSpace: {0}".format(str(e))            
        app_ssn.setStatus(bs_api, 'aborted', message[:128])                    
        print message # user won't see this
        
        # perform refund if user paid for analysis
        pr_row = db(db.purchase.app_session_id==ssn_row.id).select().first()
        if int(pr_row.amount_total) > 0:
            store_api = BillingAPI(app.store_url, app.version, ssn_row.app_session_num, user_row.access_token)           
            if pr_row.refund_status == 'NOTREFUNDED':
                comment = 'Automatic refund was triggered by a PicardSpace error'
                store_api.refundPurchase(pr_row.purchase_num, pr_row.refund_secret, 
                                         comment=comment)
                # set local refund status to 'COMPLETED' and update ssn status msg
                pr_row.update_record(refund_status='COMPLETED', comment=comment)
                ssn_row.update_record(message="[Purchase Refunded] " + str(e))            
                db.commit()                                            
        # raise exception so scheduler will mark job as failed
        # note if not using scheduler (manual debug) this shows exception in to browser
        raise
    # sanity commit to db for web2py Scheduler
    db.commit()

