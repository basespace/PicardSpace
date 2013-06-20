PicardSpace
===========

PicardSpace is a sample web application for BaseSpace that calculates alignment metrics with the open-source tool Picard. It runs Picard's CollectMultipleMetrics and CollectGcBiasMetrics programs on a BAM file.

Below are instructions for setting up a local installation of PicardSpace. A web server will run on your local machine and communicate with BaseSpace via the BaseSpace API. Analyses will run on your local machine and output files will be written back to BaseSpace.


Setup
=====
The instructions are for use with Ubuntu or Mac OSX.

1. Install the BaseSpace python SDK.

        git clone https://github.com/basespace/basespace-python-sdk.git
        cd basespace-python-sdk/src
        sudo python setup.py install
        (or)
        python setup.py install --prefix=/in/your/PYTHONPATH

2. Install pycurl (Mac only). The easiest way to this is using homebrew and pip, which requires installing a new version of python.
        
        ruby -e "$(curl -fsSL https://raw.github.com/mxcl/homebrew/go)"
        (suggested: run 'brew doctor' so homebrew works better with your machine)
        brew install python
        pip install pycurl

3. Install ImageMagick.

        sudo apt-get install imagemagick
        (or on Mac)
        brew install imagemagick
        
4. Install R. On Mac, download the latest package here (http://cran.cnr.berkeley.edu/bin/macosx/R-latest.pkg) and double-click to install. On Ubuntu:
 
        sudo apt-get install r-base

5. Ensure that java is installed (To test, type 'java -version'). To install on ubuntu:

        sudo apt-get --yes install default-jre

6. Install web2py. If you're on Mac OSX, don't download the pre-built Mac application. On Ubuntu you may also need to install python-tk.

        wget http://www.web2py.com/examples/static/web2py_src.zip
        unzip web2py_src.zip
        sudo apt-get install python-tk

7. Add PicardSpace to the web2py applications.

        cd web2py/applications
        git clone https://github.com/basespace/PicardSpace.git

8. Download genomes (this may take awhile).

        cd PicardSpace/private
        mkdir genomes; cd genomes
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/Homo_sapiens/UCSC/hg19/Homo_sapiens_UCSC_hg19.tar.gz
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/Escherichia_coli_K_12_DH10B/NCBI/2008-03-17/Escherichia_coli_K_12_DH10B_NCBI_2008-03-17.tar.gz
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/Mus_musculus/UCSC/mm9/Mus_musculus_UCSC_mm9.tar.gz
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/PhiX/Illumina/RTA/PhiX_Illumina_RTA.tar.gz
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/Rhodobacter_sphaeroides_2.4.1/NCBI/2005-10-07/Rhodobacter_sphaeroides_2.4.1_NCBI_2005-10-07.tar.gz
        wget ftp://igenome:G3nom3s4u@ussd-ftp.illumina.com/Bacillus_cereus_ATCC_10987/NCBI/2004-02-13/Bacillus_cereus_ATCC_10987_NCBI_2004-02-13.tar.gz
        tar -zvxf *.tar.gz

9. Start web2py (and the web2py Scheduler), first navigating to the main 'web2py' directory. A web browser should launch with address localhost:8000.

        cd ../../..
        python web2py.py -K PicardSpace -X

10. Register your new PicardSpace app on the BaseSpace developer portal (developer.basespace.illumina.com). Configure your app with the following: for 'App Launch Location' choose 'Projects', and for 'Home Page' enter 'http://localhost:8000/PicardSpace'.

11. Add a product to your product catalog in the BaseSpace dev portal (you may need to contact BaseSpace to get permission to add pricing to your app). Under the pricing tab, add a new consumable product named 'AlignmentQC' with a price of 2 iCredits (or whatever you wish). You'll need the new product Id in the next step.

12. Set app data and product info in the local database. Use the web2py admin panel (localhost:8000/PicardSpace/appadmin/index) to edit your local database. For table 'app_data', add your client_id, client_secret, and redirect_uri from the dev portal Details tab. For table 'product', add the product info you just added in the dev portal, with product.name=AlignmentQC, product.num=the id from the pricing tab in the dev portal, and product.price=your price.

Now launch your new app in BaseSpace with any Project that contains an AppResult with a small BAM file.


