PicardSpace
===========

A website that runs Picard tools for BaseSpace.


Setup
=====
These steps have been tested on Ubuntu and Mac OSX.

1. Download the BaseSpace python SDK.

        git clone https://github.com/basespace/basespace-python-sdk.git
        cd basespace-python-sdk/src
        sudo python setup.py install
        (or)
        python setup.py install --prefix=/in/your/PYTHONPATH

2. On Mac OSX, install pycurl (a SDK dependency). The easiest way to this is using homebrew and pip, which requires installing a new version of python.
        
        ruby -e "$(curl -fsSL https://raw.github.com/mxcl/homebrew/go)"
        (suggested: run 'brew doctor' so homebrew works better with your machine)
        brew install python
        pip install pycurl

3. Download and unzip web2py source code. If you're on Mac OSX, don't download the pre-built Mac application.

        wget http://www.web2py.com/examples/static/web2py_src.zip
        unzip web2py_src.zip

4. Clone this PicardSpace repository into the web2py applications directory.

        cd web2py/applications
        git clone https://github.com/basespace/PicardSpace.git

5. Make sure java is installed for running picard. (To test, just type 'java -version'). To install on ubuntu:

        sudo apt-get --yes install default-jre

6. Start web2py (and the web2py Scheduler), first navigating to the main 'web2py' directory. A web browser should launch with address localhost:8000.

        cd ..
        python web2py.py -K PicardSpace -X

7. Register your new PicardSpace app on the BaseSpace developer portal (developer.basespace.illumina.com) with these settings:

- App Launch Location: Projects
- Home Page: http://localhost:8000/PicardSpace
- Redirect URI: http://localhost:8000/PicardSpace/default/handle\_redirect\_uri

8. Add a product to your product catalog in the BaseSpace dev portal. Under the pricing tab, add a new consumable product named 'AlignmentQC' with a price of 2 iCredits (or whatever you wish). You'll need the new product Id in the next step.

9. Set app data and product info in the local database. Use the web2py admin panel (localhost:8000/PicardSpace/appadmin/index) to edit your local database. For table 'app_data', add your client_id, client_secret, and redirect_uri from the dev portal Details tab. For table 'purchase', add the product info you just added in the dev portal, with product.id=1, product.name=AlignmentQC, product.num=the id from the pricing tab in the dev portal, and product.price=your price.

Now go launch your new app in BaseSpace from any Project that contains an AppResult with a (small) BAM file.


