to create distrib on CentOS 6 64bit, osadt.tgz, you need to

1) download phantomjs and unpack into osadt/

https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-2.1.1-linux-x86_64.tar.bz2

If version is different, search and change executable_path in osa.py

2) 

yum install python-setuptools

easy_install pip

pip install virtualenv

3) create python virtualenv

cd /root/osadt/
virtualenv --system-site-packages --prompt='(osadt)' env
virtualenv --relocatable env
source env/bin/activate
pip install selenium

4) 

cd /root
tar zcf osadt.tgz osadt/
