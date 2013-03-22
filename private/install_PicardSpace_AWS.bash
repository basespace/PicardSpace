
#####################
### Run with sudo ###
#####################

# Install steps for PicardSpace on AWS instance

# First launch a fresh ubuntu instance - try this instance type:
# Ubuntu Server 12.04.1 LTS, 64-bit
# with security group that has these inbound TCP Ports open: 22 (SSH), 80 (HTTP), 443 (HTTPS)

# Copy this script to the instance
# scp -i mykey.pem path/install_aws.bash ubuntu@ec2-xx-xx-xxx-xx.compute-1.amazonaws.com:/home/ubuntu install_PicardSpace_AWS.bash

# SSH into instance with user ‘ubuntu’ (right click on instance in AWS Management Console and select Connect to get the public DNS name):
#ssh -i mykey.pem ubuntu@ec2-xx-xx-xxx-xxx.compute-1.amazonaws.com

# Now run this script:
# sudo bash install_PicardSpace_AWS.bash

# There will be a number of prompts including:
# - dialog of mail setup -- choose No Configuration
# - enter SSL cert info -- enter minimal info
# - enter apache web server password
# - enter git credentials since PicardSpace is a private repo


echo 'Getting and installing web2py one-step-production script'
echo
wget http://web2py.googlecode.com/hg/scripts/setup-web2py-ubuntu.sh
chmod +x setup-web2py-ubuntu.sh
./setup-web2py-ubuntu.sh

sleep 5

echo 'Installing git' 
sudo apt-get --yes install git

sleep 5

echo 'Adding PicardSpace to web2py applications directory'
cd /home/www-data/web2py/applications
git clone https://github.com/basespace/PicardSpace.git 
#(will need user/psswd since private repo)


echo 'Installing BaseSpace python SDK'
cd
git clone https://github.com/basespace/basespace-python-sdk.git
cd basespace-python-sdk/src
python setup.py install

sleep 5

echo 'Installing java'
sudo apt-get --yes install default-jre

sleep 5

echo 'Ensuring proper permissions on files (required), and Creating group to more easily edit files without need to change permissions (optional)'
# (so can run web2py and scripts as user www-data  [with sudo -u www-data], newly created files will be owned by www-data,  and can edit files as user ubuntu -- see http://serverfault.com/questions/6895/whats-the-best-way-of-handling-permissions-for-apache2s-user-www-data-in-var)
groupadd www-pub
usermod -a -G www-pub ubuntu
chown -R www-data:www-pub /home/www-data/
chmod 2775 /home/www-data
find /home/www-data -type d -exec chmod 2775 {} +
find /home/www-data -type f -exec chmod 0664 {} +
usermod -a -G www-pub www-data

#sleep 5
#echo 'Restarting web server'
#sudo /etc/init.d/apache2 restart

echo
echo "Now for the manual steps:"
echo
echo "Configure your database. Edit models/db.py and change the database definition to point to your RDS instance, such as:"
echo "  db = DAL('mysql://username:password@picardspacedb.xxxxxxxxxxxx.us-east-1.rds.amazonaws.com/db_name')"
echo
echo "Restart the web server:"
echo "sudo /etc/init.d/apache2 restart"
echo
echo "Add your product information to the 'product' table in the database. Use the web2py admin interface to do this"
echo
echo "Restart the web server:"
echo "sudo /etc/init.d/apache2 restart"
echo
echo "That's it!"
echo "Please logout and re-login so newly added www-pub group will be added to the ubuntu user account"

#Now run and scripts like this:
#sudo -u www-data python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/downloadfiles.py &
#sudo -u www-data python web2py.py -S PicardSpace -M -R applications/PicardSpace/private/analyzefiles.py &


